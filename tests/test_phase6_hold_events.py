"""Phase 6 (R4): Hold-Event play hooks."""
import pytest

from seljuk import actions, scenarios as S, engine, battle
from seljuk.actions import reset_muster_segment, lordship_remaining
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction
from tests.test_cross_game_combat import position
from tests.test_decisions_d008_sally import _cmd, _muster_siege_lord


def _muster(gs, side):
    engine.start_levy(gs)
    gs.meta.pending = []  # Isolate this subsystem; opening choices have dedicated tests.
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
    gs.roman.held_events = ["R3"]
    # Open the real enemy-reveal response window rather than bypass its timing.
    from seljuk import campaign
    gs.meta.active_player = "seljuk"
    gs.seljuk.command_plan = ["alp_arslan"]
    gs.seljuk.plan_pointer = 0
    campaign._reveal_next(gs)
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


def _betrayal_position(seed):
    gs = position()
    gs.meta.rng_state = DiceRoller(seed).get_state()
    _cmd(gs, "alp_arslan", "seljuk")
    gs.seljuk.draw_deck.remove("S3")
    gs.seljuk.held_events.append("S3")
    return gs


def _betrayal_sally(*besiegers):
    gs = _betrayal_position(seed=1)
    _muster_siege_lord(gs, "alp_arslan", inside=True)
    for lid in besiegers:
        _muster_siege_lord(gs, lid)
    melitene = gs.locales["melitene"]
    melitene.conquered_side = "seljuk"
    melitene.conquered_count = battle._eff_value(gs, "melitene")
    melitene.siege_markers = 2
    return gs


def test_sally_betrayal_keeps_card_and_strikes_against_a_single_enemy():
    action = {"type": "cmd_sally", "lord": "alp_arslan",
              "battle_decisions": {"seljuk": [["concede", False], ["concede", False], ["concede", True]]}}
    control = engine.apply_action(_betrayal_sally("chatatourios"), action)["sally"]
    gs = _betrayal_sally("chatatourios")
    result = engine.apply_action(gs, {**action, "battle_events": {"seljuk": ["S3"]}})["sally"]

    assert any(strike["round"] == 2 for strike in control["strikes"])
    assert result == control
    assert "S3" in gs.seljuk.held_events
    assert "S3" not in gs.seljuk.draw_deck and "S3" not in gs.meta.asterisks_used


@pytest.mark.parametrize("target", ["andronikos_doukas", "chatatourios"])
def test_march_battle_betrayal_moves_the_named_lord(target):
    gs = _betrayal_position(seed=2)
    # Preserve the Missile exchange that keeps both targets eligible in Round 2.
    gs.roman.draw_deck.remove("R25")
    gs.roman.capabilities_in_play.append("R25")
    for lid in ("alp_arslan", "artuk_beg"):
        _muster_siege_lord(gs, lid).cylinder = "laodikeia"
    defenders = {"andronikos_doukas", "chatatourios"}
    for lid in sorted(defenders):
        _muster_siege_lord(gs, lid).cylinder = "antioch"
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "antioch", "group": ["artuk_beg"]})
    result = engine.apply_action(gs, {
        "type": "respond_approach", "choices": {lid: {"action": "stand"} for lid in defenders},
        "battle_events": {"seljuk": [{"card": "S3", "lord": target}]},
        "battle_decisions": {"seljuk": [["concede", False], ["concede", False], ["concede", True]]},
    })["battle"]

    move, = [decision for decision in result["decisions"] if decision["type"] == "betrayal_target"]
    assert move["round"] == 2 and move["choice"] == target and set(move["options"]) == defenders
    assert {strike["target"] for strike in result["strikes"]
            if strike["round"] == 2 and strike["by"] == "attacker"} == defenders - {target}
    assert "S3" not in gs.seljuk.held_events and gs.seljuk.draw_deck.count("S3") == 1
    assert gs.meta.asterisks_used.count("S3") == 1


@pytest.mark.parametrize("front, target, advance, used, applies", [
    ("andronikos_doukas", "chatatourios", False, False, False),
    ("romanos_diogenes", "chatatourios", True, False, True),
    ("romanos_diogenes", "romanos_diogenes", True, False, False),
    ("romanos_diogenes", "chatatourios", True, True, False),
])
def test_compact_sally_betrayal_respects_front_commander_and_once_per_game(front, target, advance, used, applies):
    gs = _betrayal_sally(front, "chatatourios")
    if used:
        gs.meta.asterisks_used.append("S3")  # Older saves could hold a spent S3.
    ui = CompactInterface(LLMSession(gs))
    sally, = ui.actions(type="cmd_sally")["entries"]
    assert ("betrayal" in ui.details(sally["id"])["help"]["combat"]) == (not used)
    ui.apply(sally["id"], parameters={
        "battle_events": {"seljuk": [{"card": "S3", "lord": target}]},
        "battle_decisions": [["concede", False], ["concede", True]],
    })
    assert ui.viewer == "roman"
    reply, = ui.actions(type="supply_inputs")["entries"]
    assert "betrayal" not in ui.details(reply["id"])["help"]
    ui.apply(reply["id"], parameters={"inputs": {"battle_decisions": [
        ["initial_placement_defender", front],
        ["reserve_advance", "chatatourios" if advance else None],
    ]}})
    gs = ui.gs
    result = gs.history[-1]["result"]["sally"]

    moves = [decision for decision in result["decisions"] if decision["type"] == "betrayal_target"]
    if applies:
        move, = moves
        assert move["options"] == ["chatatourios"] and move["choice"] == target
    else:
        assert moves == []
    assert ("S3" in gs.seljuk.held_events) == (not applies)
    assert ("S3" in gs.meta.asterisks_used) == (used or applies)


def test_redrawn_betrayal_after_use_is_no_event():
    gs = _betrayal_position(seed=1)
    gs.seljuk.held_events.remove("S3")
    gs.meta.asterisks_used.append("S3")

    actions._classify_drawn_event(gs, "seljuk", "S3")

    assert "S3" not in gs.seljuk.held_events and gs.seljuk.draw_deck.count("S3") == 1
    assert gs.meta.pending == []
