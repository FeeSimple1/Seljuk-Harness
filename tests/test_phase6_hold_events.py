"""Phase 6 (R4): Hold-Event play hooks."""
import pytest

from seljuk import scenarios as S, engine, battle
from seljuk.actions import reset_muster_segment, lordship_remaining
from seljuk.state import IllegalAction


def _muster(gs, side):
    engine.start_levy(gs)
    gs.meta.subphase = "levy.muster"; gs.meta.active_player = side; gs.meta.levy_step_passed = {}
    reset_muster_segment(gs)


def test_michael_attaleiates_grants_romanos_lordship_r6():
    gs = S.load_scenario("emperor_and_the_lion"); _muster(gs, "roman")
    gs.roman.held_events = ["R6"]
    base = lordship_remaining(gs, gs.lords["romanos_diogenes"])
    engine.apply_action(gs, {"type": "play_hold_event", "card": "R6", "args": {}})
    assert lordship_remaining(gs, gs.lords["romanos_diogenes"]) == base + 1


def test_eastern_rebellions_grants_alp_arslan_lordship_s10():
    gs = S.load_scenario("emperor_and_the_lion"); _muster(gs, "seljuk")
    gs.seljuk.held_events = ["S10"]
    base = lordship_remaining(gs, gs.lords["alp_arslan"])
    engine.apply_action(gs, {"type": "play_hold_event", "card": "S10", "args": {}})
    assert lordship_remaining(gs, gs.lords["alp_arslan"]) == base + 1


def test_sultans_horse_removes_a_siege_r4():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "tephrike"
    gs.locales["tephrike"].siege_markers = 3
    gs.roman.held_events = ["R4"]
    engine.apply_action(gs, {"type": "play_hold_event", "card": "R4", "args": {}})
    assert gs.locales["tephrike"].siege_markers == 2


def test_nomadic_tribes_removes_turkic_r21():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "ani"; aa.forces = {"turkic_horse": 4}
    gs.roman.held_events = ["R21"]
    r = engine.apply_action(gs, {"type": "play_hold_event", "card": "R21", "args": {"locale": "ani", "count": 2}})
    assert r["turkic_removed"] == 2 and gs.lords["alp_arslan"].forces["turkic_horse"] == 2


def test_bad_omens_reorders_roman_plan_s24():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.seljuk.held_events = ["S24"]
    gs.roman.command_plan = ["chatatourios", "romanos_diogenes", "no_command"]
    gs.roman.plan_pointer = 0
    engine.apply_action(gs, {"type": "play_hold_event", "card": "S24", "args": {}})
    assert gs.roman.command_plan[:2] == ["romanos_diogenes", "chatatourios"]


def test_summer_heat_sets_command_one_r3():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 2  # Summer
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_lord = "alp_arslan"; gs.meta.active_card = "alp_arslan"; gs.meta.actions_remaining = 4
    gs.roman.held_events = ["R3"]
    engine.apply_action(gs, {"type": "play_hold_event", "card": "R3", "args": {}})
    assert gs.meta.actions_remaining == 1


def test_kleisourai_hits_moving_seljuk_r23():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.forces = {"turkic_horse": 4}
    gs.roman.held_events = ["R23"]
    r = engine.apply_action(gs, {"type": "play_hold_event", "card": "R23", "args": {"lord": "alp_arslan", "unit": "turkic_horse"}})
    assert r.get("eliminated") == "turkic_horse" or r.get("protected") == "turkic_horse"


def test_play_hold_event_rejects_card_not_held():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.roman.held_events = []
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "play_hold_event", "card": "R4", "args": {}})


def test_battle_event_mountain_ambush_consumed():
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "chaldia"; aa.forces = {"turkic_horse": 6}  # Chaldia is Pass-adjacent
    ch = gs.lords["chatatourios"]; ch.cylinder = "chaldia"; ch.forces = {"infantry": 2}
    gs.seljuk.held_events = ["S2"]
    gs.meta.phase = "campaign"; gs.meta.active_lord = "alp_arslan"
    res = battle.begin_battle(gs, ["alp_arslan"], ["chatatourios"], "chaldia",
                              events={"seljuk": ["S2"]})
    assert "S2" not in gs.seljuk.held_events  # Mountain Ambush consumed
    assert res["winner"] in ("attacker", "defender")


def test_battle_event_betrayal_consumed_s3():
    gs = S.load_scenario("emperor_and_the_lion", seed=4)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "melitene"; aa.forces = {"turkic_horse": 6}
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"; ch.forces = {"tagmata": 2, "infantry": 2}
    gs.seljuk.held_events = ["S3"]
    gs.meta.phase = "campaign"; gs.meta.active_lord = "alp_arslan"
    battle.begin_battle(gs, ["alp_arslan"], ["chatatourios"], "melitene", events={"seljuk": ["S3"]})
    assert "S3" not in gs.seljuk.held_events and "S3" in gs.meta.asterisks_used
