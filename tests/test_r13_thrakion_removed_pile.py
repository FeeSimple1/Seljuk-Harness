"""Bug fix: R13 Thrakion Reinforcements returns a Themata Service Marker
*previously removed from play* (card text) -- it must draw from a removed-from-
play pile, not fabricate one. The pile is populated when markers are eliminated
(S5/S7/S15). R13 is a no-op when the pile is empty."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E
from seljuk.rng import DiceRoller


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _r():
    return DiceRoller(seed=1)


def test_no_op_when_nothing_removed():
    gs = _gs()
    gs.meta.themata_removed = []
    assert E._ev_thrakion(gs, {}, _r()).get("no_op") is True


def test_does_not_fabricate_marker():
    gs = _gs()
    gs.meta.themata_removed = []
    before = len(gs.themata.get("Anatolikon", []))
    E._ev_thrakion(gs, {"thema": "Anatolikon", "unit": "tagmata", "symbols": 3}, _r())
    assert len(gs.themata.get("Anatolikon", [])) == before     # nothing created


def test_round_trip_removed_then_returned():
    gs = _gs()
    # ensure a marker exists in a border Thema, remove it (S7), then return it (R13)
    thema = "Iberia"
    box_before = len(gs.themata.get(thema, []))
    assert box_before >= 1
    E._ev_deserters(gs, {"thema": thema}, _r())                # removes 1 -> pile
    assert len(gs.meta.themata_removed) == 1
    assert len(gs.themata[thema]) == box_before - 1
    E._ev_thrakion(gs, {}, _r())                               # return it home
    assert len(gs.themata[thema]) == box_before
    assert gs.meta.themata_removed == []
