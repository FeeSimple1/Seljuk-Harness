"""S4/S5 regressions through the dispatcher and player-facing interfaces."""

from __future__ import annotations

import pytest

from seljuk import campaign, engine
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.routing import decision_side
from seljuk.state import Assets, GameState, IllegalAction
from tests.test_cross_game_combat import place, position


def avoid_position(prov, carts, other_prov, other_carts):
    state = position()
    first = place(state, "chatatourios", provender=prov, carts=carts, loot=1)
    second = place(state, "romanos_diogenes", provender=other_prov, carts=other_carts)
    attacker = place(state, "alp_arslan")
    state.meta.pending = [
        {
            "type": "approach_response",
            "locale": "melitene",
            "attackers": [attacker.id],
            "defenders": [first.id, second.id],
            "from": "edessa",
        }
    ]
    return state, first, second, attacker


def avoid_action(second="larisa"):
    return {
        "type": "respond_approach",
        "choices": {
            "chatatourios": {"action": "avoid", "to": "larisa"},
            "romanos_diogenes": {"action": "avoid", "to": second},
        },
    }


@pytest.mark.parametrize(
    "prov,carts,other_prov,other_carts,kept,other_kept",
    [
        (2, 0, 0, 2, 2, 0),
        (4, 1, 1, 2, 2, 1),
        (1, 3, 4, 0, 1, 2),
        (3, 0, 3, 0, 0, 0),
        (8, 0, 0, 8, 8, 0),
        (2, 1, 2, 1, 1, 1),
    ],
)
def test_coavoiders_share_spare_carts_and_only_excess_food_becomes_spoils(
    prov, carts, other_prov, other_carts, kept, other_kept
):
    state, first, second, attacker = avoid_position(
        prov, carts, other_prov, other_carts
    )
    reloaded = GameState.from_json(state.to_json())
    LLMSession(state).apply(avoid_action())
    engine.apply_action(reloaded, avoid_action())
    assert state.to_json() == reloaded.to_json()
    assert first.assets.provender == kept and second.assets.provender == other_kept
    assert first.assets.carts == carts and second.assets.carts == other_carts
    assert first.assets.loot == 0 and attacker.assets.loot == 1
    assert attacker.assets.provender == prov + other_prov - kept - other_kept
    assert first.cylinder == second.cylinder == "larisa"
    assert first.moved_fought and second.moved_fought


def test_avoiders_to_different_destinations_cannot_share_carts():
    state, first, second, attacker = avoid_position(2, 0, 0, 2)
    engine.apply_action(state, avoid_action("lykandos"))
    assert first.assets.provender == 0 and attacker.assets.provender == 2
    assert first.cylinder == "larisa" and second.cylinder == "lykandos"


def test_withdrawer_does_not_lend_carts_to_an_avoider():
    state, first, second, attacker = avoid_position(2, 0, 0, 2)
    action = avoid_action()
    action["choices"][second.id] = {"action": "withdraw"}
    engine.apply_action(state, action)
    assert second.besieged and second.cylinder == "melitene"
    assert first.assets.provender == 0 and attacker.assets.provender == 2


def test_bad_group_avoid_is_atomic_and_retry_matches_a_pristine_save():
    state, first, second, _ = avoid_position(2, 0, 0, 2)
    before = state.to_json()
    with pytest.raises(IllegalAction):
        engine.apply_action(state, avoid_action("constantinople"))
    assert state.to_json() == before
    assert state.lords[first.id] is first and state.lords[second.id] is second
    retry = GameState.from_json(before)
    engine.apply_action(state, avoid_action())
    engine.apply_action(retry, avoid_action())
    assert state.to_json() == retry.to_json()


def end_position(*, cap=None):
    state = position()
    state.meta.calendar_box = 1
    lord = place(state, "alp_arslan", carts=2, loot=1)
    place(state, "chatatourios", "larisa")
    lord.capabilities = []
    if cap:
        deck = state.roman if cap.startswith("R") else state.seljuk
        deck.draw_deck.remove(cap)
        lord.capabilities = [cap]
    state.seljuk.command_plan = []
    state.roman.command_plan = []
    return state


def begin_end(state):
    result = engine.apply_action(state, {"type": "end_activation"})
    while state.meta.subphase == "campaign.fpd_pay":
        engine.apply_action(state, {"type": "fpd_done"})
    return result


def waste(state, lord, discard):
    return engine.apply_action(
        state, {"type": "wastage", "lord": lord, "discard": discard}
    )


@pytest.mark.parametrize(
    "discard", [{"asset": "carts"}, {"asset": "loot"}, {"card": "S21"}]
)
def test_end_campaign_offers_singleton_assets_and_card_and_uses_the_selected_item(
    discard,
):
    state = end_position(cap="S21")
    before = state.lords["alp_arslan"].model_dump(mode="json")
    begin_end(state)
    assert state.meta.calendar_box == 1
    assert decision_side(state) == "seljuk"
    moves = engine.legal_moves(state)
    assert {str(m["discard"]) for m in moves} == {
        str(d) for d in [{"asset": "carts"}, {"asset": "loot"}, {"card": "S21"}]
    }
    waste(state, "alp_arslan", discard)
    lord = state.lords["alp_arslan"]
    assert lord.assets.carts == before["assets"]["carts"] - int(
        discard == {"asset": "carts"}
    )
    assert lord.assets.loot == before["assets"]["loot"] - int(
        discard == {"asset": "loot"}
    )
    assert ("S21" in lord.capabilities) == (discard != {"card": "S21"})
    assert state.meta.calendar_box == 2 and campaign.wastage_moves(state) is None


def test_wastage_returns_a_captured_capability_to_its_printed_side_deck():
    state = end_position(cap="R21")
    begin_end(state)
    roman_before = state.roman.draw_deck.count("R21")
    seljuk_before = state.seljuk.draw_deck.count("R21")
    waste(state, "alp_arslan", {"card": "R21"})
    assert state.roman.draw_deck.count("R21") == roman_before + 1
    assert state.seljuk.draw_deck.count("R21") == seljuk_before


@pytest.mark.parametrize(
    "action",
    [
        {"type": "wastage", "lord": "alp_arslan", "discard": {"asset": "provender"}},
        {"type": "wastage", "lord": "chatatourios", "discard": {"asset": "loot"}},
        {"type": "wastage", "lord": "alp_arslan", "discard": {"card": "S20"}},
        {"type": "end_activation"},
    ],
)
def test_invalid_or_bypassed_wastage_preserves_state_and_can_be_retried(action):
    state = end_position()
    begin_end(state)
    before = state.to_json()
    lord = state.lords["alp_arslan"]
    with pytest.raises(IllegalAction):
        engine.apply_action(state, action)
    assert state.to_json() == before and state.lords[lord.id] is lord
    waste(state, lord.id, {"asset": "loot"})
    assert lord.assets.carts == 2 and lord.assets.loot == 0


def test_pending_wastage_survives_save_load_and_has_a_private_versioned_menu():
    state = end_position(cap="S21")
    state.meta.options["hidden_mats"] = True
    begin_end(state)
    state = GameState.from_json(state.to_json())
    enemy = LLMSession(state)
    assert enemy.legal_actions(side="roman") == []
    assert enemy.pending("roman") == [
        {"type": "opponent_decision", "owed_by": "seljuk"}
    ]
    interface = CompactInterface(enemy, player="seljuk")
    version = interface.version
    interface.apply(
        {"type": "wastage", "lord": "alp_arslan", "discard": {"asset": "loot"}},
        version=version,
    )
    after = interface.gs.to_json()
    assert interface.gs.lords["alp_arslan"].assets.loot == 0
    with pytest.raises(InterfaceError):
        interface.apply(
            {"type": "wastage", "lord": "alp_arslan", "discard": {"asset": "carts"}},
            version=version,
        )
    assert interface.gs.to_json() == after


def queue_event(state, card, side):
    state.meta.phase = "levy"
    state.meta.active_player = side
    deck = state.side_decks(side)
    if card in deck.draw_deck:
        deck.draw_deck.remove(card)
    state.meta.pending = [
        {"type": "event_pending_resolution", "card": card, "side": side}
    ]
    return engine.apply_action(
        state, {"type": "resolve_event", "card": card, "args": {}}
    )


@pytest.mark.parametrize("first,count", [("carts", 1), ("loot", 2)])
def test_flooded_river_uses_seljuk_choices_and_stops_when_no_longer_qualified(
    first, count
):
    state = end_position()
    result = queue_event(state, "R1", "roman")
    assert result["wastage_pending"] and decision_side(state) == "seljuk"
    assert state.meta.active_player == "roman"
    assert state.meta.pending[0]["remaining"] == 3
    waste(state, "alp_arslan", {"asset": first})
    if count == 2:
        assert state.meta.pending[0]["remaining"] == 2
        state = GameState.from_json(state.to_json())
        waste(state, "alp_arslan", {"asset": "carts"})
    assert campaign.wastage_moves(state) is None
    assert state.lords["alp_arslan"].assets.carts == 1
    assert "R1" in state.meta.asterisks_used
    assert sum(h["action"]["type"] == "wastage" for h in state.history) == count


def test_wastage_interrupts_the_next_drawn_event():
    state = end_position()
    state.meta.phase = "levy"
    state.meta.active_player = "roman"
    state.meta.pending = [
        {"type": "event_pending_resolution", "card": "R1", "side": "roman"},
        {"type": "event_pending_resolution", "card": "R10", "side": "roman"},
    ]
    engine.apply_action(state, {"type": "resolve_event", "card": "R1", "args": {}})
    before = state.to_json()
    with pytest.raises(IllegalAction, match="pending_decision"):
        engine.apply_action(state, {"type": "resolve_event", "card": "R10", "args": {}})
    assert state.to_json() == before
    waste(state, "alp_arslan", {"asset": "carts"})
    assert decision_side(state) == "roman"
    assert engine.legal_moves(state)[0]["card"] == "R10"


def test_mercenary_discipline_lets_each_roman_lord_choose_once():
    state = end_position()
    for lid in ["chatatourios", "romanos_diogenes"]:
        place(state, lid, "larisa", carts=2, loot=1)
    state.locales["larisa"].ravaged_side = "seljuk"
    result = queue_event(state, "S25", "seljuk")
    assert result["wastage_pending"] == 2 and decision_side(state) == "roman"
    choices = {"chatatourios": "loot", "romanos_diogenes": "carts"}
    while campaign.wastage_moves(state) is not None:
        lid = engine.legal_moves(state)[0]["lord"]
        waste(state, lid, {"asset": choices[lid]})
    assert campaign.wastage_moves(state) is None
    assert state.lords["chatatourios"].assets == Assets(carts=2)
    assert state.lords["romanos_diogenes"].assets == Assets(carts=1, loot=1)


@pytest.mark.parametrize("target", ["alp_arslan", "afsin_beg"])
def test_raider_owner_can_choose_any_adjacent_enemy_then_victim_chooses_discard(target):
    state = position()
    state.meta.calendar_box = 1
    place(state, "chatatourios", "artah").capabilities = ["R22"]
    place(state, "alp_arslan", "manbij", carts=3, loot=1)
    place(state, "afsin_beg", "manbij", carts=1)
    state.seljuk.command_plan = state.roman.command_plan = []
    begin_end(state)
    waste(state, "alp_arslan", {"asset": "loot"})
    assert decision_side(state) == "roman"
    assert {m["target"] for m in engine.legal_moves(state)} == {
        "alp_arslan",
        "afsin_beg",
    }
    engine.apply_action(
        state, {"type": "wastage_target", "raider": "chatatourios", "target": target}
    )
    if target == "alp_arslan":
        assert decision_side(state) == "seljuk"
        waste(state, target, {"asset": "carts"})
    assert state.lords["alp_arslan"].assets.carts == (
        2 if target == "alp_arslan" else 3
    )
    assert campaign.wastage_moves(state) is None


def test_final_game_end_precedes_wastage():
    state = end_position()
    state.meta.final_box = state.meta.calendar_box
    before = state.lords["alp_arslan"].assets.model_copy()
    begin_end(state)
    assert (
        state.meta.phase == "game_over" and state.lords["alp_arslan"].assets == before
    )
    assert campaign.wastage_moves(state) is None
