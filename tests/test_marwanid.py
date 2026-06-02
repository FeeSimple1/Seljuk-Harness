"""Marwanid Alliance (S8) activation (3.5.1.1):

Spend a Coin during Call to Arms (from the Capability card or Alp Arslan) to
activate Amid / Mayyafariqin as a Seat for all Seljuk Lords until the end of the
next Winter Phase. No Tax there; expires at Winter.
"""
import pytest

from seljuk import scenarios as S, engine, actions, campaign
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _year_cta():
    gs = S.load_scenario("year_of_treacherous_ambition")  # S8 in play, 2 card coins
    gs.meta.phase = "levy"
    gs.meta.subphase = "levy.call_to_arms"
    gs.meta.active_player = "seljuk"
    gs.meta.levy_step_passed = {}
    return gs


def _marwanid_opts(gs):
    return [m for m in actions.enumerate_call_to_arms(gs) if m["type"] == "cta_marwanid"]


def test_marwanid_enumerated_only_when_in_play():
    # Emperor scenario has no S8 -> no Marwanid options.
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.subphase = "levy.call_to_arms"; gs.meta.active_player = "seljuk"
    assert _marwanid_opts(gs) == []
    # Year scenario has S8 -> options for both Locales and both coin sources.
    gs = _year_cta()
    opts = {(o["locale"], o["coin_source"]) for o in _marwanid_opts(gs)}
    assert ("amid", "card") in opts and ("mayyafariqin", "card") in opts


def test_marwanid_activation_from_card_spends_card_coin():
    gs = _year_cta()
    before = gs.seljuk.capability_coins["S8"]
    r = engine.apply_action(gs, {"type": "cta_marwanid", "locale": "amid", "coin_source": "card"})
    assert r["ok"] and r["active_seats"] == ["amid"]
    assert gs.seljuk.capability_coins["S8"] == before - 1
    assert gs.meta.notes["marwanid_seats"] == ["amid"]


def test_marwanid_activation_from_alp_arslan_spends_lord_coin():
    gs = _year_cta()
    gs.seljuk.capability_coins["S8"] = 0          # force the Lord-coin path
    gs.lords["alp_arslan"].assets.coin = 3
    engine.apply_action(gs, {"type": "cta_marwanid", "locale": "mayyafariqin", "coin_source": "alp_arslan"})
    assert gs.lords["alp_arslan"].assets.coin == 2
    assert gs.meta.notes["marwanid_seats"] == ["mayyafariqin"]


def test_marwanid_not_offered_without_a_coin():
    gs = _year_cta()
    gs.seljuk.capability_coins["S8"] = 0
    gs.lords["alp_arslan"].assets.coin = 0
    assert _marwanid_opts(gs) == []


def test_marwanid_rejects_double_activation_and_bad_locale():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locale": "amid", "coin_source": "card"})
    gs.meta.active_player = "seljuk"; gs.meta.levy_step_passed = {}
    with pytest.raises(IllegalAction):
        actions.h_cta_marwanid(gs, {"locale": "amid", "coin_source": "card"}, DiceRoller(1))
    with pytest.raises(IllegalAction):
        actions.h_cta_marwanid(gs, {"locale": "edessa", "coin_source": "card"}, DiceRoller(1))


def test_marwanid_seat_used_for_supply_by_any_seljuk_lord():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locale": "amid", "coin_source": "card"})
    ab = gs.lords["afsin_beg"]; ab.mustered = True; ab.cylinder = "amid"
    assert campaign._min_supply_cost(gs, ab) == 0           # at an activated Seat
    # A Roman Lord gets no Marwanid Seat.
    rl = next(l for l in gs.lords.values() if l.side == "roman")
    rl.mustered = True; rl.cylinder = "amid"
    assert campaign._min_supply_cost(gs, rl) != 0


def test_marwanid_seat_used_for_bounty():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locale": "mayyafariqin", "coin_source": "card"})
    sl = gs.lords["sav_tekin"]; sl.mustered = True; sl.cylinder = "mayyafariqin"
    sl.assets.loot = 2; sl.assets.carts = 2
    gs.holding_boxes.mosul_baghdad_loot = 0
    campaign._bounty(gs)
    assert gs.holding_boxes.mosul_baghdad_loot == 2


def test_marwanid_locale_may_not_be_taxed():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locale": "amid", "coin_source": "card"})
    ab = gs.lords["afsin_beg"]; ab.mustered = True; ab.cylinder = "amid"
    gs.meta.phase = "campaign"; gs.meta.active_lord = "afsin_beg"; gs.meta.actions_remaining = 2
    with pytest.raises(IllegalAction) as e:
        campaign.h_cmd_tax(gs, {"lord": "afsin_beg"}, DiceRoller(1))
    assert e.value.code == "marwanid_no_tax"


def test_marwanid_expires_at_end_of_winter():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locale": "amid", "coin_source": "card"})
    assert gs.meta.notes.get("marwanid_seats") == ["amid"]
    campaign._winter(gs)
    assert gs.meta.notes.get("marwanid_seats") is None


def test_marwanid_both_locales_can_be_activated():
    gs = _year_cta()
    engine.apply_action(gs, {"type": "cta_marwanid", "locale": "amid", "coin_source": "card"})
    gs.meta.active_player = "seljuk"; gs.meta.levy_step_passed = {}
    engine.apply_action(gs, {"type": "cta_marwanid", "locale": "mayyafariqin", "coin_source": "card"})
    assert set(gs.meta.notes["marwanid_seats"]) == {"amid", "mayyafariqin"}
    assert gs.seljuk.capability_coins["S8"] == 0           # both card coins spent


def test_marwanid_enumerated_moves_all_apply_cleanly():
    # Enumerator/handler agreement: every enumerated cta_marwanid applies on a copy.
    gs = _year_cta()
    kept, dropped = engine.validated_legal_moves(gs)
    marwanid = [m for m in kept if m.get("type") == "cta_marwanid"]
    assert marwanid and not any(d["action"].get("type") == "cta_marwanid" for d in dropped)
