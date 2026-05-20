"""Phase 1 scenario loaders + victory math (Rules 5.1-5.3, section 7)."""
import json
from pathlib import Path

import pytest

from seljuk import scenarios as S, static_data as sd

DATA = Path(sd.__file__).resolve().parent / "data" / "scenarios"


@pytest.mark.parametrize("name", S.SCENARIOS)
def test_scenario_loads_with_16_lords(name):
    gs = S.load_scenario(name, seed=1)
    assert len(gs.lords) == 16
    statuses = {"map": 0, "calendar": 0, "removed": 0}
    for l in gs.lords.values():
        if l.mustered:
            statuses["map"] += 1
        elif l.cylinder == "calendar":
            statuses["calendar"] += 1
        elif l.cylinder == "removed":
            statuses["removed"] += 1
    assert sum(statuses.values()) == 16


@pytest.mark.parametrize("name", S.SCENARIOS)
def test_score_matches_printed_starting_vp(name):
    """5.1: recomputed VP from markers must equal the printed scenario starting VP."""
    gs = S.load_scenario(name)
    expected = json.loads((DATA / f"{name}.json").read_text())["starting_vp"]
    assert S.score(gs) == expected


@pytest.mark.parametrize("name", S.SCENARIOS)
def test_scenario_round_trips_through_json(name):
    gs = S.load_scenario(name)
    from seljuk.state import GameState
    gs2 = GameState.from_json(gs.to_json())
    assert S.score(gs2) == S.score(gs)
    assert gs2.meta.calendar_box == gs.meta.calendar_box


def test_manzikert_errata_psiloi_goes_to_board_edge():
    """Errata (1071 setup): PSILOI is an ALL Capability -> board edge, NOT on Andronikos."""
    gs = S.load_scenario("manzikert")
    assert "R25" in gs.roman.capabilities_in_play
    assert "R25" not in gs.lords["andronikos_doukas"].capabilities
    assert gs.lords["andronikos_doukas"].capabilities == ["R13"]  # Syndosis only


def test_manzikert_savtekin_vassal_levied_adds_forces():
    """Section 7: Sav-Tekin starts with the 2x Infantry Vassal Levied (2 starting + 2 = 4)."""
    gs = S.load_scenario("manzikert")
    assert gs.lords["sav_tekin"].forces.get("infantry") == 4
    assert any(v.levied and v.forces == {"infantry": 2} for v in gs.lords["sav_tekin"].vassals)


def test_levied_capabilities_removed_from_draw_deck():
    """3.1.1 / 3.4.4: a Capability in play is not in the draw deck."""
    gs = S.load_scenario("manzikert")
    assert "S8" not in gs.seljuk.draw_deck       # Marwanid Alliance (board edge)
    assert "S4" not in gs.seljuk.draw_deck        # Shock Tactics on Alp Arslan
    assert "R25" not in gs.roman.draw_deck        # Psiloi (board edge)


def test_skip_first_levy_scenarios_start_in_campaign():
    assert S.load_scenario("year_of_treacherous_ambition").meta.phase == "campaign"
    assert S.load_scenario("manzikert").meta.phase == "campaign"
    assert S.load_scenario("emperor_and_the_lion").meta.phase == "levy"


def test_campaign_victory_when_a_side_has_no_mustered_lords():
    """5.2: a side with no Mustered Lords during Campaign loses immediately."""
    gs = S.load_scenario("manzikert")
    gs.meta.phase = "campaign"
    for l in gs.lords.values():
        if l.side == "seljuk":
            l.mustered = False
    assert S.campaign_victory(gs) == "roman"


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        S.load_scenario("not_a_scenario")
