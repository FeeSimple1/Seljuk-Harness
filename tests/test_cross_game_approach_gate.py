"""SEL2-06: raw actions cannot bypass an unresolved March Approach."""
from __future__ import annotations

import pytest

from seljuk import engine
from seljuk.llm import LLMSession
from seljuk.state import GameState, IllegalAction
from tests.test_cross_game_combat import place, position


def approach_position(side="seljuk", phase="campaign"):
    state = position()
    state.meta.calendar_box = 1
    state.meta.phase = phase
    state.meta.subphase = "winter.activation" if phase == "winter" else "campaign.command"
    attacker, defender = (("alp_arslan", "chatatourios") if side == "seljuk"
                          else ("romanos_diogenes", "alp_arslan"))
    state.meta.active_player = side
    state.meta.active_lord = state.meta.active_card = attacker
    state.meta.actions_remaining = 4
    for decks in (state.roman, state.seljuk):
        decks.draw_deck.extend(decks.held_events)
        decks.held_events = []
        decks.command_plan = []
        decks.plan_pointer = 0
    state.side_decks(side).command_plan = [attacker]
    state.side_decks("roman" if side == "seljuk" else "seljuk").command_plan = [defender]
    place(state, attacker, "edessa", provender=1, carts=1)
    place(state, defender, "melitene", provender=1, carts=1)
    action = {"type": "cmd_march", "lord": attacker, "to": "melitene"}
    result = engine.apply_action(state, action)
    assert result["pending"] == "approach_response"
    assert {m["type"] for m in engine.legal_moves(state)} == {"respond_approach"}
    return state, attacker, defender


@pytest.mark.parametrize("side", ["seljuk", "roman"])
@pytest.mark.parametrize("phase", ["campaign", "winter"])
@pytest.mark.parametrize("kind", ["cmd_pass", "end_activation", "cmd_march", "cmd_forage"])
def test_pending_approach_rejects_unrelated_commands_without_any_mutation(side, phase, kind):
    state, attacker, defender = approach_position(side, phase)
    lord, enemy = state.lords[attacker], state.lords[defender]
    pending, history, assets = state.meta.pending, state.history, lord.assets
    before = state.to_json()
    action = {"type": kind, "lord": attacker}
    if kind == "cmd_march":
        action["to"] = "larisa"
    with pytest.raises(IllegalAction, match="approach_response") as error:
        LLMSession(state).apply(action)
    assert error.value.code == "pending_decision"
    assert state.to_json() == before
    assert state.lords[attacker] is lord and state.lords[defender] is enemy
    assert state.meta.pending is pending and state.history is history and lord.assets is assets
    assert lord.cylinder == enemy.cylinder == "melitene"


@pytest.mark.parametrize("choice", ["avoid", "withdraw", "stand"])
def test_real_defender_responses_remain_legal_after_rejected_command_and_save_load(choice):
    state, attacker, defender = approach_position()
    pristine = GameState.from_json(state.to_json())
    with pytest.raises(IllegalAction, match="pending_decision"):
        engine.apply_action(state, {"type": "cmd_pass"})
    reloaded = GameState.from_json(state.to_json())
    selection = {"action": choice}
    if choice == "avoid":
        selection["to"] = "larisa"
    action = {"type": "respond_approach", "choices": {defender: selection}}
    results = [engine.apply_action(board, action) for board in (state, pristine, reloaded)]
    assert results[0] == results[1] == results[2]
    assert state.to_json() == pristine.to_json() == reloaded.to_json()
    assert not any(p["type"] == "approach_response" for p in state.meta.pending)
    if choice == "avoid":
        assert state.lords[defender].cylinder == "larisa"
        assert state.lords[attacker].cylinder == "melitene"
    elif choice == "withdraw":
        assert state.lords[defender].besieged
    else:
        assert "battle" in results[0]


def test_avoid_then_bypass_releases_the_gate_for_the_next_legal_march():
    state, attacker, defender = approach_position()
    engine.apply_action(state, {"type": "respond_approach",
                               "choices": {defender: {"action": "avoid", "to": "larisa"}}})
    assert any(p["type"] == "besiege_or_bypass" for p in state.meta.pending)
    engine.apply_action(state, {"type": "besiege_bypass", "choice": "bypass"})
    assert not state.meta.pending
    result = engine.apply_action(state, {"type": "cmd_march", "lord": attacker, "to": "edessa"})
    assert result["action"] == "cmd_march" and state.lords[attacker].cylinder == "edessa"


def test_approach_battle_still_accepts_held_events_in_the_response_payload():
    state, _, defender = approach_position()
    state.roman.draw_deck.remove("R21")
    state.roman.held_events = ["R21"]
    result = engine.apply_action(state, {
        "type": "respond_approach", "choices": {defender: {"action": "stand"}},
        "battle_events": {"roman": ["R21"]}})
    assert "battle" in result and "R21" not in state.roman.held_events
    assert state.roman.draw_deck.count("R21") == 1
    assert not any(p["type"] == "approach_response" for p in state.meta.pending)
