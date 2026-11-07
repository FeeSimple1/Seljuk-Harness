"""SEL5-02. The owner chooses which pieces the removal Event affects."""

import pytest

from seljuk import engine
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface
from seljuk.state import GameState, IllegalAction, ThemataMarker
from tests.test_cross_game_approach_gate import approach_position
from tests.test_cross_game_combat import place, position


def _hold(state, card):
    decks = state.roman if card.startswith("R") else state.seljuk
    if card in decks.draw_deck:
        decks.draw_deck.remove(card)
    decks.held_events.append(card)


def test_r21_standalone_uses_only_the_selected_units():
    state = position()
    first = place(state, "alp_arslan")
    second = place(state, "afsin_beg")
    own = place(state, "chatatourios")
    distant = place(state, "artuk_beg", "ani")
    for lord in (first, second, own, distant):
        lord.forces["turkic_horse"] = 2
    _hold(state, "R21")
    action = {"type": "play_hold_event", "card": "R21"}
    before = state.to_json()
    for args, error in (
        ({"count": 2}, "turkic_targets_required"),
        ({"targets": [{"lord": distant.id}]}, "bad_turkic_target"),
        ({"targets": [{"lord": first.id}, {"lord": first.id}]}, "bad_turkic_target"),
        ({"targets": [{"lord": first.id, "count": 2}, {"lord": second.id}]}, "bad_turkic_count"),
        ({"targets": [{"lord": first.id, "count": 0}]}, "bad_turkic_target"),
    ):
        with pytest.raises(IllegalAction, match=error):
            engine.apply_action(state, {**action, "args": {"locale": "melitene", **args}})
        assert state.to_json() == before
    result = engine.apply_action(state, {**action, "args": {
        "locale": "melitene", "targets": [{"lord": first.id}, {"lord": second.id}],
    }})
    assert result["turkic_removed"] == 2
    assert [lord.forces["turkic_horse"] for lord in (first, second, own, distant)] == [1, 1, 2, 2]
    assert "R21" not in state.roman.held_events


def test_approach_event_can_target_nonparticipants_without_revealing_their_strength():
    state, attacker, defender = approach_position()
    state.meta.options["hidden_mats"] = True
    screened = place(state, "afsin_beg")
    screened.forces["turkic_horse"] = 3
    own = place(state, "romanos_diogenes")
    own.besieged = True
    own.forces["turkic_horse"] = 2
    _hold(state, "R21")
    ui = CompactInterface(LLMSession(state))
    row = ui.actions(type="respond_approach")["entries"][0]
    info = ui.details(row["id"])["help"]["combat"]["turkic_removal"]
    assert screened.id in info["screened_lords"]
    assert {entry["lord"] for entry in info["visible_targets"]["R21"]} == {own.id}
    saved = GameState.from_json(state.to_json())
    result = engine.apply_action(saved, {
        "type": "respond_approach", "choices": {defender: {"action": "stand"}},
        "battle_events": {"roman": [{"card": "R21", "targets": [{"lord": screened.id}]}]},
        "battle_decisions": {"seljuk": [["concede", True]]},
    })
    assert result["battle"]["rounds"] == 1
    assert saved.lords[screened.id].forces["turkic_horse"] == 2
    assert saved.lords[own.id].forces["turkic_horse"] == 2
    assert saved.lords[attacker].forces.get("turkic_horse", 0) == 0


def test_friendly_turkic_horse_require_an_explicit_declaration_even_when_the_only_target():
    state = position()
    lord = place(state, "chatatourios")
    lord.forces["turkic_horse"] = 1
    state.meta.active_lord = lord.id
    state.meta.active_player = lord.side
    _hold(state, "R21")
    action = {"type": "play_hold_event", "card": "R21", "args": {"locale": "melitene"}}
    before = state.to_json()
    with pytest.raises(IllegalAction, match="turkic_targets_required"):
        engine.apply_action(state, action)
    assert state.to_json() == before
    action["args"]["targets"] = [{"lord": lord.id}]
    assert engine.apply_action(state, action)["turkic_removed"] == 1


def test_both_events_keep_original_marker_indices_and_reject_overlap_atomically():
    state, _, defender = approach_position()
    lord = place(state, "romanos_diogenes")
    lord.besieged = True
    lord.themata_on_mat = [
        ThemataMarker(unit="turkic_horse", home_thema="Iberia"),
        ThemataMarker(unit="turkic_horse", symbols=2, home_thema="Charsianon"),
    ]
    _hold(state, "R21")
    _hold(state, "S21")
    action = {
        "type": "respond_approach", "choices": {defender: {"action": "stand"}},
        "battle_events": {
            "seljuk": [{"card": "S21", "targets": [{"lord": lord.id, "index": 0}]}],
            "roman": [{"card": "R21", "targets": [{"lord": lord.id, "index": 0}]}],
        },
        "battle_decisions": {"seljuk": [["concede", True]]},
    }
    before = state.to_json()
    with pytest.raises(IllegalAction, match="overlap"):
        engine.apply_action(state, action)
    assert state.to_json() == before
    action["battle_events"]["roman"][0]["targets"][0]["index"] = 1
    engine.apply_action(state, action)
    [remaining] = lord.themata_on_mat
    assert remaining.symbols == 2 and remaining.unit_count() == 1
    assert remaining.home_thema == "Charsianon"
    assert state.meta.themata_removed[-1].home_thema == "Iberia"


@pytest.mark.parametrize("entry", ["battle", "sally", "storm"])
def test_r21_disbands_an_empty_lord_before_combat(entry):
    if entry == "battle":
        state, _, victim_id = approach_position(side="roman")
        action = {"type": "respond_approach", "choices": {victim_id: {"action": "stand"}}}
        place(state, "afsin_beg", "ani")  # The Seljuk side remains in the campaign.
        actions_before = state.meta.actions_remaining
    else:
        state = position()
        victim_id = place(state, "alp_arslan").id
        roman = place(state, "chatatourios")
        state.locales["melitene"].siege_markers = 2
        roman.besieged = True
        if entry == "sally":
            state.meta.active_player = "roman"
            state.meta.active_lord = state.meta.active_card = roman.id
        action = {"type": f"cmd_{entry}", "lord": state.meta.active_lord}
    victim = state.lords[victim_id]
    victim.forces = {"turkic_horse": 2}
    _hold(state, "R21")
    result = engine.apply_action(state, {
        **action, "battle_events": {"roman": [{"card": "R21", "targets": [{"lord": victim_id, "count": 2}]}]},
    })
    assert result[entry]["cancelled"] == "no_combatants"
    assert result[entry]["rounds"] == 0 and victim.cylinder == "calendar" and not victim.mustered
    if entry == "battle":
        assert state.meta.actions_remaining == actions_before
    else:
        assert state.locales["melitene"].siege_markers == 0
