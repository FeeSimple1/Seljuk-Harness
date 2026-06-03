"""Audit tidy: S9 Imperial Rivalry -- Romans must attempt to Muster Andronikos
Doukas once each Levy if Ready (else they may not pass the Muster step)."""
import pytest
from seljuk import scenarios as S, actions, engine
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _muster(gs):
    gs.roman.capabilities_in_play = ["S9"]            # Imperial Rivalry
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = "melitene"
    rom.service_box = 8
    an = gs.lords["andronikos_doukas"]; an.mustered = False
    an.cylinder = "calendar"; an.cylinder_calendar_box = 1   # Ready
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.muster"
    gs.meta.active_player = "roman"; gs.meta.levy_step_passed = {}
    gs.meta.calendar_box = 1
    return gs


def test_roman_cannot_pass_muster_until_andronikos_attempted():
    gs = _muster(S.load_scenario("emperor_and_the_lion"))
    assert any(m.get("type") == "levy_lord" and m.get("target") == "andronikos_doukas"
               for m in actions.enumerate_muster(gs))
    with pytest.raises(IllegalAction) as e:
        engine.apply_action(gs, {"type": "pass_step"})
    assert e.value.code == "imperial_rivalry"


def test_attempt_satisfies_obligation_then_pass_allowed():
    gs = _muster(S.load_scenario("emperor_and_the_lion"))
    engine.apply_action(gs, {"type": "levy_lord", "levyer": "romanos_diogenes",
                             "target": "andronikos_doukas"})
    assert gs.meta.notes.get("imperial_rivalry_attempted") is True
    engine.apply_action(gs, {"type": "pass_step"})   # now permitted


def test_no_obligation_without_capability():
    gs = _muster(S.load_scenario("emperor_and_the_lion"))
    gs.roman.capabilities_in_play = []   # no Imperial Rivalry
    engine.apply_action(gs, {"type": "pass_step"})   # passes freely


def test_reset_rearms_obligation_each_levy():
    gs = _muster(S.load_scenario("emperor_and_the_lion"))
    gs.meta.notes["imperial_rivalry_attempted"] = True
    actions.reset_muster_segment(gs)
    assert "imperial_rivalry_attempted" not in gs.meta.notes
