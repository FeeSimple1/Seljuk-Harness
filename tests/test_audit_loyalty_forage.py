"""Audit fixes: Loyalty-Check Coin DRMs are deducted + gated; Forage by a
Besieged (inadequately) Lord; heavily-Besieged Forage is blocked."""
import pytest
from seljuk import scenarios as S, actions, campaign
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def test_loyalty_coin_for_is_deducted_from_commander():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"; aa.assets.coin = 3
    tgt = gs.lords["robert_crepin"]; tgt.side = "seljuk"; tgt.mustered = True; tgt.cylinder = "ani"
    # Seljuk checks Robert; spends 1 Coin (+1) from the Commander's mat.
    actions.resolve_loyalty_check(gs, "robert_crepin", "seljuk", DiceRoller(1), coins_for=1)
    assert aa.assets.coin == 2


def test_loyalty_resist_forbidden_for_besieged_target():
    gs = S.load_scenario("emperor_and_the_lion")
    tgt = gs.lords["robert_crepin"]; tgt.side = "seljuk"; tgt.mustered = True; tgt.besieged = True
    with pytest.raises(IllegalAction):
        actions.resolve_loyalty_check(gs, "robert_crepin", "roman", DiceRoller(1), coins_against=1)


def test_loyalty_insufficient_coin_rejected():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.lords["alp_arslan"].assets.coin = 0
    tgt = gs.lords["robert_crepin"]; tgt.side = "seljuk"; tgt.mustered = True; tgt.cylinder = "ani"
    with pytest.raises(IllegalAction):
        actions.resolve_loyalty_check(gs, "robert_crepin", "seljuk", DiceRoller(1), coins_for=2)


def test_defender_forages_friendly_gardens_even_heavily_besieged():
    import seljuk.static_data as sd
    gs = S.load_scenario("emperor_and_the_lion")
    loc = "melitene"   # Roman Town with Gardens, Size 2
    assert sd.locale(loc).get("gardens")
    rom = gs.lords["chatatourios"]; rom.mustered = True; rom.cylinder = loc; rom.besieged = True
    for d in ("alp_arslan", "afsin_beg"):   # 2 Seljuk besiegers -> heavily besieged
        gs.lords[d].mustered = True; gs.lords[d].cylinder = loc
    gs.meta.phase = "campaign"; gs.meta.active_lord = "chatatourios"; gs.meta.actions_remaining = 2
    r = campaign.h_cmd_forage(gs, {"lord": "chatatourios"}, DiceRoller(1))
    assert r["auto"] is True   # friendly Gardens -> auto even heavily Besieged


def test_seljuk_besieger_at_enemy_gardens_town_forage_blocked():
    gs = S.load_scenario("emperor_and_the_lion")
    loc = "melitene"
    sav = gs.lords["sav_tekin"]; sav.mustered = True; sav.cylinder = loc; sav.besieged = True
    for d in ("chatatourios", "robert_crepin"):   # 2 Roman Lords here -> heavy vs the Seljuk
        gs.lords[d].mustered = True; gs.lords[d].cylinder = loc; gs.lords[d].side = "roman"
    gs.meta.phase = "campaign"; gs.meta.active_lord = "sav_tekin"; gs.meta.actions_remaining = 2
    # Not friendly to the Seljuk Lord -> Gardens does not help -> Forage blocked.
    with pytest.raises(IllegalAction):
        campaign.h_cmd_forage(gs, {"lord": "sav_tekin"}, DiceRoller(1))
