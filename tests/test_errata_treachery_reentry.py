"""Errata (Rulebook p6, 1.4.2 Ex#3): a Lord who switches sides via a failed
Loyalty Check and goes off-map rejoins under his new owner, placed at a free
Seat at the start of the FOLLOWING season's Levy, before the Pay phase."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, actions, engine


def _on_map_roman_lord(gs):
    lid = "chatatourios"
    lord = gs.lords[lid]
    seat = sd_seat(lid)
    lord.side = "roman"
    lord.mustered = True
    lord.cylinder = seat
    return lid, lord, seat


def sd_seat(lid):
    from seljuk import static_data as sd
    return sd.lord(lid)["seats"][0]


def test_switch_sends_lord_offboard_with_reentry_flag():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    lid, lord, _ = _on_map_roman_lord(gs)
    gs.meta.calendar_box = 4
    actions._switch_side(gs, lord)
    assert lord.side == "seljuk"
    assert lord.cylinder == "offboard"
    assert lord.mustered is False
    assert lord.flags.get("treachery_reentry_box") == 4


def test_no_reentry_in_same_season():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    lid, lord, _ = _on_map_roman_lord(gs)
    gs.meta.calendar_box = 4
    actions._switch_side(gs, lord)
    # Same season: must NOT re-enter yet.
    placed = actions.resolve_treachery_reentry(gs)
    assert placed == []
    assert lord.cylinder == "offboard"


def test_reentry_next_season_places_at_seat_under_new_owner():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    lid, lord, seat = _on_map_roman_lord(gs)
    gs.meta.calendar_box = 4
    actions._switch_side(gs, lord)            # now Seljuk, offboard
    gs.meta.calendar_box = 5                  # following season's Levy
    placed = actions.resolve_treachery_reentry(gs)
    assert any(p["lord"] == lid for p in placed)
    assert lord.mustered is True
    assert lord.side == "seljuk"
    assert lord.cylinder != "offboard"
    assert "treachery_reentry_box" not in lord.flags


def test_reentry_runs_before_pay_in_levy_step_machine():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    lid, lord, _ = _on_map_roman_lord(gs)
    gs.meta.calendar_box = 4
    actions._switch_side(gs, lord)
    gs.meta.calendar_box = 5
    # Entering the Pay step should re-place the switched Lord.
    engine._enter_step(gs, "pay")
    assert gs.meta.subphase == "levy.pay"
    assert lord.mustered is True
    assert lord.cylinder != "offboard"
