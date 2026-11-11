"""Conditional Commander eligibility and promotion during a Campaign."""

import pytest

from seljuk import actions, engine, scenarios
from seljuk.state import IllegalAction
from tests.test_round7_combat import _dispatch

ROMANOS = "romanos_diogenes"
MANUEL = "manuel_komnenos"
NIKEPHOROS = "nikephoros_bryennios"


def _roman_plan():
    state = scenarios.load_scenario("specter_of_norman_betrayal", seed=1)
    state.meta.phase, state.meta.subphase = "levy", "levy.muster"
    state.meta.active_player = "roman"
    state.meta.pending = []
    result = _dispatch(state, {"type": "levy_lord", "levyer": ROMANOS,
                               "target": MANUEL, "seat": "to_constantinople"})
    assert result["success"] and result["roll"] == 2
    state.meta.phase, state.meta.subphase = "campaign", "campaign.plan"
    state.meta.active_player, state.meta.plan_submitted = "seljuk", {}
    state.lords[NIKEPHOROS].service_box = state.meta.calendar_box + 1
    _dispatch(state, {"type": "build_plan", "side": "seljuk",
                      "cards": ["sav_tekin"] * 2 + ["no_command"] * 5})
    return state


def _plan_action(upper, lower):
    return {"type": "build_plan", "side": "roman",
            "cards": [MANUEL, NIKEPHOROS] + ["no_command"] * 5,
            "lieutenants": [{"lieutenant": upper, "lower_lord": lower}]}


def _pairs(state):
    plan = next(m for m in engine.legal_moves(state) if m["type"] == "build_plan")
    return plan["_lieutenant_options"]


@pytest.mark.parametrize(("upper", "lower"), [(MANUEL, NIKEPHOROS), (NIKEPHOROS, MANUEL)])
def test_manuel_can_stack_until_romanos_disbands(upper, lower):
    state = _roman_plan()
    action = _plan_action(upper, lower)
    assert not actions.is_commander(state, MANUEL)
    assert action["lieutenants"][0] in _pairs(state)
    _dispatch(state, action)
    assert state.lords[upper].lower_lord == lower
    assert state.lords[lower].lieutenant_of == upper

    state.lords[ROMANOS].service_box = state.meta.calendar_box
    _dispatch(state, {"type": "end_activation"})
    while state.meta.subphase == "campaign.fpd_pay":
        _dispatch(state, {"type": "fpd_done"})
    assert state.lords[ROMANOS].cylinder == "calendar"
    assert actions.is_commander(state, MANUEL)
    assert all(state.lords[lid].mustered and state.lords[lid].lower_lord is None
               and state.lords[lid].lieutenant_of is None for lid in (upper, lower))


@pytest.mark.parametrize("commander", [ROMANOS, MANUEL])
def test_current_commander_cannot_take_either_position_in_a_stack(commander):
    state = _roman_plan()
    if commander == MANUEL:
        state.lords[ROMANOS].service_box = state.meta.calendar_box
        actions.resolve_disband(state, "roman")
    assert actions.is_commander(state, commander)
    assert all(commander not in pair.values() for pair in _pairs(state))
    before = state.to_json()
    for upper, lower in ((commander, NIKEPHOROS), (NIKEPHOROS, commander)):
        with pytest.raises(IllegalAction) as exc:
            engine.apply_action(state, _plan_action(upper, lower))
        assert exc.value.code == "commander_lieutenant"
        assert state.to_json() == before
