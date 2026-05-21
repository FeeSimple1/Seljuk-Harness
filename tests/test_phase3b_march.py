"""Phase 3b: March (4.3), costs (4.3.2-.3), Group March (4.3.1),
Besiege/Bypass (4.3.5), Approach (4.3.4)."""
import pytest

from seljuk import scenarios as S, engine, campaign, map as gmap
from seljuk.state import IllegalAction


def _activate(gs, lord_id, actions=4):
    gs.meta.phase = "campaign"
    gs.meta.subphase = "campaign.command"
    gs.meta.active_player = gs.lords[lord_id].side
    gs.meta.active_lord = lord_id
    gs.meta.active_card = lord_id
    gs.meta.actions_remaining = actions
    # ongoing plans so card-end hands off rather than cascading to End Campaign
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["chatatourios"]; gs.roman.plan_pointer = 1


def _way(a, b, t=None):
    w = [e for e in gmap.ways_between(a, b)]
    return next((e for e in w if t is None or e["type"] == t), w[0])


def test_march_cost_turkic_first_road_is_zero_433():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.forces = {"turkic_horse": 4}  # all-Turkic
    aa.assets.loot = 0; aa.assets.provender = 0
    cost = campaign.march_cost(gs, [aa], _way("ani", "mempet"), first_march=True)
    assert cost == 0


def test_march_cost_turkic_first_pass_is_one_433():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.forces = {"turkic_horse": 4}; aa.assets.loot = 0; aa.assets.provender = 0
    cost = campaign.march_cost(gs, [aa], _way("ani", "ararat", "pass"), first_march=True)
    assert cost == 1


def test_march_cost_laden_doubles_and_pass_adds_433():
    gs = S.load_scenario("emperor_and_the_lion")
    ch = gs.lords["chatatourios"]
    ch.forces = {"tagmata": 1}  # not all-Turkic
    ch.assets.loot = 1  # Laden
    cost = campaign.march_cost(gs, [ch], _way("melitene", "amid", "pass"), first_march=True)
    assert cost == 3  # 2 (Laden) + 1 (Pass)


def test_cmd_march_moves_and_spends_actions():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]  # at Ani
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "mempet", "way_type": "road"})
    assert aa.cylinder == "mempet" and aa.moved_fought
    assert r["cost"] == 1 and gs.meta.actions_remaining == 3


def test_holding_box_march_is_whole_card_433():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "nusaybin"  # Road-WC to Mosul & Baghdad (Seljuk Holding Box)
    _activate(gs, "alp_arslan", actions=4)
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "to_mosul_and_baghdad"})
    assert r["cost"] == 4  # consumed the whole card
    assert aa.cylinder == "to_mosul_and_baghdad"


def test_enemy_holding_box_rejected_131():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "western_anatolia"  # Road-WC to (Roman) Constantinople
    _activate(gs, "alp_arslan")
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "to_constantinople"})


def test_march_to_enemy_stronghold_triggers_besiege_or_bypass_435():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "larisa"  # Roman, adjacent to Melitene (Roman town)
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    assert r.get("pending") == "besiege_or_bypass"
    moves = engine.legal_moves(gs)
    assert {m["choice"] for m in moves} == {"besiege", "bypass"}


def test_besiege_places_siege_and_ends_card_435():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    engine.apply_action(gs, {"type": "besiege_bypass", "choice": "besiege"})
    assert gs.locales["melitene"].siege_markers == 1
    assert gs.meta.active_lord != "alp_arslan"  # card ended (4.3.5)


def test_bypass_sets_marker_and_continues_435():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    _activate(gs, "alp_arslan", actions=4)
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    engine.apply_action(gs, {"type": "besiege_bypass", "choice": "bypass"})
    assert gs.locales["melitene"].bypass and aa.bypassed
    assert gs.meta.active_lord == "alp_arslan"  # still active (actions remain)


def test_approach_enemy_lord_triggers_response_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"  # Roman defender
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    assert r.get("pending") == "approach_response"
    assert "chatatourios" in r["defenders"]


def test_approach_avoid_moves_defender_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"
    ch.assets.loot = 0; ch.assets.provender = 0  # Unladen so it may Avoid
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    # Melitene neighbors include Germanikeia (Roman, no enemy) -> a legal Avoid.
    engine.apply_action(gs, {"type": "respond_approach", "choices": {"chatatourios": {"action": "avoid", "to": "germanikeia"}}})
    assert ch.cylinder == "germanikeia" and ch.moved_fought


def test_approach_withdraw_into_friendly_stronghold_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"  # Roman friendly town
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    engine.apply_action(gs, {"type": "respond_approach", "choices": {"chatatourios": {"action": "withdraw"}}})
    assert ch.besieged and ch.cylinder == "melitene"


def test_approach_stand_triggers_battle_pending_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "respond_approach", "choices": {"chatatourios": {"action": "stand"}}})
    assert r.get("pending") == "battle"
    assert any(p["type"] == "battle" for p in gs.meta.pending)


def test_group_march_moves_commander_and_co_located_431():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]  # Commander at Ani
    ar = gs.lords["arisighi"]; ar.cylinder = "ani"  # co-locate
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "mempet", "way_type": "road", "group": ["arisighi"]})
    assert aa.cylinder == "mempet" and ar.cylinder == "mempet"


def test_avoid_blocked_when_laden_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"
    ch.assets.loot = 2  # Laden -> cannot Avoid
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "respond_approach", "choices": {"chatatourios": {"action": "avoid", "to": "germanikeia"}}})
