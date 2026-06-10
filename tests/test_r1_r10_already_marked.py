"""Bug fix: the 'if already marked' branches of R1 Flooded River Crossing and R10
Afsin Murders both apply -1 Lordship to a *Seljuk* Lord (Seljuk choice). R1
previously accepted any Lord (incl. Roman); R10's already-marked branch was
missing entirely (it re-set Afsin's Fealty on every draw)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E
from seljuk.rng import DiceRoller


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _r():
    return DiceRoller(seed=1)


def test_r1_already_marked_seljuk_target_gets_penalty():
    gs = _gs(); gs.meta.asterisks_used.append("R1")
    r = E._ev_flooded_river(gs, {"lord": "alp_arslan"}, _r())
    assert r.get("lordship_penalty") == "alp_arslan"
    assert gs.lords["alp_arslan"].flags.get("lordship_persist") == -1


def test_r1_already_marked_roman_target_is_no_op():
    gs = _gs(); gs.meta.asterisks_used.append("R1")
    r = E._ev_flooded_river(gs, {"lord": "romanos_diogenes"}, _r())
    assert r.get("no_op") is True
    assert gs.lords["romanos_diogenes"].flags.get("lordship_persist") in (None, 0)


def test_r10_first_draw_sets_fealty_2():
    gs = _gs()
    if "R10" in gs.meta.asterisks_used:
        gs.meta.asterisks_used.remove("R10")
    r = E._ev_afsin_murders(gs, {}, _r())
    assert r.get("afsin_fealty") == 2 and gs.meta.notes.get("afsin_fealty_2") is True


def test_r10_already_marked_applies_seljuk_lordship_penalty():
    gs = _gs(); gs.meta.asterisks_used.append("R10")
    r = E._ev_afsin_murders(gs, {"lord": "sav_tekin"}, _r())
    assert r.get("lordship_penalty") == "sav_tekin"
    assert gs.lords["sav_tekin"].flags.get("lordship_persist") == -1


def test_r10_already_marked_roman_target_is_no_op():
    gs = _gs(); gs.meta.asterisks_used.append("R10")
    r = E._ev_afsin_murders(gs, {"lord": "romanos_diogenes"}, _r())
    assert r.get("no_op") is True
