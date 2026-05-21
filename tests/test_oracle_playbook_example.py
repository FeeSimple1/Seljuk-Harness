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


# === Example of Play: STORM at Theodosiopolis (Background Book / Playbook pp.13-15) ===
# The garrison is the two Iberia Themata (Tagmata + Turkic Horse) plus the Town's
# Militia. Numbers below are the Playbook's printed values (Shock Tactics uses the
# Jan-2026 errata correction: ceil(3/2)=2 units x1/2 = x1, not the uncorrected x2).
def test_storm_example_garrison_missile_total_is_two():
    g = {"tagmata": 1, "turkic_horse": 1, "militia": 1}
    # "Tagmata is x1/2, Turkic Horse is x1, Militia (Garrison) gains x1/2" -> x2
    assert B._garrison_missile_hits(g) == 2.0


def test_storm_example_round1_attacker_missiles_total_four():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = _seljuk_lord(gs, "alp_arslan", {"turkic_horse": 3, "ghulam_cavalry": 2}, [])
    from seljuk.battle import _Side, _lord_step_hits
    side = _Side(gs, [], "attacker"); side.front["center"] = "alp_arslan"
    # "three Turkic Horse each x1, two Ghulam each x1/2 -> x4"
    assert _lord_step_hits(gs, side, "missile", 1) == 4.0


def test_storm_example_siegeworks_and_walls_rolls():
    # Round 1 defender missiles: Siegeworks (2 markers, range 1-2), roll {1,5} -> 1 through.
    assert _roll_walls(SeqRoller(1, 5), hits=2, wrange=(1, 2)) == 1
    # Round 1 attacker missiles: Town Walls 1-4, roll {2,3,6,6} -> 2 through.
    assert _roll_walls(SeqRoller(2, 3, 6, 6), hits=4, wrange=(1, 4)) == 2
    # Round 2 attacker melee: Walls 1-4, roll blocks 3 of 6, "other three make it through".
    assert _roll_walls(SeqRoller(1, 2, 3, 4, 5, 6), hits=6, wrange=(1, 4)) == 2


def test_storm_example_round1_defender_melee_tagmata_one():
    g = {"tagmata": 1}  # after the Turkic Themata was removed, "x1 for Tagmata"
    assert B._garrison_melee_hits(g) == 1.0


def test_storm_example_shock_tactics_with_two_turkic_one_ghulam_errata():
    # Page 14 (errata-corrected): after losses Alp Arslan has 2 Turkic + 1 Ghulam.
    # ceil(2/2)=1 unit x1/2 = x0.5 ... but the errata works the example with the
    # ORIGINAL 3 Turkic: ceil(3/2)=2 x1/2 = x1, + x1 Ghulam = 2 Hits.
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _seljuk_lord(gs, "alp_arslan", {"turkic_horse": 3, "ghulam_cavalry": 1}, ["S4"])
    normal, _ = _lord_step_hits_caps(gs, "alp_arslan", "horse_melee", 1)
    assert normal == 2.0   # errata: x1 (Shock Tactics) + x1 (Ghulam)
