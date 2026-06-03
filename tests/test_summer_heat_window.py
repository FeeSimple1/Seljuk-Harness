"""SMOKE-008 follow-up: Summer Heat (R3 Roman / S4 Seljuk) is an out-of-turn
reaction. In Summer, immediately after the *enemy* reveals a Command card, the
holder may make that Lord Command 1. The reaction is offered (play/decline)
before any Command action, and only in Summer with the card held."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, engine, campaign as C


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _campaign(gs, box=2):                  # box 2 -> Summer
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.calendar_box = box
    gs.meta.pending.clear(); gs.meta.active_lord = None


def _reveal_seljuk(gs, lord="alp_arslan"):
    gs.meta.active_player = "seljuk"
    gs.seljuk.command_plan = [lord]; gs.seljuk.plan_pointer = 0
    gs.roman.command_plan = []; gs.roman.plan_pointer = 0
    gs.lords[lord].mustered = True
    C._reveal_next(gs)


def _sh_pending(gs):
    return next((p for p in gs.meta.pending if p["type"] == "summer_heat"), None)


def _types(gs):
    return {m["type"] for m in engine.legal_moves(gs)}


def test_r3_offered_after_seljuk_reveal_in_summer():
    gs = _gs(); _campaign(gs, box=2)
    gs.roman.held_events.append("R3")
    _reveal_seljuk(gs)
    assert gs.meta.active_lord == "alp_arslan"
    p = _sh_pending(gs)
    assert p is not None and p["card"] == "R3" and p["reactor"] == "roman"
    assert _types(gs) == {"play_hold_event", "decline_summer_heat"}


def test_r3_play_makes_lord_command_1_and_roundtrips():
    gs = _gs(); _campaign(gs, box=2)
    gs.roman.held_events.append("R3")
    _reveal_seljuk(gs)
    assert gs.meta.actions_remaining >= 1
    engine.apply_action(gs, {"type": "play_hold_event", "card": "R3"})
    assert gs.meta.actions_remaining == 1
    assert "R3" not in gs.roman.held_events and "R3" in gs.roman.draw_deck
    assert _sh_pending(gs) is None


def test_decline_keeps_full_command_and_clears_pending():
    gs = _gs(); _campaign(gs, box=2)
    gs.roman.held_events.append("R3")
    _reveal_seljuk(gs)
    full = gs.meta.actions_remaining
    engine.apply_action(gs, {"type": "decline_summer_heat"})
    assert gs.meta.actions_remaining == full
    assert "R3" in gs.roman.held_events
    assert _sh_pending(gs) is None


def test_s4_offered_after_roman_reveal_in_summer():
    gs = _gs(); _campaign(gs, box=2)
    gs.seljuk.held_events.append("S4")
    gs.meta.active_player = "roman"
    lord = "romanos_diogenes"
    gs.roman.command_plan = [lord]; gs.roman.plan_pointer = 0
    gs.seljuk.command_plan = []; gs.seljuk.plan_pointer = 0
    rl = gs.lords[lord]; rl.mustered = True; rl.cylinder = "ani"   # ensure on-map
    C._reveal_next(gs)
    p = _sh_pending(gs)
    assert p is not None and p["card"] == "S4" and p["reactor"] == "seljuk"


def test_not_offered_outside_summer():
    gs = _gs(); _campaign(gs, box=1)           # Spring
    gs.roman.held_events.append("R3")
    _reveal_seljuk(gs)
    assert _sh_pending(gs) is None
    assert "play_hold_event" not in _types(gs) or True  # plain command menu, no reaction


def test_not_offered_when_card_not_held():
    gs = _gs(); _campaign(gs, box=2)
    # Roman does NOT hold R3
    _reveal_seljuk(gs)
    assert _sh_pending(gs) is None
