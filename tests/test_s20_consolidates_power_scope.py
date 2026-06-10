"""Bug fix: S20 Alp Arslan Consolidates Power lowers only THIS YEAR's Seljuk
Unity threshold (the upcoming Winter box), by the number of *permanently*
disbanded Seljuk Lords -- excluding scenario setup-removed Lords. Previously it
lowered every year's box and counted setup-removed Lords."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E
from seljuk.rng import DiceRoller


def _r():
    return DiceRoller(seed=1)


def test_lowers_only_this_years_box():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)   # starts box 1 -> this year = box 3
    gs.meta.seljuk_unity_targets = {"3": 10, "6": 13, "9": 15}
    gs.lords["afsin_beg"].cylinder = "removed"             # one permanent disband
    out = E._ev_consolidates_power(gs, {}, _r())
    assert out["unity_lowered_by"] == 1 and out["box"] == 3
    assert gs.meta.seljuk_unity_targets == {"3": 9, "6": 13, "9": 15}   # others untouched


def test_no_effect_with_no_permanent_disbands():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.seljuk_unity_targets = {"3": 10}
    assert E._ev_consolidates_power(gs, {}, _r()).get("no_op") is True
    assert gs.meta.seljuk_unity_targets == {"3": 10}


def test_setup_removed_lords_do_not_count():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.seljuk_unity_targets = {"3": 10}
    sl = gs.lords["afsin_beg"]; sl.cylinder = "removed"; sl.flags["setup_removed"] = True
    assert E._ev_consolidates_power(gs, {}, _r()).get("no_op") is True   # excluded
    assert gs.meta.seljuk_unity_targets == {"3": 10}


def test_yota_setup_removed_seljuks_alone_are_no_effect():
    gs = S.load_scenario("year_of_treacherous_ambition", seed=1)   # 4 setup-removed Seljuk Lords, box 7
    assert E._ev_consolidates_power(gs, {}, _r()).get("no_op") is True
