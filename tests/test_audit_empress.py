"""Audit fix: R12 Empress Eudokia Makrembolitissa (3.5.1.2) Call-to-Arms option."""
import pytest
from seljuk import scenarios as S, engine, actions
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _roman_cta():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.roman.capabilities_in_play = ["R12"]
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.call_to_arms"
    gs.meta.active_player = "roman"; gs.meta.levy_step_passed = {}
    return gs


def test_empress_enumerated_and_shift_cylinder():
    gs = _roman_cta()
    man = gs.lords["manuel_komnenos"]; man.mustered = False
    man.cylinder = "calendar"; man.cylinder_calendar_box = 5
    types = {(m["type"], m.get("effect")) for m in actions.enumerate_call_to_arms(gs)}
    assert ("cta_empress", "shift_cylinder") in types
    engine.apply_action(gs, {"type": "cta_empress", "mode": "use", "effect": "shift_cylinder",
                             "lord": "manuel_komnenos", "direction": "left"})
    assert gs.lords["manuel_komnenos"].cylinder_calendar_box == 4
    assert gs.meta.notes["empress_token"] == "constantinople"


def test_empress_recharge_then_transfer_service():
    gs = _roman_cta()
    gs.meta.notes["empress_token"] = "constantinople"
    # Only the place-on-card option is available while the token is away.
    types = {m.get("mode") for m in actions.enumerate_call_to_arms(gs) if m["type"] == "cta_empress"}
    assert types == {"place_on_card"}
    engine.apply_action(gs, {"type": "cta_empress", "mode": "place_on_card"})
    assert gs.meta.notes["empress_token"] == "card"
    # Now transfer 1 Service from Manuel to Romanos.
    man = gs.lords["manuel_komnenos"]; man.service_box = 8
    rom = gs.lords["romanos_diogenes"]; rom.service_box = 6
    gs.meta.active_player = "roman"; gs.meta.levy_step_passed = {}
    engine.apply_action(gs, {"type": "cta_empress", "mode": "use", "effect": "transfer_service",
                             "lord": "manuel_komnenos"})
    assert man.service_box == 7 and rom.service_box == 7
    assert gs.meta.notes["empress_token"] == "constantinople"


def test_empress_use_requires_token_on_card():
    gs = _roman_cta()
    gs.meta.notes["empress_token"] = "constantinople"
    with pytest.raises(IllegalAction):
        actions.h_cta_empress(gs, {"mode": "use", "effect": "shift_cylinder", "lord": "manuel_komnenos"}, DiceRoller(1))
