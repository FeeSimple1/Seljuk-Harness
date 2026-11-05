"""SEL2-01/05: temporary Forces leaving play must clean up their Lord's mat."""
from __future__ import annotations

import pytest

from seljuk import actions, campaign, engine, static_data as sd
from seljuk.llm import LLMSession
from seljuk.state import Assets, GameState, IllegalAction
from tests.reset_helpers import keep_reset_cards
from tests.test_cross_game_avoid_wastage import begin_end, waste
from tests.test_cross_game_combat import place, position


def clean_position():
    state = position()
    state.meta.calendar_box = 1
    for lord in state.lords.values():
        lord.capabilities = []
        lord.moved_fought = False
        lord.lieutenant_of = lord.lower_lord = None
    for decks in (state.roman, state.seljuk):
        decks.draw_deck.extend(decks.capabilities_in_play + decks.held_events
                               + decks.this_campaign_events)
        decks.capabilities_in_play = []
        decks.held_events = []
        decks.this_campaign_events = []
        decks.command_plan = []
        decks.plan_pointer = 0
    place(state, "alp_arslan", "ani").service_box = 13
    place(state, "romanos_diogenes", "larisa").service_box = 13
    return state


def take_card(state, lord, card):
    decks = state.side_decks(sd.card(card)["side"])
    for zone in (decks.draw_deck, decks.held_events, decks.capabilities_in_play,
                 decks.this_campaign_events):
        while card in zone:
            zone.remove(card)
    lord.capabilities.append(card)


def thema_position(*, coins=0, free=False):
    state = clean_position()
    lord = state.lords["romanos_diogenes"]
    lord.forces = {}
    lord.assets = Assets(coin=coins)
    marker = state.themata["Boukellarion"].pop(0)
    marker.home_thema = "Boukellarion"
    lord.themata_on_mat = [marker]
    if free:
        state.roman.draw_deck.remove("R4")
        state.roman.capabilities_in_play.append("R4")
    return state, lord, marker


@pytest.mark.parametrize("box", [1, 3, 10])
def test_final_thema_disbands_commander_before_calendar_advance_or_winter(box):
    state, lord, marker = thema_position()
    state.meta.calendar_box = box
    lord.service_box = 13
    lord.assets = Assets(carts=1, provender=1, loot=1)
    take_card(state, lord, "R3")
    begin_end(state)
    assert not lord.mustered and lord.cylinder == "calendar"
    assert lord.cylinder_calendar_box == min(box + 4, 13)
    assert lord.service_box is None and lord.assets == Assets()
    assert lord.forces == lord.routed == {} and lord.vassals == []
    assert lord.themata_on_mat == [] and lord.capabilities == []
    assert state.roman.draw_deck.count("R3") == 1
    assert marker in state.themata["Boukellarion"] and marker.home_thema is None
    assert marker.strength is None and marker.routed == 0
    assert state.meta.phase == "game_over" and state.meta.notes["winner"] == "seljuk"
    assert "no Mustered Lords" in state.meta.notes["win_reason"]
    assert state.meta.calendar_box == box and engine.legal_moves(state) == []


def test_empty_commander_cleanup_preserves_other_lords_and_detaches_lieutenant():
    state, lord, _ = thema_position()
    lower = place(state, "chatatourios", "larisa")
    lord.lower_lord = lower.id
    lower.lieutenant_of = lord.id
    begin_end(state)
    assert not lord.mustered and lord.cylinder_calendar_box == 5
    assert lower.mustered and lower.forces == {"infantry": 1}
    assert lord.lower_lord is None and lower.lieutenant_of is None
    assert state.meta.phase == "levy" and state.meta.calendar_box == 2


def test_commander_with_own_units_survives_returning_all_themata():
    state, lord, marker = thema_position()
    lord.forces = {"infantry": 1}
    begin_end(state)
    assert lord.mustered and lord.forces == {"infantry": 1}
    assert not lord.themata_on_mat and marker in state.themata["Boukellarion"]
    assert state.meta.phase == "levy"


@pytest.mark.parametrize("mode", ["pay", "pressed_levy", "return"])
def test_saved_retention_choice_keeps_or_disbands_the_last_force(mode):
    state, lord, _ = thema_position(coins=int(mode != "pressed_levy"),
                                    free=mode == "pressed_levy")
    begin_end(state)
    assert state.meta.subphase == "campaign.reset"
    state = GameState.from_json(state.to_json())
    lord = state.lords[lord.id]
    LLMSession(state).apply({"type": "retain_themata", "lord": lord.id,
                             "thema": "Boukellarion", "mode": mode})
    keep_reset_cards(state)
    assert lord.mustered == (mode != "return")
    assert bool(lord.themata_on_mat) == (mode != "return")
    if mode == "return":
        assert state.meta.phase == "game_over" and lord.cylinder_calendar_box == 5
    else:
        assert state.meta.phase == "levy" and lord.cylinder == "larisa"
        assert lord.assets.coin == 0


def test_final_game_end_does_not_return_themata_or_disband_the_commander():
    state, lord, marker = thema_position()
    state.meta.calendar_box = state.meta.final_box
    begin_end(state)
    assert state.meta.phase == "game_over"
    assert lord.mustered and lord.themata_on_mat == [marker]
    assert marker.home_thema == "Boukellarion"


def special_position(card, *, optional=False, levy=True):
    state = clean_position()
    state.meta.options["vassal_service"] = optional
    lord = state.lords["alp_arslan" if card == "S20" else "romanos_diogenes"]
    lord.flags = {}
    state.meta.phase = "levy"
    state.meta.subphase = "levy.muster"
    state.meta.active_player = lord.side
    engine.apply_action(state, {"type": "levy_capability", "lord": lord.id, "card": card})
    index = next(i for i, v in enumerate(lord.vassals) if v.requires_capability == card)
    if levy:
        engine.apply_action(state, {"type": "levy_vassal", "lord": lord.id,
                                    "vassal_index": index})
    vassal = lord.vassals[index]
    state.meta.phase = "campaign"
    state.meta.subphase = "campaign.command"
    state.meta.active_lord = state.meta.active_card = "alp_arslan"
    state.meta.active_player = "seljuk"
    state.meta.actions_remaining = 2
    lord.assets.carts = 2
    return state, lord, vassal


@pytest.mark.parametrize("card", ["R2", "R7", "R17", "S20"])
@pytest.mark.parametrize("optional", [False, True])
def test_offered_wastage_discard_removes_special_units_and_service_marker(card, optional):
    state, lord, vassal = special_position(card, optional=optional)
    assert vassal.levied and (vassal.service_box is not None) == optional
    begin_end(state)
    selected = {"type": "wastage", "lord": lord.id, "discard": {"card": card}}
    assert any(all(move.get(k) == v for k, v in selected.items())
               for move in engine.legal_moves(state))
    reloaded = GameState.from_json(state.to_json())
    engine.apply_action(reloaded, selected)
    engine.apply_action(state, selected)
    assert state.to_json() == reloaded.to_json()
    assert lord.mustered and lord.forces == {"infantry": 1}
    assert not any(v.requires_capability == card for v in lord.vassals)
    assert not vassal.levied and vassal.service_box is None
    assert not vassal.unready and card not in lord.capabilities
    assert state.side_decks(sd.card(card)["side"]).draw_deck.count(card) == 1


def test_discarding_an_unlevied_special_vassal_does_not_remove_existing_units():
    state, lord, _ = special_position("R2", levy=False)
    lord.forces = {"turkic_horse": 2}
    begin_end(state)
    waste(state, lord.id, {"card": "R2"})
    assert lord.mustered and lord.forces == {"turkic_horse": 2}
    assert not any(v.requires_capability == "R2" for v in lord.vassals)


def test_special_vassal_returns_only_available_units_and_never_themata():
    state, lord, _ = special_position("R2")
    lord.forces = {"turkic_horse": 1}
    marker = state.themata["Boukellarion"].pop(0)
    marker.home_thema = "Boukellarion"
    lord.themata_on_mat = [marker]
    state.roman.draw_deck.remove("R4")
    state.roman.capabilities_in_play.append("R4")
    begin_end(state)
    waste(state, lord.id, {"card": "R2"})
    assert lord.mustered and lord.forces == {} and lord.themata_on_mat == [marker]
    assert not any(v.requires_capability == "R2" for v in lord.vassals)
    assert state.meta.subphase == "campaign.reset"


@pytest.mark.parametrize("ally", [False, True])
def test_special_vassal_final_force_disbands_and_rechecks_immediate_victory(ally):
    state, lord, _ = special_position("R2")
    lord.forces = {"turkic_horse": 2}
    take_card(state, lord, "R3")
    if ally:
        place(state, "chatatourios", "larisa")
    begin_end(state)
    waste(state, lord.id, {"card": "R2"})
    assert not lord.mustered and lord.cylinder == "calendar"
    assert lord.cylinder_calendar_box == 5 and lord.assets == Assets()
    assert lord.vassals == [] and lord.capabilities == []
    assert state.roman.draw_deck.count("R2") == 1
    assert state.roman.draw_deck.count("R3") == 1
    assert state.meta.pending == [] and engine.legal_moves(state) == []
    assert state.meta.phase == ("levy" if ally else "game_over")
    if not ally:
        assert state.meta.notes["winner"] == "seljuk" and state.meta.calendar_box == 1


def test_special_card_can_be_levied_again_with_a_fresh_ready_service_marker():
    state, lord, _ = special_position("R2", optional=True)
    begin_end(state)
    waste(state, lord.id, {"card": "R2"})
    state.meta.phase = "levy"
    state.meta.subphase = "levy.muster"
    state.meta.active_player = "roman"
    lord.flags = {}
    engine.apply_action(state, {"type": "levy_capability", "lord": lord.id, "card": "R2"})
    indices = [i for i, v in enumerate(lord.vassals) if v.requires_capability == "R2"]
    assert len(indices) == 1
    slot = lord.vassals[indices[0]]
    assert not slot.levied and not slot.unready and slot.service_box is None
    engine.apply_action(state, {"type": "levy_vassal", "lord": lord.id,
                                "vassal_index": indices[0]})
    assert slot.levied and lord.forces == {"infantry": 1, "turkic_horse": 2}


def test_rejected_special_discard_is_atomic_and_retry_still_cleans_up():
    state, lord, _ = special_position("R2")
    begin_end(state)
    before = state.to_json()
    with pytest.raises(IllegalAction):
        waste(state, lord.id, {"card": "R7"})
    assert state.to_json() == before and state.lords[lord.id] is lord
    waste(state, lord.id, {"card": "R2"})
    assert lord.forces == {"infantry": 1} and "R2" not in lord.capabilities


def test_empty_lord_during_levy_disbands_without_campaign_victory():
    state, lord, _ = special_position("R2")
    lord.forces = {"turkic_horse": 2}
    state.meta.phase = "levy"
    actions.discard_lord_capability(state, lord, "R2")
    assert not lord.mustered and lord.cylinder_calendar_box == 5
    assert state.meta.phase == "levy" and "winner" not in state.meta.notes
