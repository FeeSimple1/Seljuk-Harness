"""Phase 6 (R5/R6): Relief Sally (4.8.1) + combat-aggressive self-play."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from seljuk import battle, scenarios as S, engine
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.state import GameState, IllegalAction
from strategic_agent import play_game as strategic_play  # noqa: E402
from tests.test_cross_game_combat import place, position


SALLIERS = ["nikephoros_bryennios", "chatatourios"]


def relief_approach():
    gs = position()
    gs.meta.active_player = "roman"
    gs.meta.active_lord = gs.meta.active_card = "romanos_diogenes"
    active = place(gs, "romanos_diogenes", "laodikeia")
    active.forces = {"tagmata": 4}
    enemy = place(gs, "alp_arslan", "antioch")
    enemy.forces = {"infantry": 8}
    for lid in SALLIERS:
        inside = place(gs, lid, "antioch", provender=1)
        inside.besieged = True
        inside.forces = {"infantry": 4}
    gs.locales["antioch"].siege_markers = 2
    engine.apply_action(gs, {"type": "cmd_march", "lord": active.id, "to": "antioch"})
    action = {"type": "respond_approach", "choices": {enemy.id: {"action": "stand"}}}
    return gs, action


@pytest.mark.parametrize("joined", [[], SALLIERS[:1], SALLIERS[1:], SALLIERS[::-1]])
def test_relief_sally_accepts_any_subset_and_only_joiners_affect_siege(joined):
    gs, action = relief_approach()
    candidates = engine.legal_moves(gs)[0].get("_sally_join")
    result = engine.apply_action(gs, {
        **action, "sally_join": joined, "battle_decisions": {"roman": [["concede", True]]},
    })["battle"]
    assert result["winner"] == "defender"
    assert result["relief_sally"] == [lid for lid in SALLIERS if lid in joined]
    assert {entry["lord"] for entry in result["ending"]["retreat"] if entry["fate"] == "withdraw"} == set(joined)
    assert {step["choice"] for step in result["decisions"] if step["type"] == "sally_placement"} == set(joined)
    assert candidates == SALLIERS
    assert gs.locales["antioch"].siege_markers == (1 if joined else 2)
    for lid in SALLIERS:
        lord = gs.lords[lid]
        assert lord.besieged and lord.cylinder == "antioch"
        assert lord.service_box == 10
        assert lord.assets.provender == (0 if lid in joined else 1)  # Feed after Battle


@pytest.mark.parametrize("bad_selection", [
    None, "chatatourios", ["chatatourios", "chatatourios"], ["alp_arslan"],
    ["romanos_diogenes"], ["manuel_komnenos"], [["chatatourios"]],
])
def test_illegal_relief_sally_selection_rejects_without_mutating_state(bad_selection):
    gs, action = relief_approach()
    away = place(gs, "manuel_komnenos", "mopsuestia")
    away.besieged = True
    before = gs.to_json()
    with pytest.raises(IllegalAction) as error:
        engine.apply_action(gs, {**action, "sally_join": bad_selection})
    assert error.value.code == "bad_sally_join"
    assert gs.to_json() == before


@pytest.mark.parametrize("pair", [SALLIERS, SALLIERS[::-1]])
def test_relief_sally_pair_joins_together_alongside_independent_lords(pair):
    gs, action = relief_approach()
    upper, lower = pair
    # Stage an intact pair formed during Planning.
    gs.lords[upper].lower_lord = lower
    gs.lords[lower].lieutenant_of = upper
    independent = place(gs, "manuel_komnenos", "antioch", provender=1)
    independent.besieged = True
    before = gs.to_json()
    move = {**action, "battle_decisions": {"roman": [["concede", True]]}}
    for selected in ([upper], [lower, independent.id]):
        with pytest.raises(IllegalAction, match="split_stack"):
            engine.apply_action(gs, {**move, "sally_join": selected})
        assert gs.to_json() == before

    for selected in ([], pair, [independent.id], [*pair, independent.id]):
        restored = GameState.from_json(before)
        result = engine.apply_action(restored, {**move, "sally_join": selected})
        assert set(result["battle"]["relief_sally"]) == set(selected)
        for lid in (*pair, independent.id):
            assert restored.lords[lid].assets.provender == (0 if lid in selected else 1)

    survivor = GameState.from_json(before)
    battle._remove_by_combat(survivor, survivor.lords[lower])
    assert survivor.lords[upper].lower_lord is None
    result = engine.apply_action(survivor, {**move, "sally_join": [upper]})
    assert result["battle"]["relief_sally"] == [upper]


def test_compact_relief_sally_exposes_pair_and_rejects_split_after_reload(tmp_path):
    gs, action = relief_approach()
    upper, lower = SALLIERS
    gs.lords[upper].lower_lord = lower
    gs.lords[lower].lieutenant_of = upper
    ui = CompactInterface(LLMSession(gs))
    ui.apply(action, version=ui.version)
    assert ui.owed == "roman"
    saved = tmp_path / "relief-pair.json"
    ui.save(saved)
    ui = CompactInterface.load(saved)
    version = ui.version
    before = ui.gs.to_json()
    row = ui.actions(type="supply_inputs")["entries"][0]
    with pytest.raises(IllegalAction, match="split_stack"):
        ui.apply(row["id"], parameters={"inputs": {"sally_join": [upper]}})
    assert ui.version == version and ui.gs.to_json() == before and ui.owed == "roman"
    help_ = ui.details(row["id"])["help"]["sally_join"]
    assert help_["lieutenant_pairs"] == [SALLIERS]
    result = ui.apply(row["id"], parameters={"inputs": {
        "sally_join": SALLIERS, "battle_decisions": [["concede", True]],
    }})
    assert result["outcome"]["battle"]["relief_sally"] == SALLIERS


def test_compact_relief_sally_only_approaching_player_chooses_and_can_resume(tmp_path):
    gs, action = relief_approach()
    ui = CompactInterface(LLMSession(gs))
    before = gs.to_json()
    row = ui.actions()["entries"][0]
    assert "sally_join" not in ui.details(row["id"])["help"]["parameters"]
    with pytest.raises(InterfaceError, match="Approaching player chooses"):
        ui.apply({**action, "sally_join": []}, version=ui.version)
    assert ui.owed == "seljuk"
    ui.apply(row["id"], parameters={"choices": action["choices"]})
    assert ui.owed == "roman" and gs.to_json() == before
    row = ui.actions(type="supply_inputs")["entries"][0]
    assert ui.details(row["id"])["help"]["sally_join"]["eligible_lords"] == SALLIERS
    saved = tmp_path / "relief.json"
    ui.save(saved)
    ui = CompactInterface.load(saved)
    assert ui.owed == "roman" and ui.gs.to_json() == before
    result = ui.apply(row["id"], parameters={"inputs": {
        "sally_join": [], "battle_decisions": [["concede", True]],
    }})
    assert result["outcome"]["battle"]["relief_sally"] == []
    assert ui.gs.locales["antioch"].siege_markers == 2
    assert all(not ui.gs.lords[lid].moved_fought for lid in SALLIERS)


@pytest.mark.parametrize("timing", ["no_battle", "before_scouts_response", "after_scouts_response"])
def test_compact_relief_sally_is_conditional_on_local_scouts_creating_battle(timing):
    gs, action = relief_approach()
    gs.roman.draw_deck.remove("R18")
    gs.roman.held_events.append("R18")
    action["choices"]["alp_arslan"] = {"action": "avoid", "to": "artah"}
    ui = CompactInterface(LLMSession(gs))
    ui.apply(action, version=ui.version)
    scouts = timing != "no_battle"
    inputs = {"play_local_scouts": scouts, "battle_decisions": [["concede", True]]}
    if timing != "after_scouts_response":
        inputs["sally_join"] = SALLIERS[:1]
    choice = {"type": "supply_inputs", "inputs": inputs}
    if scouts:
        version = ui.version
        with pytest.raises(IllegalAction, match="bad_sally_join"):
            ui.apply({**choice, "inputs": {**inputs, "sally_join": ["alp_arslan"]}}, version=version)
        assert ui.version == version and ui.owed == "roman"
        response = ui.apply(choice, version=version)
        assert ui.owed == "seljuk"
        assert "sally_join" not in response["pending"]["committed_action"]
        assert ui.gs.to_json() == gs.to_json()
        scout_response = {"lord": "alp_arslan", "action": "stand"}
        final = ui.apply({"type": "supply_inputs", "inputs": {"local_scouts": scout_response}},
                         version=ui.version)
        if timing == "after_scouts_response":
            assert ui.owed == "roman" and ui.gs.to_json() == gs.to_json()
            assert final["pending"]["committed_action"]["local_scouts"] == scout_response
            row = ui.actions(type="supply_inputs")["entries"][0]
            assert ui.details(row["id"])["help"]["parameters"] == ["sally_join"]
            final = ui.apply(row["id"], parameters={"inputs": {"sally_join": SALLIERS[:1]}})
        assert final["outcome"]["battle"]["relief_sally"] == SALLIERS[:1]
        assert ui.gs.locales["antioch"].siege_markers == 1
    else:
        final = ui.apply(choice, version=ui.version)
        assert final["outcome"]["avoided"] == ["alp_arslan"]
        assert ui.gs.locales["antioch"].siege_markers == 0
        assert all(not ui.gs.lords[lid].moved_fought for lid in SALLIERS)


def test_relief_sally_besieged_lord_joins_attack_481():
    gs = S.load_scenario("emperor_and_the_lion", seed=2)
    ch = gs.lords["chatatourios"]; ch.cylinder = "antioch"; ch.besieged = True
    ch.forces = {"tagmata": 2, "infantry": 2}
    aa = gs.lords["alp_arslan"]; aa.cylinder = "antioch"; aa.forces = {"turkic_horse": 2}
    gs.locales["antioch"].siege_markers = 2
    rom = gs.lords["romanos_diogenes"]; rom.cylinder = "laodikeia"
    rom.forces = {"tagmata": 2, "infantry": 1, "turkic_horse": 2}
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = "roman"
    gs.meta.active_lord = "romanos_diogenes"; gs.meta.active_card = "romanos_diogenes"; gs.meta.actions_remaining = 4
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1
    engine.apply_action(gs, {"type": "cmd_march", "lord": "romanos_diogenes", "to": "antioch", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "respond_approach", "choices": {"alp_arslan": {"action": "stand"}}})
    assert r["battle"].get("relief_sally") == ["chatatourios"]  # besieged Roman joined the relief Attack


def test_relief_sally_loss_reduces_siege_to_one_481():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    ch = gs.lords["chatatourios"]; ch.cylinder = "antioch"; ch.besieged = True; ch.forces = {"militia": 1}
    aa = gs.lords["alp_arslan"]; aa.cylinder = "antioch"; aa.forces = {"turkic_horse": 6, "ghulam_cavalry": 2}
    gs.locales["antioch"].siege_markers = 3
    rom = gs.lords["romanos_diogenes"]; rom.cylinder = "laodikeia"; rom.forces = {"militia": 1}  # weak relief
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = "roman"
    gs.meta.active_lord = "romanos_diogenes"; gs.meta.active_card = "romanos_diogenes"; gs.meta.actions_remaining = 4
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1
    engine.apply_action(gs, {"type": "cmd_march", "lord": "romanos_diogenes", "to": "antioch", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "respond_approach", "choices": {"alp_arslan": {"action": "stand"}}})
    if r["battle"]["winner"] == "defender":
        assert gs.locales["antioch"].siege_markers == 1


@pytest.mark.parametrize("scenario", S.SCENARIOS)
def test_strategic_agent_reaches_terminal(scenario):
    res = strategic_play(scenario, seed=1)
    assert res["over"] is True
    assert res["winner"] in ("roman", "seljuk", "draw")
