"""Regressions for Anglo-Saxon Exiles and repeated Roman Muster penalties."""

import pytest

from seljuk import actions, engine, scenarios
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.session import LLMSession
from seljuk.state import IllegalAction


SEEDS = {"R1": 123, "R10": 143, "R16": 70}
NO_LORD = object()


def _event(card, *, repeated=True):
    # Staged Summer bookkeeping, with a seeded draw and the native armies.
    state = scenarios.load_scenario("emperor_and_the_lion", seed=SEEDS[card])
    state.meta.calendar_box = 2
    state.meta.notes["first_aow_done"] = True
    if repeated and card in ("R1", "R10"):
        state.meta.asterisks_used.append(card)
    engine.start_levy(state)
    assert [pending["card"] for pending in state.meta.pending] == [card]
    assert not check_invariants(state)
    return CompactInterface(LLMSession(state))


def _row(ui):
    [row] = ui.actions(type="resolve_event")["entries"]
    return row["id"]


def _help(ui):
    return ui.details(_row(ui))["help"]


def _choose(ui, lord=NO_LORD):
    args = {} if lord is NO_LORD else {"lord": lord}
    ui.apply(_row(ui), parameters={"args": args})
    assert not ui.gs.meta.pending
    assert not check_invariants(ui.gs)
    return ui.gs.history[-1]["result"]


def _reject(ui, code, lord=NO_LORD):
    before, version = ui.gs.to_json(), ui.version
    row = _row(ui)
    args = {} if lord is NO_LORD else {"lord": lord}
    with pytest.raises(IllegalAction) as exc:
        ui.apply(row, parameters={"args": args})
    assert exc.value.code == code
    assert ui.gs.to_json() == before
    assert ui.version == version and _row(ui) == row


def _roundtrip(ui, tmp_path):
    path = tmp_path / "event.json"
    ui.session.save(path)
    loaded = CompactInterface(LLMSession.load(path), player=ui.owed)
    assert loaded.gs.to_json() == ui.gs.to_json()
    assert _help(loaded) == _help(ui)
    return loaded


@pytest.mark.parametrize("lord", ["chatatourios", "romanos_diogenes"])
def test_anglo_saxon_adds_one_guard_on_map_or_in_a_holding_box(lord, tmp_path):
    ui = _event("R16")
    assert set(_help(ui)["eligible_lords"]) == {
        "chatatourios", "romanos_diogenes", "nikephoros_bryennios",
    }
    assert _help(ui)["required_count"] == 1
    saved = _roundtrip(ui, tmp_path)

    foreign = CompactInterface(ui.session, player="seljuk")
    assert foreign.actions(type="resolve_event")["entries"] == []
    before = ui.gs.to_json()
    action = {"type": "resolve_event", "card": "R16", "args": {"lord": lord}}
    with pytest.raises(InterfaceError) as exc:
        foreign.apply(action, version=foreign.version)
    assert exc.value.code == "not_your_decision"
    assert ui.gs.to_json() == before

    old_id = _row(ui)
    assert _choose(ui, lord) == _choose(saved, lord)
    assert saved.gs.to_json() == ui.gs.to_json()
    assert ui.gs.lords[lord].forces["varangian_guard"] == 1
    assert actions._pool_remaining(ui.gs, "varangian_guard") == 1
    assert ui.gs.roman.draw_deck.count("R16") == 1
    with pytest.raises(InterfaceError) as exc:
        ui.apply(old_id, parameters={"args": {"lord": lord}})
    assert exc.value.code == "stale_selection"


def test_anglo_saxon_rejects_invalid_targets_without_spending_the_event():
    ui = _event("R16")
    # The existing unit disqualifies its Lord even in the Routed box.
    ui.gs.lords["chatatourios"].routed["varangian_guard"] = 1
    ui.gs.lords["joseph_tarchaneiotes"].cylinder = "removed"
    for lord in ("manuel_komnenos", "joseph_tarchaneiotes", "alp_arslan",
                 "robert_crepin", "roussel_de_bailleul", "chatatourios"):
        _reject(ui, "bad_event_target", lord)
    _reject(ui, "bad_lord", "unknown_lord")
    _reject(ui, "bad_lord", [])
    _reject(ui, "missing_or_bad_arg")
    assert actions._pool_remaining(ui.gs, "varangian_guard") == 1

    before = ui.gs.to_json()
    action = {"type": "resolve_event", "card": "R16", "args": {"lord": "manuel_komnenos"}}
    with pytest.raises(IllegalAction, match="bad_event_target"):
        engine.apply_action(ui.gs, action)
    assert ui.gs.to_json() == before


@pytest.mark.parametrize("pool_empty", [False, True])
def test_anglo_saxon_can_resolve_without_a_legal_effect(pool_empty):
    ui = _event("R16")
    if pool_empty:
        ui.gs.lords["romanos_diogenes"].forces["varangian_guard"] = 1
        ui.gs.lords["nikephoros_bryennios"].routed["varangian_guard"] = 1
        assert actions._pool_remaining(ui.gs, "varangian_guard") == 0
    else:
        for lord in ui.gs.lords.values():
            if lord.side == "roman":
                lord.mustered = False
                lord.cylinder = "calendar"
        assert actions._pool_remaining(ui.gs, "varangian_guard") == 2
    assert _help(ui)["eligible_lords"] == []
    assert _help(ui)["required_count"] == 0
    assert _choose(ui)["no_op"]
    assert ui.gs.roman.draw_deck.count("R16") == 1


def test_anglo_saxon_uses_the_last_available_guard():
    ui = _event("R16")
    ui.gs.lords["chatatourios"].routed["varangian_guard"] = 1
    assert "chatatourios" not in _help(ui)["eligible_lords"]
    assert _choose(ui, "romanos_diogenes")["added_varangian"] == "romanos_diogenes"
    assert actions._pool_remaining(ui.gs, "varangian_guard") == 0


def test_loading_an_old_save_returns_an_off_map_guard_to_the_pool(tmp_path):
    ui = _event("R16")
    _choose(ui, "chatatourios")
    board = ui.gs
    board.lords["manuel_komnenos"].forces["varangian_guard"] = 1
    assert check_invariants(board) == ["manuel_komnenos has a Varangian Guard without an in-play mat"]
    path = tmp_path / "old-save.json"
    ui.session.save(path)
    restored = LLMSession.load(path).gs
    assert not check_invariants(restored)
    assert not restored.lords["manuel_komnenos"].forces
    assert restored.lords["chatatourios"].forces["varangian_guard"] == 1
    assert actions._pool_remaining(restored, "varangian_guard") == 1


def _finish_pay(session):
    ui = CompactInterface(session)
    for _ in range(2):
        [row] = ui.actions(type="pass_step")["entries"]
        ui.apply(row["id"])
    assert ui.gs.meta.subphase == "levy.muster"
    assert ui.owed == "seljuk"
    return ui


@pytest.mark.parametrize("card", ["R1", "R10"])
def test_repeated_event_requires_an_able_lord_and_penalizes_this_muster(card, tmp_path):
    ui = _event(card)
    assert ui.owed == "seljuk"
    arisighi = ui.gs.lords["arisighi"]
    # Last Levy's temporary budget/arrival flags are cleared on entering Muster.
    arisighi.flags.update(lordship_spent=1, lordship_bonus=2, mustered_this_segment=True)
    assert arisighi.cylinder == "to_mosul_and_baghdad"
    assert set(_help(ui)["eligible_lords"]) == {"alp_arslan", "arisighi", "ibn_khan"}
    foreign = CompactInterface(ui.session, player="roman")
    assert foreign.actions(type="resolve_event")["entries"] == []
    with pytest.raises(InterfaceError) as exc:
        foreign.apply({"type": "resolve_event", "card": card,
                       "args": {"lord": "arisighi"}}, version=foreign.version)
    assert exc.value.code == "not_your_decision"
    _reject(ui, "missing_or_bad_arg")
    _reject(ui, "bad_lord", "unknown_lord")
    _reject(ui, "bad_event_target", "artuk_beg")
    _reject(ui, "bad_event_target", "romanos_diogenes")

    saved = _roundtrip(ui, tmp_path)
    assert _choose(ui, "arisighi") == _choose(saved, "arisighi")
    assert ui.gs.roman.draw_deck.count(card) == 1
    current, replay = _finish_pay(ui.session), _finish_pay(saved.session)
    assert current.gs.to_json() == replay.gs.to_json()
    arisighi = current.gs.lords["arisighi"]
    assert actions.lordship_remaining(current.gs, arisighi) == 0
    assert arisighi.flags["lordship_persist"] == -1
    assert not current.actions(type="levy_transport", lord="arisighi")["entries"]
    host = current.gs.lords["alp_arslan"]
    assert actions.lordship_remaining(current.gs, host) == 3
    for _ in range(2):
        [row] = current.actions(type="pass_step")["entries"]
        current.apply(row["id"])
    assert current.gs.meta.subphase == "levy.call_to_arms"
    assert "lordship_persist" not in current.gs.lords["arisighi"].flags


@pytest.mark.parametrize(("card", "inside"), [("R1", True), ("R10", False)])
def test_repeated_event_excludes_hostile_lords_and_lords_at_a_siege(card, inside):
    ui = _event(card)
    ui.gs.lords["alp_arslan"].besieged = inside
    ui.gs.locales["ani"].siege_markers = 1
    ui.gs.locales["hama"].conquered_side = "roman"
    ui.gs.locales["hama"].conquered_count = 1
    assert _help(ui)["eligible_lords"] == ["arisighi"]
    for lord in ("alp_arslan", "ibn_khan", "artuk_beg"):
        _reject(ui, "bad_event_target", lord)
    assert _choose(ui, "arisighi")["lordship_penalty"] == "arisighi"


@pytest.mark.parametrize("card", ["R1", "R10"])
def test_repeated_event_falls_back_to_in_play_seljuk_lords_when_none_can_muster(card):
    ui = _event(card)
    state = ui.gs
    for lord in state.lords.values():
        if lord.side == "seljuk" and lord.mustered:
            lord.besieged = True
    state.lords["ibn_khan"].cylinder = "removed"
    state.lords["ibn_khan"].mustered = False
    assert "artuk_beg" in _help(ui)["eligible_lords"]
    assert "ibn_khan" not in _help(ui)["eligible_lords"]
    _reject(ui, "missing_or_bad_arg")
    assert _choose(ui, "artuk_beg")["lordship_penalty"] == "artuk_beg"


@pytest.mark.parametrize("card", ["R1", "R10"])
def test_repeated_event_clears_if_no_seljuk_lord_remains_in_play(card):
    ui = _event(card)
    for lord in ui.gs.lords.values():
        if lord.side == "seljuk":
            lord.cylinder = "removed"
            lord.mustered = False
    assert _help(ui)["eligible_lords"] == []
    assert _choose(ui)["no_op"]


@pytest.mark.parametrize("card", ["R1", "R10"])
def test_first_occurrence_still_has_its_printed_effect(card):
    ui = _event(card, repeated=False)
    assert ui.owed == "roman"
    assert "eligible_lords" not in _help(ui)
    ui.apply(_row(ui), parameters={"args": {}})
    result = ui.gs.history[-1]["result"]
    assert card in ui.gs.meta.asterisks_used
    if card == "R1":
        assert "wastage_pending" in result
    else:
        assert result["afsin_fealty"] == 2
