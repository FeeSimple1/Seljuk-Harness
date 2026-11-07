"""SEL5-01. A Sortie selects its group before the enemy responds."""

import pytest

from seljuk import engine
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface
from seljuk.rng import roller_for_state
from seljuk.state import GameState, IllegalAction
from tests.test_cross_game_combat import place, position


def _position(lead="afsin_beg"):
    state = position()
    leader = place(state, lead, "ani", loot=3, provender=3)
    leader.forces = {"ghulam_cavalry": 4}
    defender = place(state, "chatatourios", "ani")
    defender.bypassed = state.locales["ani"].bypass = True
    state.meta.active_lord = state.meta.active_card = lead
    state.meta.options["hidden_mats"] = True
    return state, leader, defender


def _sortie(leader, **params):
    return {"type": "cmd_sortie", "lord": leader.id, **params}


def test_ordinary_lord_sorties_alone_and_bypasser_can_avoid_after_reload():
    state, leader, defender = _position()
    ally = place(state, "artuk_beg", "ani")
    before = state.to_json()
    with pytest.raises(IllegalAction, match="Commander"):
        engine.apply_action(state, _sortie(leader, group=[ally.id]))
    assert state.to_json() == before

    rng = roller_for_state(state).get_state()
    assets = leader.assets.model_copy()
    result = engine.apply_action(state, _sortie(leader))
    assert result["cost"] == 1 and result["group"] == [leader.id]
    assert result["pending"] == "approach_response" and "battle" not in result
    assert state.meta.actions_remaining == 1 and roller_for_state(state).get_state() == rng
    assert leader.assets == assets and leader.moved_fought and not ally.moved_fought
    pending = state.meta.pending[0]
    assert pending["attackers"] == [leader.id] and pending["_owed_by"] == "roman"
    before = state.to_json()
    with pytest.raises(IllegalAction, match="approach_response"):
        engine.apply_action(state, {"type": "end_activation"})
    assert state.to_json() == before

    restored = GameState.from_json(before)
    result = engine.apply_action(restored, {
        "type": "respond_approach", "choices": {defender.id: {"action": "avoid", "to": "ararat"}},
    })
    assert result["avoided"] == [defender.id] and "battle" not in result
    assert restored.lords[defender.id].cylinder == "ararat"
    assert not restored.lords[defender.id].bypassed and not restored.locales["ani"].bypass
    assert restored.meta.active_lord == leader.id and restored.meta.actions_remaining == 1


def test_commander_selects_allies_and_leaves_unselected_lords_inside():
    state, leader, defender = _position("alp_arslan")
    selected = place(state, "afsin_beg", "ani")
    staying = place(state, "artuk_beg", "ani")
    selected.besieged = staying.besieged = True  # Withdrew before the Bypass.
    move = next(m for m in engine.legal_moves(state) if m["type"] == "cmd_sortie")
    assert set(move["_co_marchers"]) == {selected.id, staying.id}
    before = state.to_json()
    with pytest.raises(IllegalAction, match="cannot Group-March"):
        engine.apply_action(state, _sortie(leader, group=[defender.id]))
    assert state.to_json() == before
    result = engine.apply_action(state, {**move, "group": [selected.id]})
    assert result["group"] == [leader.id, selected.id]
    assert not selected.besieged and selected.moved_fought
    assert staying.besieged and not staying.moved_fought
    before = state.to_json()
    stand = {"type": "respond_approach", "choices": {defender.id: {"action": "stand"}}}
    with pytest.raises(IllegalAction, match="eligible Besieged Lords"):
        engine.apply_action(state, {**stand, "sally_join": [staying.id]})
    assert state.to_json() == before
    result = engine.apply_action(state, {**stand, "battle_decisions": {"seljuk": [["concede", True]]}})
    assert {entry["lord"] for entry in result["battle"]["ending"]["retreat"]} == {
        leader.id, selected.id,
    }
    assert staying.besieged and not staying.moved_fought


def test_lieutenant_sorties_with_his_lower_lord_only():
    state, leader, _ = _position()
    lower = place(state, "artuk_beg", "ani")
    ally = place(state, "sav_tekin", "ani")
    leader.lower_lord, lower.lieutenant_of = lower.id, leader.id
    move = next(m for m in engine.legal_moves(state) if m["type"] == "cmd_sortie")
    assert move["_required_lower_lord"] == lower.id
    before = state.to_json()
    with pytest.raises(IllegalAction, match="Commander"):
        engine.apply_action(state, {**move, "group": [ally.id]})
    assert state.to_json() == before
    assert engine.apply_action(state, move)["group"] == [leader.id, lower.id]


def test_losing_sortie_can_withdraw_and_keep_bypass():
    state, leader, defender = _position()
    engine.apply_action(state, _sortie(leader))
    result = engine.apply_action(state, {
        "type": "respond_approach", "choices": {defender.id: {"action": "stand"}},
        "battle_decisions": {"seljuk": [["concede", True], ["retreat", "withdraw"]]},
    })
    battle = result["battle"]
    assert battle["conceder"] == "attacker" and battle["winner"] == "defender"
    assert battle["ending"]["retreat"] == [{"lord": leader.id, "fate": "withdraw"}]
    assert leader.besieged and leader.cylinder == defender.cylinder == "ani"
    assert defender.bypassed and state.locales["ani"].bypass


def test_compact_sortie_reveals_only_selected_fighters_after_stand():
    state, leader, defender = _position("alp_arslan")
    ally = place(state, "afsin_beg", "ani")
    staying = place(state, "artuk_beg", "ani")
    staying.besieged = True
    ui = CompactInterface(LLMSession(state))
    row = ui.actions(type="cmd_sortie")["entries"][0]
    ui.apply(row["id"], parameters={"group": [ally.id]})
    assert ui.owed == "roman"
    assert ui.session.state("roman")["lords"][leader.id]["forces"] == "<hidden>"
    ui.apply({"type": "respond_approach", "choices": {defender.id: {"action": "stand"}}},
             version=ui.version)
    assert ui.owed == "seljuk"
    roman_view = ui.session.state("roman")["lords"]
    assert roman_view[leader.id]["forces"] == leader.forces
    assert roman_view[ally.id]["forces"] == ally.forces
    assert roman_view[staying.id]["forces"] == "<hidden>"
    ui.apply({"type": "decline_inputs"}, version=ui.version)
    assert ui.owed == "roman"
    assert ui.session.state("roman")["lords"][staying.id]["forces"] == "<hidden>"
    result = ui.apply({"type": "decline_inputs"}, version=ui.version)
    assert result["applied"] == "respond_approach"
    assert not state._revealed_combat_lords
