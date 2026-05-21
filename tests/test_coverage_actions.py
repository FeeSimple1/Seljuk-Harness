"""Aggressive coverage of actions.py validation guards (Pay/Muster/CtA/Loyalty)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S
from seljuk import actions as A
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


class FakeRoller:
    def __init__(self, v): self.v = v
    def d6(self): return self.v


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _r():
    return DiceRoller(seed=1)


# --- h_pay guards -----------------------------------------------------------
def test_pay_wrong_step():
    gs = _gs(); gs.meta.subphase = "levy.muster"
    with pytest.raises(IllegalAction):
        A.h_pay(gs, {"payer": "alp_arslan", "target": "alp_arslan"}, _r())


def test_pay_guard_branches():
    gs = _gs(); gs.meta.subphase = "levy.pay"; gs.meta.active_player = "seljuk"
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    aa.service_box = 5; aa.assets.coin = 2; aa.assets.loot = 2
    # bad_lord
    with pytest.raises(IllegalAction):
        A.h_pay(gs, {"payer": "nobody", "target": "alp_arslan", "asset": "coin"}, _r())
    # not_active_side
    with pytest.raises(IllegalAction):
        A.h_pay(gs, {"payer": "romanos_diogenes", "target": "romanos_diogenes", "asset": "coin"}, _r())
    # bad_asset
    with pytest.raises(IllegalAction):
        A.h_pay(gs, {"payer": "alp_arslan", "target": "alp_arslan", "asset": "gold"}, _r())
    # insufficient_asset
    with pytest.raises(IllegalAction):
        A.h_pay(gs, {"payer": "alp_arslan", "target": "alp_arslan", "asset": "coin", "amount": 99}, _r())


def test_pay_loot_location_guard():
    gs = _gs(); gs.meta.subphase = "levy.pay"; gs.meta.active_player = "seljuk"
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    aa.service_box = 5; aa.assets.loot = 2
    gs.locales["ani"].siege_markers = 1  # under siege -> loot can't pay
    with pytest.raises(IllegalAction):
        A.h_pay(gs, {"payer": "alp_arslan", "target": "alp_arslan", "asset": "loot"}, _r())


def test_pay_payer_not_on_map():
    gs = _gs(); gs.meta.subphase = "levy.pay"; gs.meta.active_player = "seljuk"
    aa = gs.lords["alp_arslan"]; aa.mustered = False; aa.assets.coin = 2
    with pytest.raises(IllegalAction):
        A.h_pay(gs, {"payer": "alp_arslan", "target": "alp_arslan", "asset": "coin"}, _r())


def test_pay_success_shifts_service():
    gs = _gs(); gs.meta.subphase = "levy.pay"; gs.meta.active_player = "seljuk"
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    aa.service_box = 5; aa.assets.coin = 2
    out = A.h_pay(gs, {"payer": "alp_arslan", "target": "alp_arslan", "asset": "coin", "amount": 1}, _r())
    assert out["ok"] and aa.service_box == 6 and aa.assets.coin == 1


# --- Muster handler guards --------------------------------------------------
def test_muster_handlers_wrong_step():
    gs = _gs(); gs.meta.subphase = "levy.pay"
    for fn, act in [
        (A.h_levy_lord, {"levyer": "alp_arslan", "target": "afsin_beg"}),
        (A.h_levy_transport, {"lord": "alp_arslan"}),
        (A.h_levy_capability, {"lord": "alp_arslan", "card": "S1"}),
        (A.h_levy_vassal, {"lord": "alp_arslan", "vassal_index": 0}),
        (A.h_levy_themata, {"lord": "manuel_komnenos"}),
    ]:
        with pytest.raises(IllegalAction):
            fn(gs, act, _r())


def test_levy_themata_not_roman_commander():
    gs = _gs(); gs.meta.subphase = "levy.muster"; gs.meta.active_player = "seljuk"
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    aa.flags["lordship_bonus"] = 5  # ensure it can act
    with pytest.raises(IllegalAction):
        A.h_levy_themata(gs, {"lord": "alp_arslan"}, _r())


def test_levy_lord_target_not_ready():
    gs = _gs(); gs.meta.subphase = "levy.muster"; gs.meta.active_player = "seljuk"
    levyer = gs.lords["alp_arslan"]; levyer.mustered = True; levyer.cylinder = "ani"
    levyer.flags["lordship_bonus"] = 5
    tgt = gs.lords["afsin_beg"]; tgt.mustered = True  # already mustered -> not ready
    with pytest.raises(IllegalAction):
        A.h_levy_lord(gs, {"levyer": "alp_arslan", "target": "afsin_beg"}, _r())


# --- Call to Arms guards ----------------------------------------------------
def test_cta_loot_wrong_step_and_no_loot():
    gs = _gs(); gs.meta.subphase = "levy.muster"
    with pytest.raises(IllegalAction):
        A.h_cta_loot(gs, {"lord": "alp_arslan"}, _r())
    gs.meta.subphase = "levy.call_to_arms"; gs.meta.active_player = "seljuk"
    gs.holding_boxes.mosul_baghdad_loot = 0
    with pytest.raises(IllegalAction):
        A.h_cta_loot(gs, {"lord": "alp_arslan"}, _r())


def test_cta_strategic_objective_guards():
    gs = _gs(); gs.meta.subphase = "levy.call_to_arms"; gs.meta.active_player = "roman"
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = "to_constantinople"
    # bad mode
    with pytest.raises(IllegalAction):
        A.h_cta_strategic_objective(gs, {"mode": "frobnicate"}, _r())
    # place with none available
    gs.holding_boxes.constantinople_strategic_objectives_available = 0
    with pytest.raises(IllegalAction):
        A.h_cta_strategic_objective(gs, {"mode": "place", "target": "ani"}, _r())
    # take when supply empty (all 3 out)
    gs.holding_boxes.constantinople_strategic_objectives_available = 3
    with pytest.raises(IllegalAction):
        A.h_cta_strategic_objective(gs, {"mode": "take"}, _r())


def test_cta_strategic_objective_place_on_seljuk_lord():
    gs = _gs(); gs.meta.subphase = "levy.call_to_arms"; gs.meta.active_player = "roman"
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = "to_constantinople"
    gs.holding_boxes.constantinople_strategic_objectives_available = 1
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    out = A.h_cta_strategic_objective(gs, {"mode": "place", "target": "alp_arslan"}, _r())
    assert out["lord"] == "alp_arslan" and aa.strategic_objective is True


# --- Loyalty Check natural-1 / natural-6 ------------------------------------
def test_loyalty_natural_one_never_switches_and_six_always():
    gs = _gs()
    tid = "robert_crepin"
    r1 = A.resolve_loyalty_check(gs, tid, "roman", FakeRoller(1))
    assert r1["natural"] == 1 and r1["switched"] is False
    gs2 = _gs()
    r6 = A.resolve_loyalty_check(gs2, tid, "roman", FakeRoller(6))
    assert r6["natural"] == 6 and r6["switched"] is True


def test_loyalty_bad_lord():
    gs = _gs()
    with pytest.raises(IllegalAction):
        A.resolve_loyalty_check(gs, "nobody", "roman", _r())
