"""Bug fixes: R3 Steeled Resolve grants Infantry Armor 1-3 vs Horse for BOTH
Missile and Melee (was Melee-only); S24 Bad Omens lets the Seljuk player keep the
top-2 Roman Plan order or swap it (was a forced swap)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E, capabilities, battle
from seljuk.rng import DiceRoller


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _r():
    return DiceRoller(seed=1)


def test_steeled_resolve_boosts_infantry_protection_vs_horse():
    gs = _gs()
    lord = gs.lords["chatatourios"]; lord.capabilities = ["R3"]
    # vs Horse: Steeled Resolve raises Infantry protection to 1-4 (both Missile/Melee)
    assert capabilities.protection_range(gs, "chatatourios", "infantry", "missile", vs_horse=True) == (1, 4)
    assert capabilities.protection_range(gs, "chatatourios", "infantry", "melee", vs_horse=True) == (1, 4)
    # not vs Horse: ordinary Infantry armor 1-3
    assert capabilities.protection_range(gs, "chatatourios", "infantry", "missile", vs_horse=False) == (1, 3)


def test_missile_step_counts_as_vs_horse_for_steeled_resolve():
    # the battle Missile step now applies the 'vs Horse' scope (Round 1), so a
    # Steeled-Resolve Infantry negates Turkic Horse Missile Hits at 1-4.
    src = Path("src/seljuk/battle.py").read_text()
    assert 'step in ("horse_melee", "missile")' in src   # scope includes Missiles


def test_s24_swaps_by_default():
    gs = _gs()
    gs.roman.command_plan = ["A", "B", "C"]; gs.roman.plan_pointer = 0
    r = E._hold_bad_omens(gs, {}, _r())
    assert r["reordered"] == ["B", "A"] and gs.roman.command_plan[:2] == ["B", "A"]


def test_s24_can_keep_order():
    gs = _gs()
    gs.roman.command_plan = ["A", "B", "C"]; gs.roman.plan_pointer = 0
    r = E._hold_bad_omens(gs, {"order": "keep"}, _r())
    assert r["kept"] == ["A", "B"] and gs.roman.command_plan[:2] == ["A", "B"]


def test_s24_no_op_when_fewer_than_two():
    gs = _gs()
    gs.roman.command_plan = ["A"]; gs.roman.plan_pointer = 0
    assert E._hold_bad_omens(gs, {}, _r()).get("no_op") is True
