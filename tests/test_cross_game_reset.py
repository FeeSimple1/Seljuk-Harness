"""SEL2-04: optional owner-controlled Arts of War discards at Reset."""
from __future__ import annotations

from itertools import combinations

import pytest

from seljuk import engine
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.routing import decision_side
from seljuk.state import Assets, IllegalAction
from tests.reset_helpers import keep_reset_cards
from tests.test_cross_game_avoid_wastage import begin_end
from tests.test_cross_game_lifecycle import (
    clean_position,
    special_position,
    take_card,
    thema_position,
)


def put(state, side, card, zone):
    decks = state.side_decks(side)
    decks.draw_deck.remove(card)
    getattr(decks, zone).append(card)


def position(*, both=True, box=1):
    state = clean_position()
    state.meta.calendar_box = box
    for locale in state.locales.values():
        locale.ravaged_side = None
    put(state, "seljuk", "S21", "held_events")
    put(state, "seljuk", "S8", "capabilities_in_play")
    take_card(state, state.lords["alp_arslan"], "S25")
    if both:
        put(state, "roman", "R21", "held_events")
        put(state, "roman", "R12", "capabilities_in_play")
        take_card(state, state.lords["romanos_diogenes"], "R3")
    return state


def discard(state, side, card, **extra):
    return engine.apply_action(state, {"type": "reset_discard", "side": side, "card": card, **extra})


SUBSETS = [subset for size in range(4) for subset in combinations(["S21", "S8", "S25"], size)]


@pytest.mark.parametrize("selected", SUBSETS)
def test_any_subset_of_held_side_and_lord_cards_can_be_returned_or_kept(selected):
    state = position()
    begin_end(state)
    assert state.meta.subphase == "campaign.reset_discard" and decision_side(state) == "seljuk"
    for card in selected:
        moves, dropped = engine.validated_legal_moves(state)
        assert not dropped
        assert {m["card"] for m in moves if m["type"] == "reset_discard"} == {
            "S21", "S8", "S25"} - set(selected[:selected.index(card)])
        discard(state, "seljuk", card)
    if decision_side(state) == "seljuk":
        engine.apply_action(state, {"type": "reset_done", "side": "seljuk"})
    assert decision_side(state) == "roman"
    assert state.roman.held_events == ["R21"] and state.roman.capabilities_in_play == ["R12"]
    assert state.lords["romanos_diogenes"].capabilities == ["R3"]
    keep_reset_cards(state)
    assert ("S21" in state.seljuk.held_events) == ("S21" not in selected)
    assert ("S8" in state.seljuk.capabilities_in_play) == ("S8" not in selected)
    assert ("S25" in state.lords["alp_arslan"].capabilities) == ("S25" not in selected)
    assert all(state.seljuk.draw_deck.count(card) == int(card in selected) for card in ["S21", "S8", "S25"])
    assert state.meta.phase == "levy" and state.meta.calendar_box == 2


def test_mandatory_cleanup_precedes_optional_elections_and_returns_cards_once():
    state = position()
    put(state, "seljuk", "S13", "capabilities_in_play")
    state.seljuk.this_campaign_events = ["S13"]
    put(state, "seljuk", "S17", "this_campaign_events")
    state.meta.notes.update(gifts_coins=3, peace_offering_season=True, weather_plan9=True)
    begin_end(state)
    assert not state.seljuk.this_campaign_events
    assert all(state.seljuk.draw_deck.count(card) == 1 for card in ["S13", "S17"])
    assert not any(key in state.meta.notes for key in ["gifts_coins", "peace_offering_season", "weather_plan9"])
    assert not {"S13", "S17"} & {m.get("card") for m in engine.legal_moves(state)}
    keep_reset_cards(state)
    assert all(state.seljuk.draw_deck.count(card) == 1 for card in ["S13", "S17"])


@pytest.mark.parametrize("card", ["R2", "R7", "R17", "S20"])
def test_reset_special_vassal_discard_removes_contingent_and_optional_service(card):
    state, lord, vassal = special_position(card, optional=True)
    lord.assets = Assets()  # no Wastage: elect this singleton card at Reset
    begin_end(state)
    assert {m.get("card") for m in engine.legal_moves(state) if m["type"] == "reset_discard"} == {card}
    result = discard(state, lord.side, card, lord=lord.id)
    assert result["special_vassals_disbanded"]
    assert lord.mustered and lord.forces == {"infantry": 1}
    assert vassal not in lord.vassals and vassal.service_box is None and not vassal.levied
    assert card not in lord.capabilities
    assert state.side_decks(lord.side).draw_deck.count(card) == 1
    assert state.meta.phase == "levy"


@pytest.mark.parametrize("card", ["R2", "S20"])
def test_discarding_the_last_force_disbands_and_ends_campaign_before_other_owner(card):
    state, lord, _ = special_position(card)
    lord.assets = Assets()
    lord.forces.pop("infantry")
    other = "seljuk" if lord.side == "roman" else "roman"
    put(state, other, "S21" if other == "seljuk" else "R21", "held_events")
    begin_end(state)
    if decision_side(state) != lord.side:
        engine.apply_action(state, {"type": "reset_done", "side": other})
    result = discard(state, lord.side, card)
    assert result["disbanded"] == lord.id and not lord.mustered
    assert lord.cylinder == "calendar" and lord.cylinder_calendar_box == result["calendar_box"]
    assert state.meta.phase == "game_over" and state.meta.notes["winner"] == other
    assert state.meta.calendar_box == 1 and state.meta.pending == []


def test_pressed_levy_retention_is_not_repeated_after_discarding_r4():
    state, lord, marker = thema_position(free=True)
    begin_end(state)
    engine.apply_action(state, {"type": "retain_themata", "lord": lord.id,
                               "thema": "Boukellarion", "mode": "pressed_levy"})
    assert state.meta.subphase == "campaign.reset_discard"
    discard(state, "roman", "R4")
    assert lord.mustered and lord.themata_on_mat == [marker]
    assert state.meta.phase == "levy" and marker.home_thema == "Boukellarion"


@pytest.mark.parametrize("keep", [False, True])
def test_optional_discard_precedes_winter_and_can_keep_or_return_a_winter_hold(keep):
    state = clean_position()
    state.meta.calendar_box = 3
    put(state, "roman", "R9", "held_events")
    begin_end(state)
    assert state.meta.phase == "campaign" and state.meta.subphase == "campaign.reset_discard"
    if keep:
        engine.apply_action(state, {"type": "reset_done", "side": "roman"})
        assert state.meta.phase == "winter" and state.meta.subphase == "winter.activation"
        assert "R9" in state.roman.held_events
    else:
        discard(state, "roman", "R9")
        assert "R9" not in state.roman.held_events and state.roman.draw_deck.count("R9") == 1
        assert state.meta.subphase != "winter.activation"
        while any(p["type"] == "winter_quarters" for p in state.meta.pending):
            engine.apply_action(state, engine.legal_moves(state)[0])
        assert state.meta.phase == "levy" and state.meta.calendar_box == 4


@pytest.mark.parametrize("action", [
    {"type": "reset_discard", "side": "roman", "card": "R21"},
    {"type": "reset_done", "side": "roman"},
    {"type": "reset_discard", "side": "seljuk", "card": "R21"},
    {"type": "reset_discard", "side": "seljuk", "card": "R3", "lord": "romanos_diogenes"},
    {"type": "reset_discard", "side": "seljuk", "card": "S25", "lord": "romanos_diogenes"},
    {"type": "reset_discard", "side": "seljuk", "card": "S17"},
    {"type": "reset_discard", "side": "seljuk", "card": None},
    {"type": "reset_discard", "side": "seljuk", "card": ["S21", "S8"]},
    {"type": "reset_discard", "side": "seljuk", "card": {"S21": True}},
    {"type": "cmd_pass"}, {"type": "end_activation"}, {"type": "winter_proceed"},
])
def test_invalid_discard_or_bypass_is_atomic_and_keep_all_retry_is_legal(action):
    state = position()
    begin_end(state)
    assert state.meta.subphase == "campaign.reset_discard" and decision_side(state) == "seljuk"
    before = state.to_json()
    pending, history, lord = state.meta.pending, state.history, state.lords["alp_arslan"]
    with pytest.raises(IllegalAction):
        engine.apply_action(state, action)
    assert state.to_json() == before
    assert state.meta.pending is pending and state.history is history and state.lords[lord.id] is lord
    keep_reset_cards(state)
    assert state.meta.phase == "levy" and state.seljuk.held_events == ["S21"]


def test_cards_return_to_their_printed_deck_for_a_lord_of_different_allegiance():
    state = clean_position()
    take_card(state, state.lords["alp_arslan"], "R3")
    begin_end(state)
    discard(state, "seljuk", "R3", lord="alp_arslan")
    assert state.roman.draw_deck.count("R3") == 1 and "R3" not in state.seljuk.draw_deck


def test_partial_discard_and_private_pages_survive_save_load_and_reject_stale_ids(tmp_path):
    state = position()
    begin_end(state)
    interface = CompactInterface(LLMSession(state))
    first = interface.actions(type="reset_discard", limit=1)
    second = interface.actions(cursor=first["next_cursor"])
    card = second["entries"][0]["action"]["card"]
    selected = interface.actions(card=card)["entries"][0]
    assert selected["id"] == second["entries"][0]["id"]
    assert len(interface.details(selected["id"])["help"]["eligible_cards"]) == 3
    interface.apply(selected["id"])
    path = tmp_path / "reset.json"
    interface.save(path)
    interface = CompactInterface.load(path)
    before = interface.gs.to_json()
    with pytest.raises(InterfaceError):
        interface.apply(first["entries"][0]["id"])
    assert interface.gs.to_json() == before
    interface.apply(interface.actions(type="reset_done")["entries"][0]["id"])
    assert interface.owed == "roman"
    interface.player = "seljuk"
    assert interface.actions()["entries"] == []
    with pytest.raises(InterfaceError):
        interface.apply({"type": "reset_discard", "side": "roman", "card": "R21"}, version=interface.version)
    interface.player = "roman"
    interface.apply(interface.actions(card="R21")["entries"][0]["id"])
    assert "R21" not in interface.gs.roman.held_events


@pytest.mark.parametrize("cards", [False, True])
def test_final_game_end_never_creates_optional_reset_choices(cards):
    state = position() if cards else clean_position()
    state.meta.calendar_box = state.meta.final_box
    for lord in state.lords.values():
        if lord.mustered:
            lord.service_box = 13
    begin_end(state)
    assert state.meta.phase == "game_over" and state.meta.pending == []
    if cards:
        assert state.seljuk.held_events == ["S21"]
