"""Showdown self-play regressions (seed 20261016), extended to other scenarios.

The saved position is immediately before the previously accepted fourth SO
marker. These checks ensure both menu completeness and handler enforcement.
"""
from collections import Counter
from pathlib import Path

import pytest

from seljuk import actions, battle, engine, events, scenarios, static_data as sd
from seljuk.invariants import check_invariants
from seljuk.rng import DiceRoller
from seljuk.state import GameState, IllegalAction

FIXTURE = Path(__file__).parent / "fixtures" / "showdown_rules_20261016" / "so-before-fourth.json"


def showdown_checkpoint():
    return GameState.from_json(FIXTURE.read_text())


def _so_on_board(gs):
    return (sum(bool(l.strategic_objective) for l in gs.lords.values())
            + sum(bool(st.strategic_objective) for st in gs.locales.values()))


def _physical_so(gs):
    return (gs.holding_boxes.constantinople_strategic_objectives_available
            + _so_on_board(gs)
            + gs.meta.notes.get("strategic_objectives_removed_from_play", 0)
            + gs.meta.notes.get("strategic_objectives_claimed", 0))


def _marker_inventory(gs):
    tally = Counter()
    for home, markers in gs.themata.items():
        for m in markers:
            tally[(home, m.unit, m.symbols)] += 1
    for lord in gs.lords.values():
        for m in lord.themata_on_mat:
            tally[(m.home_thema, m.unit, m.symbols)] += 1
    for st in gs.locales.values():
        for m in st.themata_defending:
            tally[(m.home_thema, m.unit, m.symbols)] += 1
    for m in gs.meta.themata_removed:
        tally[(m.home_thema, m.unit, m.symbols)] += 1
    return tally


def _go_to_roman_cta(gs):
    gs.meta.phase = "levy"
    gs.meta.subphase = "levy.call_to_arms"
    gs.meta.active_player = "roman"
    gs.meta.pending = []
    gs.lords["manuel_komnenos"].mustered = True
    gs.lords["manuel_komnenos"].cylinder = "to_constantinople"
    return gs


def _take(gs):
    return engine.apply_action(gs, {"type": "cta_strategic_objective", "mode": "take"})


def _place(gs, target):
    return engine.apply_action(gs, {"type": "cta_strategic_objective", "mode": "place", "target": target})


def test_sd01_recorded_fourth_so_missing_from_raw_and_validated_menus():
    gs = showdown_checkpoint()
    assert gs.holding_boxes.constantinople_strategic_objectives_available == 2
    assert _so_on_board(gs) == 1
    assert scenarios.strategic_objectives_in_supply(gs) == 0
    for moves in (engine.legal_moves(gs), engine.validated_legal_moves(gs)[0]):
        assert not any(m["type"] == "cta_strategic_objective" and m["mode"] == "take" for m in moves)
    # Placing an AVAILABLE marker on an unmarked target remains discoverable.
    assert any(m["type"] == "cta_strategic_objective" and m["mode"] == "place" for m in engine.legal_moves(gs))


def test_sd01_recorded_fourth_so_rejected_atomically_even_after_reload():
    gs = GameState.from_json(showdown_checkpoint().to_json())
    snapshot = gs.to_json()
    with pytest.raises(IllegalAction, match="supply"):
        _take(gs)
    assert gs.to_json() == snapshot


@pytest.mark.parametrize("target", ["artuk_beg", "ani"])
def test_sd02_duplicate_placement_lord_or_stronghold_rejected_atomically(target):
    gs = showdown_checkpoint()
    if target == "ani":
        gs.locales[target].strategic_objective = True
    assert target not in [m.get("target") for m in engine.legal_moves(gs)
                          if m.get("type") == "cta_strategic_objective" and m.get("mode") == "place"]
    snapshot = gs.to_json()
    with pytest.raises(IllegalAction, match="already"):
        _place(gs, target)
    assert gs.to_json() == snapshot


@pytest.mark.parametrize("sc", scenarios.SCENARIOS)
def test_sd03_every_scenario_accounts_for_all_31_physical_themata_at_setup(sc):
    gs = scenarios.load_scenario(sc, seed=20261016)
    expected = Counter((home, m["unit"], m["symbols"])
                       for home, arr in sd.themata()["baseline_1068"].items()
                       for m in arr)
    assert sum(expected.values()) == 31
    assert _marker_inventory(gs) == expected
    removed_by_setup = sum(len(arr) for arr in sd.themata()["scenario_removals"].get(sc, {}).values())
    assert len(gs.meta.themata_removed) == removed_by_setup
    assert all(m.home_thema for m in gs.meta.themata_removed)
    assert _marker_inventory(GameState.from_json(gs.to_json())) == expected


def test_sd03_showdown_nine_setup_removals_are_retained_with_double_marker():
    gs = scenarios.load_scenario("showdown_in_anatolia", seed=20261016)
    removed = Counter((m.home_thema, m.unit, m.symbols) for m in gs.meta.themata_removed)
    assert sum(removed.values()) == 9
    assert removed[("Iberia", "tagmata", 1)] == 1
    assert removed[("Melitene", "infantry", 2)] == 1
    assert not gs.themata["Iberia"]


def test_sd03_r13_can_return_setup_removed_iberia_tagmata_without_fabrication():
    gs = scenarios.load_scenario("showdown_in_anatolia", seed=20261016)
    original = _marker_inventory(gs)
    gs.meta.pending = [{"type": "event_pending_resolution", "side": "roman",
                        "card": "R13", "tags": ["immediate"], "_owed_by": "roman"}]
    gs.meta.phase, gs.meta.subphase, gs.meta.active_player = "levy", "levy.pay", "roman"
    result = engine.apply_action(gs, {"type": "resolve_event", "card": "R13",
                                       "args": {"thema": "Iberia", "unit": "tagmata"}})
    assert result["returned"] == {"thema": "Iberia", "unit": "tagmata"}
    assert len(gs.themata["Iberia"]) == 1
    assert gs.themata["Iberia"][0].home_thema == "Iberia"
    assert _marker_inventory(gs) == original


@pytest.mark.parametrize("sc", scenarios.SCENARIOS)
def test_so_supply_counts_setup_removals_and_initial_placements(sc):
    gs = scenarios.load_scenario(sc)
    assert _physical_so(gs) + scenarios.strategic_objectives_in_supply(gs) == 3
    assert 0 <= scenarios.strategic_objectives_in_supply(gs) <= 3


def test_so_exhausted_supply_remains_exhausted_after_placing_all_three():
    gs = _go_to_roman_cta(scenarios.load_scenario("showdown_in_anatolia"))
    for target in ("alp_arslan", "emir_of_arran", "ani"):
        assert scenarios.strategic_objectives_in_supply(gs) > 0
        _take(gs)
        _go_to_roman_cta(gs)
        _place(gs, target)
        _go_to_roman_cta(gs)
    assert _physical_so(gs) == 3 and scenarios.strategic_objectives_in_supply(gs) == 0
    assert not any(m.get("mode") == "take" and m["type"] == "cta_strategic_objective"
                   for m in engine.legal_moves(gs))
    with pytest.raises(IllegalAction, match="supply"):
        _take(gs)


@pytest.mark.parametrize("claim", ["disband", "conquer", "ruin"])
def test_so_claimed_counter_cannot_be_minted_again(claim):
    gs = _go_to_roman_cta(scenarios.load_scenario("showdown_in_anatolia"))
    for _ in range(3):
        _take(gs)
        _go_to_roman_cta(gs)
    gs.holding_boxes.constantinople_strategic_objectives_available -= 1
    if claim == "disband":
        gs.lords["alp_arslan"].strategic_objective = True
        actions._disband_beyond(gs, gs.lords["alp_arslan"])
    else:
        gs.locales["ani"].strategic_objective = True
        (battle.conquer(gs, "ani", "roman") if claim == "conquer"
         else battle.ruin(gs, "ani"))
    assert gs.meta.notes["strategic_objectives_claimed"] == 1
    assert gs.holding_boxes.constantinople_roman_vp_markers >= 1
    assert scenarios.strategic_objectives_in_supply(gs) == 0
    _go_to_roman_cta(gs)
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="supply"):
        _take(gs)
    assert gs.to_json() == before
    assert _physical_so(gs) == 3


def test_so_r20_return_to_available_does_not_create_extra_supply():
    gs = _go_to_roman_cta(scenarios.load_scenario("showdown_in_anatolia"))
    for _ in range(3):
        _take(gs)
        _go_to_roman_cta(gs)
    gs.holding_boxes.constantinople_strategic_objectives_available -= 1
    gs.locales["khliat"].strategic_objective = True
    assert scenarios.strategic_objectives_in_supply(gs) == 0
    events._ev_armenian_resistance(gs, {"locale": "khliat"}, DiceRoller(2))
    assert not gs.locales["khliat"].strategic_objective
    assert gs.holding_boxes.constantinople_strategic_objectives_available == 3
    assert scenarios.strategic_objectives_in_supply(gs) == 0


def test_so_invariant_detects_impossible_fourth_marker():
    gs = showdown_checkpoint()
    gs.holding_boxes.constantinople_strategic_objectives_available += 1
    assert scenarios.strategic_objectives_in_supply(gs) == -1
    assert any("Strategic Objective" in v for v in check_invariants(gs))
