"""End-to-end oracle: the Playbook Example of Play - BATTLE (pp.16-18).

The Playbook text (source/Seljuk_Background_Book_web.pdf) prints every Strike
total, Protection roll, and post-battle number for the Keltzene -> Theodosiopolis
Battle (Romanos + Nikephoros attack Alp Arslan + Artuk Beg, Summer 1070). These
tests drive the printed values through the REAL engine functions. Where the
Jan-2026 errata corrects the example (p17 Retreat/Withdraw; Lamellar/Evade),
the errata text governs.

Printed sequence pinned here:
  R21 Nomadic Tribes: "eliminate two Turkic Horse from Alp Arslan's mat".
  Rd1 Missiles: Alp x3 (2 Turkic x1 + 2 Ghulam x1/2), Artuk x4 (4 Turkic),
    Romanos x3 (2 Tagmata x1/2 + 2 Turkic x1), Nikephoros x1 (lone Turkic).
  Protections: Infantry 1-3, Ghulam 1-4, Tagmata 1-3, Turkic 1 (Missile) /
    1-3 Evade (Melee; Lamellar Armor gives the same 1-3, errata p17).
  Rd1 Melee: Alp x1 (lone unrouted Ghulam), Romanos x2 (2 Tagmata),
    Artuk Foot x1 (lone Infantry).
  Rd2 (Artuk Flanks Romanos): Seljuk Missiles pool x5 (rounded up from x4.5 =
    Alp 1 Turkic + 1 Ghulam = 1.5, Artuk 3 Turkic = 3.0).
  Concede: Romanos' x2 Missiles and x2 Horse Melee each halve to x1.
  Service (losing side Retreats): roll 2 -> 1 box, roll 5 -> 2 boxes.
  Spoils: the Conceded+Retreating Romanos (3 Provender, 2 Carts) hands over
    exactly the 1 excess Provender.
  Losses: Routed Infantry rolls 1-3 (a 1 recovers); Routed Turkic uses Evade
    1-3 post-Battle (a 5 eliminates).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S
from seljuk import battle as B, capabilities as C
from seljuk.battle import (DecisionContext, _consume_battle_events,
                           _lord_step_hits_caps, _natural_protection,
                           _spoils_and_removal)
from seljuk.rng import DiceRoller


def _mk(gs, lid, side, forces, caps=(), cylinder="ani"):
    l = gs.lords[lid]
    l.side = side; l.mustered = True; l.cylinder = cylinder
    l.forces = dict(forces); l.routed = {}; l.lost = {}
    l.capabilities = list(caps); l.flags["turkic_routed_battle"] = 0
    return l


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def test_battle_example_r21_removes_two_turkic_pre_battle():
    gs = _gs()
    aa = _mk(gs, "alp_arslan", "seljuk", {"turkic_horse": 4, "ghulam_cavalry": 2})
    gs.roman.held_events = ["R21"]
    played, cc, charge = _consume_battle_events(gs, {"roman": ["R21"]}, locale="ani")
    assert played["roman"] == ["R21"] and not cc and not charge
    assert "R21" not in gs.roman.held_events and "R21" in gs.roman.draw_deck
    assert aa.forces["turkic_horse"] == 2      # "eliminate two Turkic Horse"


def test_battle_example_round1_missile_totals():
    gs = _gs()
    _mk(gs, "alp_arslan", "seljuk", {"turkic_horse": 2, "ghulam_cavalry": 2})   # after R21
    _mk(gs, "artuk_beg", "seljuk", {"turkic_horse": 4, "infantry": 1})
    _mk(gs, "romanos_diogenes", "roman", {"tagmata": 2, "infantry": 1, "turkic_horse": 2})
    _mk(gs, "nikephoros_bryennios", "roman", {"turkic_horse": 1})               # after x4 routs
    assert _lord_step_hits_caps(gs, "alp_arslan", "missile", 1)[0] == 3.0
    assert _lord_step_hits_caps(gs, "artuk_beg", "missile", 1)[0] == 4.0
    assert _lord_step_hits_caps(gs, "romanos_diogenes", "missile", 1)[0] == 3.0
    assert _lord_step_hits_caps(gs, "nikephoros_bryennios", "missile", 1)[0] == 1.0


def test_battle_example_protection_ranges():
    gs = _gs()
    _mk(gs, "alp_arslan", "seljuk", {"turkic_horse": 2, "ghulam_cavalry": 2}, caps=["S1"])  # Lamellar
    _mk(gs, "romanos_diogenes", "roman", {"tagmata": 2, "infantry": 1, "turkic_horse": 2})
    assert C.protection_range(gs, "romanos_diogenes", "infantry", "missile") == (1, 3)
    assert C.protection_range(gs, "romanos_diogenes", "tagmata", "missile") == (1, 3)
    assert C.protection_range(gs, "romanos_diogenes", "turkic_horse", "missile") == (1, 1)
    assert C.protection_range(gs, "romanos_diogenes", "turkic_horse", "melee") == (1, 3)  # Evade
    assert C.protection_range(gs, "alp_arslan", "ghulam_cavalry", "missile") == (1, 4)
    # Errata p17: Lamellar Armor OR Evade both give 1-3 on a melee strike.
    assert C.protection_range(gs, "alp_arslan", "turkic_horse", "melee") == (1, 3)


def test_battle_example_round1_melee_totals():
    gs = _gs()
    _mk(gs, "alp_arslan", "seljuk", {"turkic_horse": 2, "ghulam_cavalry": 1})   # 1 Ghulam Routed
    _mk(gs, "romanos_diogenes", "roman", {"tagmata": 2, "infantry": 1, "turkic_horse": 1})
    _mk(gs, "artuk_beg", "seljuk", {"turkic_horse": 3, "infantry": 1})
    # "x1 Hit in Melee from his Ghulam" (Turkic Horse have no Melee in Battle).
    assert _lord_step_hits_caps(gs, "alp_arslan", "horse_melee", 1)[0] == 1.0
    # "Romanos does x1 Melee Hit for each Tagmata, for a total of 2."
    assert _lord_step_hits_caps(gs, "romanos_diogenes", "horse_melee", 1)[0] == 2.0
    # "Artuk Beg still has his single Infantry, which does x1 Hit."
    assert _lord_step_hits_caps(gs, "artuk_beg", "foot_melee", 1)[0] == 1.0


def test_battle_example_round2_flanked_missile_pool_rounds_to_five():
    gs = _gs()
    _mk(gs, "alp_arslan", "seljuk", {"turkic_horse": 1, "ghulam_cavalry": 1})
    _mk(gs, "artuk_beg", "seljuk", {"turkic_horse": 3, "infantry": 1})
    a = _lord_step_hits_caps(gs, "alp_arslan", "missile", 2)[0]
    b = _lord_step_hits_caps(gs, "artuk_beg", "missile", 2)[0]
    assert a == 1.5 and b == 3.0               # "a total of x5 (rounded up from x4.5)"
    assert int(a + b + 0.999) == 5


def test_battle_example_conceded_hits_halve():
    gs = _gs()
    _mk(gs, "romanos_diogenes", "roman", {"tagmata": 2, "turkic_horse": 1})
    n = _lord_step_hits_caps(gs, "romanos_diogenes", "missile", 2)[0]
    assert n == 2.0                            # "x2 Hits in Missiles"
    assert int(n / 2.0 + 0.999) == 1           # "halved to x1 because he Conceded"
    m = _lord_step_hits_caps(gs, "romanos_diogenes", "horse_melee", 2)[0]
    assert m == 2.0 and int(m / 2.0 + 0.999) == 1


def test_battle_example_losses_natural_protection():
    # "rolls against the 1-3 Protection rating of his Infantry and gets a 1;
    #  the unit is moved back to Forces" / Turkic "allowed to use his Evade
    #  Protection rating, and rolls a 5" -> eliminated.
    assert _natural_protection("infantry") == (1, 3)
    assert _natural_protection("turkic_horse") == (1, 3)
    assert _natural_protection("tagmata") == (1, 3)


class _SeqRoller:
    def __init__(self, *vals): self.vals = list(vals); self.i = 0
    def d6(self):
        v = self.vals[min(self.i, len(self.vals) - 1)]; self.i += 1; return v
    def roll(self, n): return [self.d6() for _ in range(n)]


def test_battle_example_service_shift_rolls_via_end_battle():
    # "Romanos rolls a 2, which shifts his Service Marker ... one box (Spring
    #  1071 -> Autumn 1070). Nikephoros rolls a 5 ... two boxes." (4.8.3)
    gs = _gs()
    rom = _mk(gs, "romanos_diogenes", "roman", {"tagmata": 1}, cylinder="keltzene")
    nik = _mk(gs, "nikephoros_bryennios", "roman", {"tagmata": 1}, cylinder="keltzene")
    aa = _mk(gs, "alp_arslan", "seljuk", {"turkic_horse": 3}, cylinder="keltzene")
    rom.service_box, nik.service_box = 10, 8
    # Attackers lost at Theodosiopolis-stand-in; both Retreat (origin friendly).
    from seljuk.battle import _end_battle
    ev = _end_battle(gs, ["romanos_diogenes", "nikephoros_bryennios"], ["alp_arslan"],
                     "attacker", "attacker", "keltzene", DecisionContext(),
                     _SeqRoller(2, 5, 1, 1, 1, 1, 1, 1))
    sv = {e["lord"]: e for e in ev["service"]}
    if "romanos_diogenes" in sv:               # fate must be Retreat for a shift
        assert sv["romanos_diogenes"]["roll"] == 2 and sv["romanos_diogenes"]["shift"] == 1
        assert rom.service_box == 9
    if "nikephoros_bryennios" in sv:
        assert sv["nikephoros_bryennios"]["roll"] == 5 and sv["nikephoros_bryennios"]["shift"] == 2
        assert nik.service_box == 6
    assert sv, "losing Retreating Lords must take Service rolls (4.8.3)"


def test_battle_example_conceded_retreat_spoils_excess_provender():
    gs = _gs()
    rom = _mk(gs, "romanos_diogenes", "roman", {"tagmata": 2})
    aa = _mk(gs, "alp_arslan", "seljuk", {"turkic_horse": 2})
    rom.assets.carts = 2; rom.assets.provender = 3; rom.assets.coin = 1; rom.assets.loot = 0
    aa.assets.provender = 2
    events = {"retreat": [{"lord": "romanos_diogenes", "fate": "retreat"}],
              "losses": [], "service": [], "removed": [], "spoils_to": "defender"}
    _spoils_and_removal(gs, ["romanos_diogenes"], ["alp_arslan"], "attacker",
                        events, conceder="attacker")
    # Conceded + Retreated: hands over Loot and the excess Provender ONLY.
    assert rom.assets.provender == 2 and rom.assets.coin == 1 and rom.assets.carts == 2
    assert aa.assets.provender == 3            # "Alp Arslan takes the Provender"
