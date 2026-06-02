"""Phase 4: S13 Peace Offering coin-gate + Gifts Exchanged 4-Coin pool."""
import pytest
from seljuk import scenarios as S, campaign, engine
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def test_s13_peace_gate_requires_one_coin_per_card():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.notes["peace_offering_season"] = True
    lord = gs.lords["afsin_beg"]; lord.mustered = True; lord.cylinder = "manbij"
    lord.assets.coin = 0
    gs.lords["alp_arslan"].assets.coin = 0
    with pytest.raises(IllegalAction):
        campaign._peace_gate(gs, lord)              # no Coin anywhere -> blocked
    lord.assets.coin = 1
    campaign._peace_gate(gs, lord)
    assert lord.assets.coin == 0 and lord.flags.get("peace_paid_this_card")
    campaign._peace_gate(gs, lord)                  # already paid this card -> free
    assert lord.assets.coin == 0


def test_s13_peace_gate_can_pay_from_alp_arslan():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.notes["peace_offering_season"] = True
    lord = gs.lords["afsin_beg"]; lord.mustered = True; lord.cylinder = "manbij"; lord.assets.coin = 0
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"; aa.besieged = False; aa.assets.coin = 2
    campaign._peace_gate(gs, lord)
    assert aa.assets.coin == 1                       # paid from Alp Arslan


def test_s13_gifts_coin_pool_two_per_side():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.notes["gifts_coins"] = 4
    gs.meta.notes["gifts_taken"] = {"seljuk": 0, "roman": 0}
    lord = gs.lords["sav_tekin"]; lord.mustered = True; lord.cylinder = "manbij"; lord.assets.coin = 0
    gs.meta.phase = "campaign"; gs.meta.active_lord = "sav_tekin"
    engine.apply_action(gs, {"type": "cmd_take_gift_coin", "lord": "sav_tekin"})
    engine.apply_action(gs, {"type": "cmd_take_gift_coin", "lord": "sav_tekin"})
    assert lord.assets.coin == 2 and gs.meta.notes["gifts_coins"] == 2
    with pytest.raises(IllegalAction):              # each side limited to 2
        engine.apply_action(gs, {"type": "cmd_take_gift_coin", "lord": "sav_tekin"})
