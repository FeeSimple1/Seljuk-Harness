"""Bug fix: S15 Thematic Troops Desert removes 1 Levied OR Unlevied Themata
marker in Alp Arslan's Thema. The resolver must search the Unlevied box,
defending markers at his Locale (even Besieged), and Levied markers on Lord mats
at his Locale -- not only the Unlevied box."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E
from seljuk.state import ThemataMarker, IllegalAction
from seljuk.rng import DiceRoller

THEMA, LOC = "Iberia", "theodosiopolis"   # theodosiopolis is in the Iberia Thema


def _gs():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = LOC
    return gs


def _r():
    return DiceRoller(seed=1)


def test_removes_unlevied_from_box():
    gs = _gs()
    gs.themata[THEMA] = [ThemataMarker(unit="tagmata")]
    r = E._ev_thematic_desert(gs, {}, _r())
    assert r["removed"]["source"] == "unlevied"
    assert gs.themata[THEMA] == []


def test_removes_defending_marker_at_locale_when_box_empty():
    gs = _gs()
    gs.themata[THEMA] = []                                   # nothing unlevied
    gs.locales[LOC].themata_defending = [ThemataMarker(unit="tagmata", home_thema=THEMA)]
    r = E._ev_thematic_desert(gs, {}, _r())
    assert r["removed"]["source"] == "defending"
    assert gs.locales[LOC].themata_defending == []


def test_removes_levied_marker_on_colocated_lord_mat():
    gs = _gs()
    gs.themata[THEMA] = []
    gs.locales[LOC].themata_defending = []
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = LOC
    rom.themata_on_mat = [ThemataMarker(unit="tagmata", home_thema=THEMA)]
    r = E._ev_thematic_desert(gs, {}, _r())
    assert r["removed"]["source"] == "levied" and r["removed"]["lord"] == "romanos_diogenes"
    assert rom.themata_on_mat == []


def test_no_themata_anywhere_is_no_op():
    """No marker in box / defending / co-located mats -> the immediate Event has
    no effect (must NOT raise, or the Levy stalls on an unresolvable pending)."""
    gs = _gs()
    gs.themata[THEMA] = []
    gs.locales[LOC].themata_defending = []
    for l in gs.lords.values():
        if l.cylinder == LOC:
            l.themata_on_mat = []
    assert E._ev_thematic_desert(gs, {}, _r()).get("no_op") is True


def test_no_op_when_not_in_thema():
    gs = _gs(); gs.lords["alp_arslan"].mustered = False
    assert E._ev_thematic_desert(gs, {}, _r()).get("no_op") is True
