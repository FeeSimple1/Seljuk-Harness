"""End-to-end oracle: the Playbook Example of Play (pp.14, 17).

The full Playbook game text is NOT in the provided source materials, but the
Errata & Clarifications (Jan 31 2026) preserve the example's exact printed
combat numbers. This test drives those numbers through the REAL engine
functions (`_lord_step_hits_caps`, `_roll_walls`, `_apply_hits`, `_lord_fate`,
`protection_range`) and asserts the engine reproduces them.

Documented numbers:
  p14: "half (rounded up) of Alp Arslan's Turkic Horse have x1/2 Hits due to
        Shock Tactics, which is x1 in total (after rounding), along with x1 for
        the remaining Ghulam." -> 2 Hits total. "The Roman player rolls Walls
        and gets a 1, 4 to cancel both hits before they get to his lone
        defending Tagmata unit."
  p17: "the Roman player cannot Withdraw into Theodosiopolis (the site of
        Battle) ... They must retreat back to Keltzene."
       "LAMELLAR ARMOR or, since this is a melee strike, Evade" -> Protection 1-3.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S
from seljuk import battle as B, capabilities as C
from seljuk.battle import DecisionContext, _lord_step_hits_caps, _roll_walls, _apply_hits, _lord_fate
from seljuk.rng import DiceRoller


class SeqRoller:
    """Deterministic roller returning a fixed sequence of d6 values."""
    def __init__(self, *vals): self.vals = list(vals); self.i = 0
    def d6(self):
        v = self.vals[min(self.i, len(self.vals) - 1)]; self.i += 1; return v
    def roll(self, n): return [self.d6() for _ in range(n)]


def _seljuk_lord(gs, lid, forces, caps):
    l = gs.lords[lid]; l.side = "seljuk"; l.mustered = True; l.cylinder = "ani"
    l.forces = dict(forces); l.routed = {}; l.capabilities = list(caps)
    l.flags["turkic_routed_battle"] = 0
    return l


# --- p14: Shock Tactics force produces exactly 2 Hits ----------------------
def test_p14_shock_tactics_two_hits_total():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _seljuk_lord(gs, "alp_arslan", {"turkic_horse": 3, "ghulam_cavalry": 1}, ["S4"])  # S4 = Shock Tactics
    normal, anti = _lord_step_hits_caps(gs, "alp_arslan", "horse_melee", 1)
    # ceil(3/2)=2 Turkic x0.5 = 1.0, plus 1 Ghulam x1.0 = 1.0  -> 2.0 total
    assert normal == 2.0 and anti == 0.0
    n_hits = int(normal + 0.999)
    assert n_hits == 2  # rounds up to 2 Hits


# --- p14: defender's Walls roll {1,4} cancels both Hits --------------------
def test_p14_walls_roll_one_four_cancels_both_hits():
    # ankyra is a Town with Walls 1-4 (matching the example's cancelling rolls).
    remaining = _roll_walls(SeqRoller(1, 4), hits=2, wrange=(1, 4))
    assert remaining == 0  # both cancelled before reaching the Tagmata


def test_p14_lone_tagmata_survives_after_walls():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    d = gs.lords["chatatourios"]; d.side = "roman"; d.mustered = True
    d.forces = {"tagmata": 1}; d.routed = {}
    # 0 Hits reach the defender after Walls -> Tagmata unharmed.
    applied = _apply_hits(gs, "chatatourios", 0, "melee", DecisionContext(), DiceRoller(seed=1))
    assert applied == [] and d.forces["tagmata"] == 1


# --- p17: melee Protection uses Lamellar OR Evade (1-3) --------------------
def test_p17_melee_protection_one_to_three():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _seljuk_lord(gs, "alp_arslan", {"turkic_horse": 4}, [])      # Evade (no Lamellar)
    assert C.protection_range(gs, "alp_arslan", "turkic_horse", "melee") == (1, 3)
    _seljuk_lord(gs, "alp_arslan", {"turkic_horse": 4}, ["S1"])  # Lamellar Armor
    assert C.protection_range(gs, "alp_arslan", "turkic_horse", "melee") == (1, 3)


# --- p17: attacking Romans cannot Withdraw into the battle site ------------
def test_p17_attacker_retreats_to_origin_cannot_withdraw():
    locale = "ankyra"  # a Roman-Friendly Stronghold (stands in for Theodosiopolis)
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    a = gs.lords["chatatourios"]; a.side = "roman"; a.mustered = True; a.cylinder = locale
    fate = _lord_fate(gs, a, "attacker", locale, conceded=False, ctx=DecisionContext())
    assert fate != "withdraw"
    assert a.besieged is False and a.cylinder != locale  # retreated off the battle site
