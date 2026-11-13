"""Physical Themata choices for S5 and R13 through the versioned menu."""

import pytest

from seljuk import battle, engine, scenarios
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.session import LLMSession
from seljuk.state import GameState, IllegalAction
from tests.test_phase3b_march import _activate


def _s5():
    gs = scenarios.load_scenario("emperor_and_the_lion", seed=229)
    # Stage the later Levy and let the seeded draw queue the physical S5 card.
    gs.meta.calendar_box = 2
    gs.meta.notes["first_aow_done"] = True
    engine.start_levy(gs)
    assert [p.get("card") for p in gs.meta.pending] == ["S5"]
    return CompactInterface(LLMSession(gs))


def _event(ui, card):
    [row] = ui.actions(type="resolve_event")["entries"]
    assert row["action"]["card"] == card
    return ui.details(row["id"])


def _choose(ui, choice, args):
    ui.apply(choice["id"], parameters={"args": args})
    return ui.gs.history[-1]["result"]


@pytest.mark.parametrize(("args", "code"), [
    ({}, "bad_themata_count"),
    ({"themata": ["Sebasteia"], "unit": "infantry"}, "bad_themata_count"),
    ({"themata": ["Sebasteia", "invalid"], "unit": "infantry"}, "bad_themata_selection"),
    ({"markers": [{"thema": "Sebasteia", "marker_index": 0}] * 2}, "bad_themata_selection"),
    ({"markers": [{"thema": "Sebasteia", "marker_index": 0},
                  {"thema": "Sebasteia", "marker_index": True}]}, "bad_themata_selection"),
    ({"markers": [{"thema": "Sebasteia", "marker_index": 0},
                  {"thema": "Sebasteia", "marker_index": 2, "unit": "infantry"}]},
     "bad_themata_selection"),
])
def test_s5_rejects_incomplete_or_invalid_elections_atomically(args, code):
    ui = _s5()
    choice = _event(ui, "S5")
    assert choice["help"]["required_count"] == 2
    before = ui.gs.to_json()
    version = ui.version
    with pytest.raises(IllegalAction, match=code):
        _choose(ui, choice, args)
    assert ui.gs.to_json() == before
    assert ui.version == version
    with pytest.raises(IllegalAction, match=code):
        engine.apply_action(ui.gs, {"type": "resolve_event", "card": "S5", "args": args})
    assert ui.gs.to_json() == before


def test_s5_removes_mixed_counters_from_one_box_and_keeps_election_order():
    ui = _s5()
    choice = _event(ui, "S5")
    markers = [m for m in choice["help"]["eligible_markers"] if m["thema"] == "Sebasteia"]
    assert [(m["unit"], m["symbols"]) for m in markers] == [
        ("infantry", 1), ("infantry", 2), ("tagmata", 1),
    ]
    before = list(ui.gs.meta.themata_removed)
    result = _choose(ui, choice, {"markers": [markers[1], markers[2]]})
    assert result["removed"] == [
        {"thema": "Sebasteia", "unit": "infantry", "symbols": 2},
        {"thema": "Sebasteia", "unit": "tagmata", "symbols": 1},
    ]
    assert ui.gs.meta.themata_removed[:-2] == before
    assert [m.symbols for m in ui.gs.themata["Sebasteia"]] == [1]
    assert "S5" in ui.gs.meta.asterisks_used and ui.gs.seljuk.draw_deck.count("S5") == 1
    assert not check_invariants(ui.gs)


@pytest.mark.parametrize("available", [0, 1])
def test_s5_requires_every_available_counter_when_fewer_than_two_remain(available):
    ui = _s5()
    for thema, box in ui.gs.themata.items():
        for index, marker in enumerate(box):
            if (thema, index) == ("Sebasteia", 0) and available:
                continue
            marker.home_thema = thema
            ui.gs.meta.themata_removed.append(marker)
        box[:] = box[:available] if thema == "Sebasteia" else []
    choice = _event(ui, "S5")
    assert choice["help"]["required_count"] == available
    if available:
        before = ui.gs.to_json()
        with pytest.raises(IllegalAction, match="bad_themata_count"):
            _choose(ui, choice, {})
        assert ui.gs.to_json() == before
    result = _choose(ui, choice, {"markers": choice["help"]["eligible_markers"]})
    assert len(result["removed"]) == available
    assert not any(ui.gs.themata.values())
    assert "S5" in ui.gs.meta.asterisks_used
    assert not check_invariants(ui.gs)


def _r13():
    ui = _s5()
    # The complete legacy election can still take two distinct native markers.
    _choose(ui, _event(ui, "S5"), {"themata": ["Sebasteia", "Sebasteia"], "unit": "infantry"})
    gs = ui.gs
    # Stage the later R13 draw using the actual removed counters from S5.
    gs.roman.draw_deck.remove("R13")
    gs.meta.pending = [{"type": "event_pending_resolution", "side": "roman", "card": "R13"}]
    return CompactInterface(LLMSession(gs), player="roman")


@pytest.mark.parametrize("symbols", [1, 2])
def test_r13_returns_the_selected_counter_after_save_and_later_musters_its_strength(symbols, tmp_path):
    ui = _r13()
    choice = _event(ui, "R13")
    markers = [m for m in choice["help"]["eligible_markers"] if m["thema"] == "Sebasteia"]
    assert [m["symbols"] for m in markers] == [1, 2]
    selected = next(m for m in markers if m["symbols"] == symbols)
    index = selected["marker_index"]
    original = ui.gs.meta.themata_removed
    remaining = original[:index] + original[index + 1:]
    box = list(ui.gs.themata["Sebasteia"])

    path = tmp_path / "thrakion.json"
    ui.save(path)
    resumed = CompactInterface.load(path)
    assert _event(resumed, "R13") == choice
    args = {"marker_index": index}
    result = _choose(resumed, choice, args)
    assert result == _choose(ui, choice, args)
    assert resumed.gs.to_json() == ui.gs.to_json()
    assert result["symbols"] == symbols
    assert resumed.gs.meta.themata_removed == remaining
    assert resumed.gs.themata["Sebasteia"] == box + [original[index]]
    assert not check_invariants(resumed.gs)
    with pytest.raises(InterfaceError) as rejected:
        _choose(resumed, choice, args)
    assert rejected.value.code == "stale_selection"

    gs = resumed.gs
    gs.meta.subphase, gs.meta.active_player = "levy.muster", "roman"
    gs.lords["romanos_diogenes"].cylinder = "sebasteia"
    move = next(m for m in engine.legal_moves(gs) if m["type"] == "levy_themata"
                and m["marker_index"] == len(box))
    result = engine.apply_action(gs, move)
    assert result["marker"] == {"unit": "infantry", "symbols": symbols}
    assert gs.lords["romanos_diogenes"].themata_on_mat[-1].unit_count() == symbols
    assert not check_invariants(gs)


@pytest.mark.parametrize("args", [
    {"marker_index": -1}, {"marker_index": 99}, {"marker_index": False},
    {"marker_index": 2, "symbols": 1}, {"thema": "invalid"},
])
def test_r13_rejects_bad_selection_and_preserves_event(args):
    ui = _r13()
    choice = _event(ui, "R13")
    before = ui.gs.to_json()
    with pytest.raises(IllegalAction, match="bad_themata_index"):
        _choose(ui, choice, args)
    assert ui.gs.to_json() == before
    assert _event(ui, "R13") == choice


def test_returned_double_marker_supplies_two_garrison_infantry():
    ui = _r13()
    choice = _event(ui, "R13")
    index = next(m["marker_index"] for m in choice["help"]["eligible_markers"]
                 if m["thema"] == "Sebasteia" and m["symbols"] == 2)
    _choose(ui, choice, {"marker_index": index})
    gs = GameState.from_json(ui.gs.to_json())
    # Stage a later Siege at Sebasteia with native Lord mats and the returned counter.
    gs.lords["alp_arslan"].cylinder = "sebasteia"
    _activate(gs, "alp_arslan")
    gs.locales["sebasteia"].siege_markers = 1
    gs.meta.pending = [{"type": "assign_themata_defenders", "locale": "sebasteia"}]
    engine.apply_action(gs, {"type": "assign_themata_defenders",
                             "markers": [len(gs.themata["Sebasteia"]) - 1]})
    assert battle._build_garrison(gs, "sebasteia") == {"militia": 1, "infantry": 2}
    storm = engine.apply_action(gs, {"type": "cmd_storm", "lord": "alp_arslan"})["storm"]
    assert any(s["step"] == "def_missile_garrison" and s["hits"] == 2 for s in storm["strikes"])
    assert not check_invariants(gs)
