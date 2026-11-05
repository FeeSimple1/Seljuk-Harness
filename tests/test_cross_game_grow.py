"""SEL2-03: player-selected Spring Grow, with fixed quotas and ordered owners."""
from __future__ import annotations

from itertools import combinations

import pytest

from seljuk import engine, scenarios
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.routing import decision_side
from seljuk.state import GameState, IllegalAction
from tests.test_cross_game_avoid_wastage import begin_end, waste
from tests.test_cross_game_lifecycle import clean_position

LOCALES = ["larisa", "tephrike", "keltzene", "chaldia", "melitene", "koloneia"]


def position(*, side="seljuk", count=4, box=1):
    state = clean_position()
    state.meta.calendar_box = box
    for locale in state.locales.values():
        locale.ravaged_side = None
    for lid in LOCALES[:count]:
        state.locales[lid].ravaged_side = side
    return state


def grow(state, side, locale):
    return engine.apply_action(state, {"type": "grow", "side": side, "locale": locale})


@pytest.mark.parametrize("box", [1, 4, 7, 10])
def test_spring_owner_can_choose_last_two_markers_instead_of_map_order(box):
    state = position(box=box)
    begin_end(state)
    assert state.meta.subphase == "campaign.grow" and decision_side(state) == "roman"
    assert {m["locale"] for m in engine.legal_moves(state)} == set(LOCALES[:4])
    assert all(state.locales[lid].ravaged_side == "seljuk" for lid in LOCALES[:4])
    before = scenarios.score(state)["seljuk"]
    grow(state, "roman", "keltzene")
    assert state.meta.vp == scenarios.score(state)
    assert state.meta.vp["seljuk"] == before - 0.5
    grow(state, "roman", "chaldia")
    assert {lid for lid in LOCALES if state.locales[lid].ravaged_side} == {"larisa", "tephrike"}
    assert state.meta.phase == "levy" and state.meta.calendar_box == box + 1


@pytest.mark.parametrize("side", ["seljuk", "roman"])
@pytest.mark.parametrize("count", range(7))
def test_even_and_odd_counts_leave_half_rounded_up_for_each_marker_owner(side, count):
    state = position(side=side, count=count)
    begin_end(state)
    owner = "roman" if side == "seljuk" else "seljuk"
    for remaining in range(count // 2, 0, -1):
        assert decision_side(state) == owner
        moves, dropped = engine.validated_legal_moves(state)
        assert not dropped and all(m["_remaining"] == remaining for m in moves)
        grow(state, owner, moves[-1]["locale"])
    assert sum(l.ravaged_side == side for l in state.locales.values()) == (count + 1) // 2
    assert not any(p["type"] == "grow" for p in state.meta.pending)
    assert state.meta.phase == "levy"


@pytest.mark.parametrize("kept", list(combinations(LOCALES[:4], 2)))
def test_every_half_sized_retained_subset_is_reachable(kept):
    state = position()
    begin_end(state)
    for lid in [lid for lid in LOCALES[:4] if lid not in kept]:
        assert {m["locale"] for m in engine.legal_moves(state)} == {
            lid for lid in LOCALES[:4] if state.locales[lid].ravaged_side == "seljuk"}
        grow(state, "roman", lid)
    assert {lid for lid in LOCALES[:4] if state.locales[lid].ravaged_side} == set(kept)


def test_seljuk_finishes_before_roman_and_each_quota_remains_fixed():
    state = position(count=5)
    roman_marks = ["ani", "edessa", "artah"]
    for lid in roman_marks:
        state.locales[lid].ravaged_side = "roman"
    begin_end(state)
    assert decision_side(state) == "seljuk"
    grow(state, "seljuk", "edessa")
    assert decision_side(state) == "roman"
    assert all(m["_remaining"] == 2 for m in engine.legal_moves(state))
    grow(state, "roman", "larisa")
    grow(state, "roman", "tephrike")
    assert sum(l.ravaged_side == "roman" for l in state.locales.values()) == 2
    assert sum(l.ravaged_side == "seljuk" for l in state.locales.values()) == 3
    assert not state.meta.pending


@pytest.mark.parametrize("action", [
    {"type": "grow", "side": "seljuk", "locale": "larisa"},
    {"type": "grow", "side": "roman", "locale": "ani"},
    {"type": "grow", "side": "roman", "locale": "edessa"},
    {"type": "grow", "side": "roman", "locale": "missing"},
    {"type": "grow", "side": "roman", "locale": ["larisa"]},
    {"type": "grow", "side": "roman", "locale": {"larisa": True}},
    {"type": "grow", "side": "roman", "locale": None},
    {"type": "end_activation"}, {"type": "cmd_pass"},
    {"type": "wastage", "lord": "alp_arslan", "discard": {"asset": "carts"}},
])
def test_invalid_or_bypassed_grow_is_atomic_and_retry_matches_a_pristine_save(action):
    state = position()
    state.locales["ani"].ravaged_side = "roman"  # singleton: no Seljuk removal owed
    begin_end(state)
    before = state.to_json()
    pending, history, locale = state.meta.pending, state.history, state.locales["larisa"]
    with pytest.raises(IllegalAction):
        engine.apply_action(state, action)
    assert state.to_json() == before
    assert state.meta.pending is pending and state.history is history
    assert state.locales["larisa"] is locale
    pristine = GameState.from_json(before)
    for lid in ["keltzene", "chaldia"]:
        grow(state, "roman", lid)
        grow(pristine, "roman", lid)
    assert state.to_json() == pristine.to_json()


def test_already_removed_marker_and_extra_removal_are_rejected():
    state = position()
    begin_end(state)
    grow(state, "roman", "larisa")
    before = state.to_json()
    with pytest.raises(IllegalAction):
        grow(state, "roman", "larisa")
    assert state.to_json() == before
    grow(state, "roman", "tephrike")
    before = state.to_json()
    with pytest.raises(IllegalAction):
        grow(state, "roman", "keltzene")
    assert state.to_json() == before


def test_repair_wastage_and_reset_wait_for_grow_and_run_once_afterwards():
    state = position()
    lord = state.lords["alp_arslan"]
    lord.assets.carts = 2
    lord.cylinder = "melitene"
    state.lords["romanos_diogenes"].cylinder = "melitene"
    state.lords["romanos_diogenes"].besieged = True
    state.locales["melitene"].siege_markers = 3
    state.seljuk.draw_deck.remove("S17")
    state.seljuk.this_campaign_events = ["S17"]
    begin_end(state)
    grow(state, "roman", "larisa")
    assert state.locales["melitene"].siege_markers == 3 and lord.assets.carts == 2
    assert state.seljuk.this_campaign_events == ["S17"]
    grow(state, "roman", "tephrike")
    assert state.locales["melitene"].siege_markers == 2
    assert lord.assets.carts == 2 and state.seljuk.this_campaign_events == ["S17"]
    assert {m["type"] for m in engine.legal_moves(state)} == {"wastage"}
    waste(state, lord.id, {"asset": "carts"})
    assert lord.assets.carts == 1 and state.locales["melitene"].siege_markers == 2
    assert not state.seljuk.this_campaign_events and state.seljuk.draw_deck.count("S17") == 1
    assert state.meta.phase == "levy"


@pytest.mark.parametrize("box,final", [(2, 12), (3, 12), (4, 4)])
def test_no_grow_outside_spring_or_after_final_game_end(box, final):
    state = position(box=box)
    state.meta.final_box = final
    begin_end(state)
    assert not any(p["type"] == "grow" for p in state.meta.pending)
    assert all(state.locales[lid].ravaged_side == "seljuk" for lid in LOCALES[:4])
    if box == final:
        assert state.meta.phase == "game_over"


def test_partial_grow_save_load_and_compact_pagination_preserve_choice_and_owner(tmp_path):
    state = position()
    begin_end(state)
    interface = CompactInterface(LLMSession(state))
    first = interface.actions(type="grow", limit=1)
    second = interface.actions(cursor=first["next_cursor"])
    lid = second["entries"][0]["action"]["locale"]
    selected = next(row for row in interface.actions()["entries"] if row["action"]["locale"] == lid)
    assert selected["id"] == second["entries"][0]["id"]
    detail = interface.details(selected["id"])["help"]
    assert detail["remaining"] == 2 and set(detail["eligible_locales"]) == set(LOCALES[:4])
    interface.apply(selected["id"])
    path = tmp_path / "grow.json"
    interface.save(path)
    interface = CompactInterface.load(path)
    assert interface.owed == "roman" and interface.details(interface.actions()["entries"][0]["id"])["help"]["remaining"] == 1
    before = interface.gs.to_json()
    with pytest.raises(InterfaceError):
        interface.apply(first["entries"][0]["id"])
    assert interface.gs.to_json() == before
    interface.player = "seljuk"
    assert interface.actions()["entries"] == []
    with pytest.raises(InterfaceError):
        interface.apply({"type": "grow", "side": "roman", "locale": "chaldia"}, version=interface.version)
    interface.player = "roman"
    interface.apply(interface.actions()["entries"][0]["id"])
    assert not any(p["type"] == "grow" for p in interface.gs.meta.pending)
