"""SEL2-02: owner-selected excess Capabilities before Campaign Planning."""
from __future__ import annotations

from itertools import combinations

import pytest

from seljuk import engine
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.routing import decision_side
from seljuk.state import GameState, IllegalAction
from tests.test_cross_game_combat import place
from tests.test_cross_game_lifecycle import clean_position, take_card


def position(*, seljuk=(), roman=()):
    state = clean_position()
    for side, cards in (("seljuk", seljuk), ("roman", roman)):
        decks = state.side_decks(side)
        for card in cards:
            decks.draw_deck.remove(card)
            decks.capabilities_in_play.append(card)
    state.meta.phase = "levy"
    state.meta.subphase = "levy.call_to_arms"
    state.meta.active_player = "roman"
    state.meta.levy_step_passed = {"seljuk": True}
    return state


def begin(state):
    LLMSession(state).apply({"type": "pass_step"})


def discard(state, side, card):
    return engine.apply_action(state, {"type": "capability_discard", "side": side, "card": card})


@pytest.mark.parametrize("kept", ["R4", "R12"])
def test_public_levy_transition_preserves_both_elections_instead_of_popping_last(kept):
    state = position(roman=["R4", "R12"])
    begin(state)
    assert state.meta.phase == "campaign" and state.meta.subphase == "campaign.capability_discard"
    assert state.roman.capabilities_in_play == ["R4", "R12"]
    assert decision_side(state) == "roman"
    assert {m["card"] for m in engine.legal_moves(state)} == {"R4", "R12"}
    discarded = "R12" if kept == "R4" else "R4"
    discard(state, "roman", discarded)
    assert state.roman.capabilities_in_play == [kept]
    assert state.roman.draw_deck.count(discarded) == 1
    assert state.meta.subphase == "campaign.plan" and decision_side(state) == "seljuk"


def test_seljuk_finishes_all_choices_then_roman_before_either_can_plan():
    state = position(seljuk=["S8", "S9", "S23"], roman=["R4", "R12"])
    begin(state)
    for card in ["S8", "S9"]:
        assert decision_side(state) == "seljuk"
        assert {m["type"] for m in engine.legal_moves(state)} == {"capability_discard"}
        discard(state, "seljuk", card)
    assert decision_side(state) == "roman" and state.seljuk.capabilities_in_play == ["S23"]
    discard(state, "roman", "R4")
    assert state.roman.capabilities_in_play == ["R12"]
    assert state.meta.pending == [] and state.meta.subphase == "campaign.plan"
    assert {m["type"] for m in engine.legal_moves(state)} == {"build_plan"}
    engine.apply_action(state, {"type": "build_plan", "side": "seljuk",
                               "cards": ["alp_arslan"] * 2 + ["no_command"] * 5})
    assert decision_side(state) == "roman"


@pytest.mark.parametrize("kept", list(combinations(["R4", "R12", "R16", "R25"], 2)))
def test_every_legal_retained_subset_is_reachable_and_menu_choices_all_validate(kept):
    cards = ["R4", "R12", "R16", "R25"]
    state = position(roman=cards)
    place(state, "chatatourios", "larisa")
    begin(state)
    for card in [card for card in cards if card not in kept]:
        offered, dropped = engine.validated_legal_moves(state)
        assert not dropped and {m["card"] for m in offered} == set(state.roman.capabilities_in_play)
        assert all(m["_remaining"] == len(state.roman.capabilities_in_play) - 2 for m in offered)
        discard(state, "roman", card)
    assert set(state.roman.capabilities_in_play) == set(kept)
    assert state.meta.subphase == "campaign.plan"


@pytest.mark.parametrize("side", ["seljuk", "roman"])
def test_no_excess_does_not_create_a_discard_window_or_count_this_lord_cards(side):
    card = "S8" if side == "seljuk" else "R4"
    state = position(**{side: [card]})
    lord = state.lords["alp_arslan" if side == "seljuk" else "romanos_diogenes"]
    take_card(state, lord, "S20" if side == "seljuk" else "R2")
    begin(state)
    assert state.meta.subphase == "campaign.plan" and not state.meta.pending
    assert state.side_decks(side).capabilities_in_play == [card]
    assert lord.capabilities == (["S20"] if side == "seljuk" else ["R2"])


@pytest.mark.parametrize("action", [
    {"type": "build_plan", "side": "roman", "cards": ["romanos_diogenes"] * 2 + ["no_command"] * 5},
    {"type": "cmd_pass"}, {"type": "end_activation"},
    {"type": "play_hold_event", "card": "R21", "args": {"locale": "larisa"}},
    {"type": "capability_discard", "side": "seljuk", "card": "S8"},
    {"type": "capability_discard", "side": "roman", "card": "R2"},
    {"type": "capability_discard", "side": "roman", "card": "R21"},
    {"type": "capability_discard", "side": "roman", "card": "R25"},
    {"type": "capability_discard", "side": "roman", "card": None},
    {"type": "capability_discard", "side": "roman", "card": ["R4", "R12"]},
    {"type": "capability_discard", "side": "roman", "card": {"R4": True}},
])
def test_wrong_owner_wrong_card_and_skipped_choices_reject_atomically(action):
    state = position(roman=["R4", "R12"])
    take_card(state, state.lords["romanos_diogenes"], "R2")
    state.roman.draw_deck.remove("R21")
    state.roman.held_events = ["R21"]
    begin(state)
    pending, history, decks = state.meta.pending, state.history, state.roman
    before = state.to_json()
    with pytest.raises(IllegalAction):
        engine.apply_action(state, action)
    assert state.to_json() == before
    assert state.meta.pending is pending and state.history is history and state.roman is decks
    discard(state, "roman", "R4")
    assert state.roman.capabilities_in_play == ["R12"]


def test_partial_discard_survives_reload_and_repeated_phase_initialization():
    state = position(seljuk=["S8", "S9", "S23"])
    begin(state)
    discard(state, "seljuk", "S8")
    restored = GameState.from_json(state.to_json())
    session = LLMSession(restored)
    before = restored.to_json()
    session.ensure_phase_started()
    assert restored.to_json() == before and decision_side(restored) == "seljuk"
    assert len([p for p in restored.meta.pending if p["type"] == "capability_discard"]) == 1
    discard(state, "seljuk", "S9")
    session.apply({"type": "capability_discard", "side": "seljuk", "card": "S9"})
    assert restored.to_json() == state.to_json()


def test_compact_pages_keep_all_choices_stable_ids_expire_and_owner_handoff_is_private(tmp_path):
    state = position(seljuk=["S8", "S9", "S23"], roman=["R4", "R12"])
    begin(state)
    interface = CompactInterface(LLMSession(state))
    first = interface.actions(type="capability_discard", limit=1)
    second = interface.actions(cursor=first["next_cursor"])
    assert second["entries"][0]["action"]["card"] == "S9"
    selection = interface.actions(card="S9")["entries"][0]
    assert selection["id"] == second["entries"][0]["id"]
    detail = interface.details(selection["id"])
    assert detail["help"]["remaining"] == 2
    assert set(detail["help"]["eligible_cards"]) == {"S8", "S9", "S23"}
    path = tmp_path / "discard.json"
    interface.save(path)
    interface = CompactInterface.load(path)
    interface.apply(selection["id"])
    before = interface.gs.to_json()
    with pytest.raises(InterfaceError):
        interface.apply(first["entries"][0]["id"])
    assert interface.gs.to_json() == before
    interface.apply(interface.actions(card="S8")["entries"][0]["id"])
    assert interface.owed == "roman"
    interface.player = "seljuk"
    assert interface.actions()["entries"] == []
    with pytest.raises(InterfaceError):
        interface.apply({"type": "capability_discard", "side": "roman", "card": "R4"},
                        version=interface.version)
    interface.player = "roman"
    interface.apply(interface.actions(card="R4")["entries"][0]["id"])
    assert interface.gs.roman.capabilities_in_play == ["R12"] and interface.owed == "seljuk"


def test_gifts_exchanged_discard_removes_its_coin_pool_but_not_the_seasonal_event():
    state = position(seljuk=["S13", "S23"])
    state.meta.notes.update(gifts_coins=4, gifts_taken={"seljuk": 0, "roman": 0},
                            peace_offering_season=True)
    begin(state)
    discard(state, "seljuk", "S13")
    assert "gifts_coins" not in state.meta.notes and "gifts_taken" not in state.meta.notes
    assert state.meta.notes["peace_offering_season"] is True
    assert state.seljuk.draw_deck.count("S13") == 1


def test_campaign_victory_precedes_discard_when_a_side_has_no_mustered_lords():
    state = position(roman=["R4", "R12"])
    state.lords["romanos_diogenes"].mustered = False
    begin(state)
    assert state.meta.phase == "game_over" and state.meta.notes["winner"] == "seljuk"
    assert state.roman.capabilities_in_play == ["R4", "R12"]
    assert not state.meta.pending and engine.legal_moves(state) == []


def test_finished_quota_cannot_be_used_to_discard_extra_cards():
    state = position(roman=["R4", "R12"])
    begin(state)
    discard(state, "roman", "R4")
    before = state.to_json()
    with pytest.raises(IllegalAction):
        discard(state, "roman", "R12")
    assert state.to_json() == before
