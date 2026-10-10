"""Regressions from a 132-action, deliberately chosen two-sided Manzikert game.

The recorded game avoids the SP-01 exploit. All 132 actions are unchanged.
Ten state hashes were rebaselined by the longest-scenario fixes: relief clears
immediately, and the returned S17 card changes the later Autumn draw. Exact
state and save/load assertions still cover every action.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from seljuk import actions, campaign, engine, scenarios
from seljuk.invariants import check_invariants
from seljuk.llm import LLMSession
from seljuk.state import GameState, IllegalAction

FIXTURE = Path(__file__).parent / "fixtures" / "manzikert_selfplay_20261009.json"


def _hash(gs):
    return hashlib.sha256(gs.to_json(indent=None).encode()).hexdigest()


def _concrete(moves):
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in moves]


@pytest.fixture(scope="module")
def replayed_game():
    record = json.loads(FIXTURE.read_text())
    session = LLMSession.start_new(record["scenario"], seed=record["seed"])
    assert _hash(session.gs) == record["initial_sha256"]
    checkpoints = {}
    for i, entry in enumerate(record["steps"]):
        if i in (11, 16, 130):
            checkpoints[i] = session.gs.to_json()
        session.apply(entry["action"])
        assert not check_invariants(session.gs), f"invariants after action {i}"
        assert _hash(session.gs) == entry["after_sha256"], f"replay mismatch at {i}"
        # Continue from the serialized state, not merely inspect its contents.
        session = LLMSession(GameState.from_json(session.gs.to_json()))
        assert _hash(session.gs) == entry["after_sha256"], f"save/load mismatch at {i}"
    return session, checkpoints, record


def test_complete_game_replays_all_132_actions_and_save_loads(replayed_game):
    session, _, record = replayed_game
    assert len(record["steps"]) == 132
    assert session.is_over() and session.winner() == record["expected_winner"]
    assert session.gs.meta.notes["win_reason"] == record["expected_win_reason"]
    assert session.gs.meta.calendar_box == 12
    assert session.gs.meta.vp == record["expected_score"]


FULL_CARD_CASES = [
    (11, {"type": "cmd_siege", "lord": "alp_arslan"}),
    (11, {"type": "cmd_siege", "lord": "alp_arslan", "roll_surrender": False}),
    (16, {"type": "cmd_tax", "lord": "romanos_diogenes"}),
    (16, {"type": "cmd_march", "lord": "romanos_diogenes",
          "to": "to_constantinople", "way_type": "road"}),
]


@pytest.mark.parametrize("step,action", FULL_CARD_CASES)
def test_sp01_partial_card_not_in_either_palette(replayed_game, step, action):
    gs = GameState.from_json(replayed_game[1][step])
    assert gs.meta.actions_remaining == 3 and gs.meta.notes["card_full_actions"] == 4
    assert action not in _concrete(engine.legal_moves(gs))
    kept, dropped = engine.validated_legal_moves(gs)
    assert action not in _concrete(kept)
    # Fix the raw enumerator, rather than rely on the validation filter.
    assert not any(d["action"] == action for d in dropped)


@pytest.mark.parametrize("step,action", FULL_CARD_CASES)
def test_sp01_direct_submission_rejects_before_any_mutation(replayed_game, step, action):
    gs = GameState.from_json(replayed_game[1][step])
    before = gs.to_json()
    with pytest.raises(IllegalAction) as exc:
        engine.apply_action(gs, action)
    assert exc.value.code == "full_card_required"
    assert gs.to_json() == before  # includes dice, history, assets and pending state


@pytest.mark.parametrize("step,action", FULL_CARD_CASES)
def test_sp01_same_position_with_full_budget_is_legal(replayed_game, step, action):
    gs = GameState.from_json(replayed_game[1][step])
    gs.meta.actions_remaining = gs.meta.notes["card_full_actions"]
    assert action in _concrete(engine.legal_moves(gs))
    assert engine.apply_action(gs, action)["ok"]


def test_sp01_rejects_holding_box_exit_after_supply(replayed_game):
    gs = GameState.from_json(replayed_game[1][16])
    gs.lords["romanos_diogenes"].cylinder = "to_constantinople"
    action = {"type": "cmd_march", "lord": "romanos_diogenes", "to": "ankyra", "way_type": "road"}
    assert action not in _concrete(engine.legal_moves(gs))
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="full_card_required"):
        engine.apply_action(gs, action)
    assert gs.to_json() == before


def test_sp01_rejects_before_discarding_assets(replayed_game):
    gs = GameState.from_json(replayed_game[1][16])
    gs.lords["romanos_diogenes"].assets.loot = 2
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="full_card_required"):
        engine.apply_action(gs, {**FULL_CARD_CASES[-1][1], "discard_to_unladen": True})
    assert gs.to_json() == before


@pytest.mark.parametrize("remaining", [0, -1])
def test_sp01_no_full_card_command_without_actions(replayed_game, remaining):
    gs = GameState.from_json(replayed_game[1][16])
    gs.meta.actions_remaining = remaining
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="full_card_required"):
        engine.apply_action(gs, FULL_CARD_CASES[2][1])
    assert gs.to_json() == before


def test_sp01_storm_can_end_a_partially_used_card(replayed_game):
    gs = GameState.from_json(replayed_game[1][11])
    action = {"type": "cmd_storm", "lord": "alp_arslan"}
    assert action in _concrete(engine.legal_moves(gs))
    assert engine.apply_action(gs, action)["ok"]


def test_sp01_ordinary_march_remains_available_after_supply(replayed_game):
    gs = GameState.from_json(replayed_game[1][16])
    action = {"type": "cmd_march", "lord": "romanos_diogenes", "to": "charsianon", "way_type": "road"}
    assert action in _concrete(engine.legal_moves(gs))
    assert engine.apply_action(gs, action)["cost"] == 1
    assert gs.meta.actions_remaining == 2


def _tax_card(side="seljuk", winter=False):
    gs = scenarios.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.phase = "winter" if winter else "campaign"
    gs.meta.subphase = "winter.activation" if winter else "campaign.command"
    gs.meta.calendar_box = 3 if winter else 2
    gs.meta.pending.clear()
    gs.meta.active_player = side
    gs.meta.active_lord = None
    lid = "alp_arslan" if side == "seljuk" else "romanos_diogenes"
    lord = gs.lords[lid]
    lord.mustered = True
    lord.cylinder = "ani" if side == "seljuk" else "ankyra"
    lord.service_box = 12
    gs.side_decks(side).command_plan = [lid]
    gs.side_decks(side).plan_pointer = 0
    # Keep another card in each Plan; the tests are not about final cleanup.
    other = "roman" if side == "seljuk" else "seljuk"
    gs.side_decks(other).command_plan = ["chatatourios" if side == "seljuk" else "alp_arslan"]
    gs.side_decks(other).plan_pointer = 0
    return gs, lid


@pytest.mark.parametrize("side,heat", [("seljuk", "R3"), ("roman", "S4")])
def test_sp01_summer_heat_changes_full_card_budget_not_actions_spent(side, heat):
    gs, lid = _tax_card(side)
    opponent = "roman" if side == "seljuk" else "seljuk"
    gs.side_decks(opponent).held_events.append(heat)
    campaign._reveal_next(gs)
    engine.apply_action(gs, {"type": "play_hold_event", "card": heat})
    assert gs.meta.actions_remaining == gs.meta.notes["card_full_actions"] == 1
    action = {"type": "cmd_tax", "lord": lid}
    assert action in _concrete(engine.legal_moves(gs))
    assert engine.apply_action(gs, action)["ok"]


@pytest.mark.parametrize("side,card", [("seljuk", "S18"), ("roman", "R9")])
def test_sp01_winter_initializes_budget_and_blocks_partial_card_tax(side, card):
    gs, lid = _tax_card(side, winter=True)
    gs.side_decks(side).held_events.append(card)
    gs.meta.notes["winter_holders"] = [side]
    engine.apply_action(gs, {"type": "winter_activate", "lord": lid})
    assert gs.meta.notes["card_full_actions"] == gs.meta.actions_remaining
    assert {"type": "cmd_tax", "lord": lid} in _concrete(engine.legal_moves(gs))
    engine.apply_action(gs, {"type": "cmd_supply", "lord": lid, "source": gs.lords[lid].cylinder})
    assert {"type": "cmd_tax", "lord": lid} not in _concrete(engine.legal_moves(gs))
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="full_card_required"):
        engine.apply_action(gs, {"type": "cmd_tax", "lord": lid})
    assert gs.to_json() == before


def test_sp01_capability_modified_budget_is_not_recomputed_after_spending():
    gs, lid = _tax_card()
    gs.lords[lid].capabilities.append("S14")  # Support from Aleppo; seed 1 rolls 2
    campaign._reveal_next(gs)
    assert gs.meta.actions_remaining == gs.meta.notes["card_full_actions"] == 5
    engine.apply_action(gs, {"type": "cmd_supply", "lord": lid, "source": "ani"})
    assert gs.meta.actions_remaining == 4  # printed rating, but NOT the full card
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="full_card_required"):
        engine.apply_action(gs, {"type": "cmd_tax", "lord": lid})
    assert gs.to_json() == before


@pytest.mark.parametrize("coins,active,ruins,expected", [
    (0, [], [], set()),
    (1, [], [], {("amid",), ("mayyafariqin",)}),
    (2, [], [], {("amid",), ("mayyafariqin",), ("amid", "mayyafariqin")}),
    (1, ["amid"], [], {("mayyafariqin",)}),
    (2, ["amid"], [], {("mayyafariqin",)}),
    (1, [], ["amid"], {("mayyafariqin",)}),
    (2, [], ["amid", "mayyafariqin"], set()),
])
def test_sp02_marwanid_choices_are_unique_and_complete(replayed_game, coins, active, ruins, expected):
    gs = GameState.from_json(replayed_game[1][130])
    gs.seljuk.capability_coins["S8"] = coins
    gs.meta.notes["marwanid_seats"] = active
    for loc in ruins:
        gs.locales[loc].ruins = True
    choices = [tuple(m["locales"]) for m in actions.enumerate_call_to_arms(gs) if m["type"] == "cta_marwanid"]
    assert len(choices) == len(set(choices)), choices
    assert set(choices) == expected
    for locales in choices:
        probe = GameState.from_json(gs.to_json())
        assert engine.apply_action(probe, {"type": "cta_marwanid", "locales": list(locales)})["ok"]


def test_sp01_honors_of_war_cannot_bypass_full_card_requirement():
    gs, lid = _tax_card("roman")
    gs.lords[lid].cylinder = "azaz"
    gs.locales["azaz"].siege_markers = 1
    gs.roman.held_events.append("R25")
    campaign._reveal_next(gs)
    gs.meta.actions_remaining -= 1
    action = {"type": "cmd_siege", "lord": lid, "honors_of_war": True}
    assert action not in _concrete(engine.legal_moves(gs))
    assert {"type": "cmd_storm", "lord": lid} in _concrete(engine.legal_moves(gs))
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="full_card_required"):
        engine.apply_action(gs, action)
    assert gs.to_json() == before  # do not consume the Hold or surrender the Fort


def test_sp01_rejects_siege_before_peace_offering_coin_payment(replayed_game):
    gs = GameState.from_json(replayed_game[1][11])
    gs.meta.notes["peace_offering_season"] = True
    gs.lords["alp_arslan"].assets.coin = 1
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="full_card_required"):
        engine.apply_action(gs, FULL_CARD_CASES[0][1])
    assert gs.to_json() == before


@pytest.mark.parametrize("side,heat", [("seljuk", "R3"), ("roman", "S4")])
@pytest.mark.parametrize("when", ["after_decline", "after_supply", "own_lord"])
def test_sp03_summer_heat_requires_its_enemy_reveal_window(side, heat, when):
    owner = "roman" if side == "seljuk" else "seljuk"
    gs, lid = _tax_card(owner if when == "own_lord" else side)
    gs.side_decks(owner).held_events.append(heat)
    campaign._reveal_next(gs)
    if when != "own_lord":
        engine.apply_action(gs, {"type": "decline_summer_heat"})
        if when == "after_supply":
            engine.apply_action(gs, {"type": "cmd_supply", "lord": lid})
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="wrong_timing"):
        engine.apply_action(gs, {"type": "play_hold_event", "card": heat})
    assert gs.to_json() == before
