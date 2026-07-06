"""Phase 4c: immediate Event resolvers + remaining passive Capabilities."""
import pytest

from seljuk import scenarios as S, engine, campaign, capabilities as C
from seljuk.rng import DiceRoller
from seljuk.state import ThemataMarker, IllegalAction


def _queue_event(gs, card, side):
    gs.meta.phase = "levy"
    gs.meta.pending.append({"type": "event_pending_resolution", "card": card, "side": side, "tags": ["immediate"]})


# --- Events ---
def test_event_shift_seljuk_cylinder_r5():
    gs = S.load_scenario("emperor_and_the_lion")  # Afsin Beg cylinder on Calendar box 2
    _queue_event(gs, "R5", "roman")
    engine.apply_action(gs, {"type": "resolve_event", "card": "R5", "args": {"lord": "afsin_beg", "what": "cylinder", "direction": "left"}})
    assert gs.lords["afsin_beg"].cylinder_calendar_box == 1


def test_event_afsin_murders_sets_fealty_2_r10():
    gs = S.load_scenario("emperor_and_the_lion")
    _queue_event(gs, "R10", "roman")
    engine.apply_action(gs, {"type": "resolve_event", "card": "R10", "args": {}})
    assert C.fealty_rating(gs, "afsin_beg") == 2
    assert "R10" in gs.meta.asterisks_used


def test_event_aleppo_independence_marks_r14():
    gs = S.load_scenario("emperor_and_the_lion")
    _queue_event(gs, "R14", "roman")
    engine.apply_action(gs, {"type": "resolve_event", "card": "R14", "args": {}})
    assert gs.meta.aleppo_independence_played


def test_event_resilient_agriculture_removes_two_seljuk_ravaged_r19():
    gs = S.load_scenario("emperor_and_the_lion")
    for loc in ("larisa", "tephrike", "keltzene"):
        gs.locales[loc].ravaged_side = "seljuk"  # all in the Roman Empire
    _queue_event(gs, "R19", "roman")
    r = engine.apply_action(gs, {"type": "resolve_event", "card": "R19", "args": {}})
    assert r["ravaged_removed"] == 2


def test_event_armenian_resistance_conquers_r20():
    gs = S.load_scenario("emperor_and_the_lion")
    _queue_event(gs, "R20", "roman")
    engine.apply_action(gs, {"type": "resolve_event", "card": "R20", "args": {"locale": "khliat"}})
    assert gs.locales["khliat"].conquered_side == "roman"


def test_event_deserters_removes_border_themata_s7():
    gs = S.load_scenario("emperor_and_the_lion")
    before = len(gs.themata["Iberia"])
    _queue_event(gs, "S7", "seljuk")
    engine.apply_action(gs, {"type": "resolve_event", "card": "S7", "args": {"thema": "Iberia"}})
    assert len(gs.themata["Iberia"]) == before - 1


def test_event_merchant_financing_exchange_s8():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.assets.carts = 2; aa.assets.coin = 2
    _queue_event(gs, "S8", "seljuk")
    engine.apply_action(gs, {"type": "resolve_event", "card": "S8", "args": {"lord": "alp_arslan", "to": "coin", "amount": 2}})
    assert aa.assets.carts == 0 and aa.assets.coin == 4


def test_event_consolidates_power_lowers_unity_s20():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.seljuk_unity_targets = {"3": 10}
    gs.lords["ibn_khan"].cylinder = "removed"  # one permanently disbanded Seljuk Lord
    _queue_event(gs, "S20", "seljuk")
    engine.apply_action(gs, {"type": "resolve_event", "card": "S20", "args": {}})
    assert gs.meta.seljuk_unity_targets["3"] == 9


def test_event_unimplemented_resolver_discards_no_op():
    gs = S.load_scenario("emperor_and_the_lion")
    _queue_event(gs, "R3", "roman")  # R3 is a Hold Event; no immediate resolver
    r = engine.apply_action(gs, {"type": "resolve_event", "card": "R3", "args": {}})
    assert r["no_op"]


# --- Passive Capabilities ---
def _activate(gs, lord, actions=4):
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = gs.lords[lord].side
    gs.meta.active_lord = lord; gs.meta.active_card = lord; gs.meta.actions_remaining = actions
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["chatatourios"]; gs.roman.plan_pointer = 1


def test_mules_first_pass_march_costs_one_even_laden_s25():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "melitene"; aa.capabilities = ["S25"]; aa.assets.loot = 1  # Laden
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "amid", "way_type": "pass"})
    assert r["cost"] == 1  # Mules: Pass + Laden would be 3, reduced to 1


def test_provincial_bureaucracy_first_empire_tax_no_ravage_r9():
    gs = S.load_scenario("emperor_and_the_lion")
    man = gs.lords["manuel_komnenos"]; man.mustered = True; man.cylinder = "ankyra"; man.capabilities = ["R9"]
    gs.lords["romanos_diogenes"].mustered = False; gs.lords["romanos_diogenes"].cylinder = "calendar"
    _activate(gs, "manuel_komnenos")
    r = engine.apply_action(gs, {"type": "cmd_tax", "lord": "manuel_komnenos"})
    assert r["placed_ravaged"] is False  # R9: no Ravaged on the first Empire Tax this Campaign
    assert gs.locales["ankyra"].ravaged_side is None


def test_winter_stay_capability_keeps_lord_in_place_s15():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "melitene"; aa.capabilities = ["S15"]  # Nizam al-Mulk
    campaign._begin_winter_quarters(gs)
    p = next(p for p in gs.meta.pending if p["type"] == "winter_quarters" and p["lord"] == "alp_arslan")
    assert p["may_stay"]              # S15: "may CHOOSE not to return" -- a choice, not an auto-stay
    engine.apply_action(gs, {"type": "winter_quarters", "lord": "alp_arslan", "stay": True})
    assert aa.cylinder == "melitene"  # chose to stay in the field


def test_prisoners_returns_loot_beyond_carts_s24():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]  # at Ani (Seat)
    aa.assets.loot = 3; aa.assets.carts = 2; aa.capabilities = ["S24"]
    campaign._bounty(gs)
    assert gs.holding_boxes.mosul_baghdad_loot == 3  # carts 2 + 1 (Prisoners)


def test_artukid_legacy_supply_from_amid_s10():
    gs = S.load_scenario("emperor_and_the_lion")
    art = gs.lords["artuk_beg"]; art.mustered = True; art.cylinder = "amid"; art.capabilities = ["S10"]
    art.service_box = 6
    cost = campaign._min_supply_cost(gs, art)
    assert cost == 0  # Amid is a Seat for Artuk via Artukid Legacy
