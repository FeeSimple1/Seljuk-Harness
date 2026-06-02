"""Marwanid Alliance (S8) (3.5.1.1): in Call to Arms the Seljuk player may EITHER
transfer 1 Coin from Alp Arslan onto the card, OR spend Coin from the card (1 per
Locale) to activate Amid/Mayyafariqin as Seats until end of next Winter.
"""
import pytest
from seljuk import scenarios as S, engine, actions, campaign
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _year_cta():
    gs = S.load_scenario("year_of_treacherous_ambition")  # S8 in play, 2 card coins
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.call_to_arms"
    gs.meta.active_player = "seljuk"; gs.meta.levy_step_passed = {}
    return gs


def _types(gs):
    return {m["type"] for m in actions.enumerate_call_to_arms(gs)}


def test_marwanid_not_offered_without_capability():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.subphase = "levy.call_to_arms"; gs.meta.active_player = "seljuk"
    assert "cta_marwanid" not in _types(gs) and "cta_marwanid_bank" not in _types(gs)


def test_marwanid_activate_spends_card_coin_only():
    gs = _year_cta()
    before = gs.seljuk.capability_coins["S8"]
    r = engine.apply_action(gs, {"type": "cta_marwanid", "locales": ["amid"]})
    assert r["ok"] and gs.meta.notes["marwanid_seats"] == ["amid"]
    assert gs.seljuk.capability_coins["S8"] == before - 1


def test_marwanid_activate_both_locales_in_one_option():
    gs = _year_cta()  # 2 card coins
    engine.apply_action(gs, {"type": "cta_marwanid", "locales": ["amid", "mayyafariqin"]})
    assert set(gs.meta.notes["marwanid_seats"]) == {"amid", "mayyafariqin"}
    assert gs.seljuk.capability_coins["S8"] == 0


def test_marwanid_bank_transfers_alp_arslan_coin_to_card():
    gs = _year_cta()
    gs.seljuk.capability_coins["S8"] = 0
    gs.lords["alp_arslan"].assets.coin = 2
    engine.apply_action(gs, {"type": "cta_marwanid_bank"})
    assert gs.lords["alp_arslan"].assets.coin == 1
    assert gs.seljuk.capability_coins["S8"] == 1


def test_marwanid_cannot_activate_without_card_coin():
    gs = _year_cta()
    gs.seljuk.capability_coins["S8"] = 0   # Alp Arslan's Coin must be banked first
    gs.lords["alp_arslan"].assets.coin = 3
    with pytest.raises(IllegalAction):
        actions.h_cta_marwanid(gs, {"locales": ["amid"]}, DiceRoller(1))
    # Banking is offered instead; activation is not.
    assert "cta_marwanid_bank" in _types(gs) and "cta_marwanid" not in _types(gs)


def test_marwanid_rejects_double_and_bad_locale():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locales": ["amid"]})
    gs.meta.active_player = "seljuk"; gs.meta.levy_step_passed = {}
    with pytest.raises(IllegalAction):
        actions.h_cta_marwanid(gs, {"locales": ["amid"]}, DiceRoller(1))      # already active
    with pytest.raises(IllegalAction):
        actions.h_cta_marwanid(gs, {"locales": ["edessa"]}, DiceRoller(1))    # not a Marwanid Locale


def test_marwanid_seat_used_for_supply_and_bounty():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locales": ["amid"]})
    ab = gs.lords["afsin_beg"]; ab.mustered = True; ab.cylinder = "amid"
    assert campaign._min_supply_cost(gs, ab) == 0
    rl = next(l for l in gs.lords.values() if l.side == "roman")
    rl.mustered = True; rl.cylinder = "amid"
    assert campaign._min_supply_cost(gs, rl) != 0


def test_marwanid_locale_may_not_be_taxed():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locales": ["amid"]})
    ab = gs.lords["afsin_beg"]; ab.mustered = True; ab.cylinder = "amid"
    gs.meta.phase = "campaign"; gs.meta.active_lord = "afsin_beg"; gs.meta.actions_remaining = 2
    with pytest.raises(IllegalAction) as e:
        campaign.h_cmd_tax(gs, {"lord": "afsin_beg"}, DiceRoller(1))
    assert e.value.code == "marwanid_no_tax"


def test_marwanid_expires_at_end_of_winter():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locales": ["amid"]})
    campaign._winter(gs)
    assert gs.meta.notes.get("marwanid_seats") is None


def test_marwanid_enumerated_moves_all_apply_cleanly():
    gs = _year_cta()
    kept, dropped = engine.validated_legal_moves(gs)
    assert not any(d["action"].get("type", "").startswith("cta_marwanid") for d in dropped)
