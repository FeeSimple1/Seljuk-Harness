"""Action dispatcher + Levy step machine (Phase 2).

`apply_action(gs, action)` validates a submitted action against the rules,
mutates the state, logs it to history, and returns a structured result (dice
rolled, effects). `legal_moves(gs)` enumerates the actions the active player
may currently take. These two MUST stay in agreement — every IllegalAction a
handler can raise is a candidate gap in the enumerator
(CROSS_PROJECT_LESSONS.md sections 1-2); the Phase 2 test suite includes a
round-trip sweep.

Levy sequence (3.0): Arts of War (3.1) -> Pay (3.2) -> Disband (3.3) ->
Muster (3.4) -> Call to Arms (3.5). Within each interactive step the Seljuk
player acts, then the Roman player (2.2.4); a side ends its participation with
a `pass_step` action. Disband is automatic; Arts of War draw is engine-driven.
"""
from __future__ import annotations

from typing import Any, Callable

from . import actions, campaign
from .rng import DiceRoller
from .state import GameState, IllegalAction

# Order of Levy steps. (Arts of War draw and Disband are resolved automatically
# on entry; Pay, Muster, and Call to Arms are interactive.)
LEVY_STEPS = ["arts_of_war", "pay", "disband", "muster", "call_to_arms"]
_INTERACTIVE = {"pay", "muster", "call_to_arms"}
SIDES = ["seljuk", "roman"]  # Seljuk first (2.2.4)


def roller_for(gs: GameState) -> DiceRoller:
    r = DiceRoller(seed=gs.meta.seed)
    if gs.meta.rng_state is not None:
        # JSON round-trips tuples to lists; Random.setstate needs the nested
        # element to be a tuple.
        st = gs.meta.rng_state
        r.set_state((st[0], tuple(st[1]), st[2]))
    return r


def _save_roller(gs: GameState, r: DiceRoller) -> None:
    st = r.get_state()
    gs.meta.rng_state = [st[0], list(st[1]), st[2]]


# --- dispatch table ---------------------------------------------------------
# Each handler: fn(gs, action, roller) -> dict result. Handlers mutate gs.
_HANDLERS: dict[str, Callable[[GameState, dict, DiceRoller], dict]] = {
    "pay": actions.h_pay,
    "levy_lord": actions.h_levy_lord,
    "levy_transport": actions.h_levy_transport,
    "levy_capability": actions.h_levy_capability,
    "levy_vassal": actions.h_levy_vassal,
    "levy_themata": actions.h_levy_themata,
    "deploy_capability": actions.h_deploy_capability,
    "cta_loot": actions.h_cta_loot,
    "cta_strategic_objective": actions.h_cta_strategic_objective,
    "pass_step": actions.h_pass_step,
}

_CAMPAIGN_HANDLERS: dict[str, Callable[[GameState, dict, DiceRoller], dict]] = {
    "build_plan": campaign.h_build_plan,
    "cmd_pass": campaign.h_cmd_pass,
    "end_activation": campaign.h_end_activation,
    "cmd_tax": campaign.h_cmd_tax,
    "cmd_forage": campaign.h_cmd_forage,
    "cmd_ravage": campaign.h_cmd_ravage,
    "resolve_ravage_defence": campaign.h_resolve_ravage_defence,
    "cmd_supply": campaign.h_cmd_supply,
    "cmd_recruit": campaign.h_cmd_recruit,
    "cmd_march": campaign.h_cmd_march,
    "respond_approach": campaign.h_respond_approach,
    "besiege_bypass": campaign.h_besiege_bypass,
    "cmd_siege": campaign.h_cmd_siege,
    "assign_themata_defenders": campaign.h_assign_themata_defenders,
    "cmd_storm": campaign.h_cmd_storm,
    "cmd_sally": campaign.h_cmd_sally,
}


def _handlers_for_phase(phase: str) -> dict[str, Callable[[GameState, dict, DiceRoller], dict]]:
    if phase == "levy":
        return _HANDLERS
    if phase == "campaign":
        return _CAMPAIGN_HANDLERS
    return {}


def apply_action(gs: GameState, action: dict[str, Any]) -> dict[str, Any]:
    atype = action.get("type")
    table = _handlers_for_phase(gs.meta.phase)
    if atype not in table:
        raise IllegalAction("unknown_action",
                            f"no handler for action type {atype!r} in phase {gs.meta.phase}")
    roller = roller_for(gs)
    result = table[atype](gs, action, roller)
    _save_roller(gs, roller)
    gs.history.append({"action": action, "result": result})
    return result


def legal_moves(gs: GameState) -> list[dict[str, Any]]:
    if gs.meta.phase == "campaign":
        return campaign.legal_moves_campaign(gs)
    if gs.meta.phase != "levy":
        return []
    step = gs.meta.subphase
    if step == "levy.pay":
        moves = actions.enumerate_pay(gs)
        moves.append({"type": "pass_step", "_desc": "Finish Pay for this side (3.2)"})
        return moves
    if step == "levy.muster":
        moves = actions.enumerate_muster(gs)
        moves.append({"type": "pass_step", "_desc": "Finish Muster for this side (3.4)"})
        return moves
    if step == "levy.call_to_arms":
        moves = actions.enumerate_call_to_arms(gs)
        moves.append({"type": "pass_step", "_desc": "Decline a Call to Arms option for this side (3.5)"})
        return moves
    return []


# --- Levy step machine ------------------------------------------------------

def start_levy(gs: GameState) -> None:
    """Enter the Levy phase at its first step, resolving automatic steps."""
    gs.meta.phase = "levy"
    _enter_step(gs, LEVY_STEPS[0])


def _enter_step(gs: GameState, step: str) -> None:
    gs.meta.subphase = f"levy.{step}"
    gs.meta.active_player = "seljuk"
    gs.meta.levy_step_passed = {}
    if step == "disband":
        roller = roller_for(gs)
        for side in SIDES:
            actions.resolve_disband(gs, side)
        _save_roller(gs, roller)
        _advance_step(gs)
    elif step == "muster":
        actions.reset_muster_segment(gs)
    elif step == "arts_of_war":
        roller = roller_for(gs)
        actions.resolve_arts_of_war(gs, roller)
        _save_roller(gs, roller)
        _advance_step(gs)


def _advance_step(gs: GameState) -> None:
    cur = (gs.meta.subphase or "levy.arts_of_war").split(".", 1)[1]
    idx = LEVY_STEPS.index(cur)
    if idx + 1 < len(LEVY_STEPS):
        _enter_step(gs, LEVY_STEPS[idx + 1])
    else:
        gs.meta.subphase = "levy.complete"


def note_pass(gs: GameState) -> None:
    """Record that the active side has finished the current interactive step;
    pass to the other side, or advance the step when both have passed."""
    gs.meta.levy_step_passed[gs.meta.active_player] = True
    other = "roman" if gs.meta.active_player == "seljuk" else "seljuk"
    if gs.meta.levy_step_passed.get(other):
        _advance_step(gs)
    else:
        gs.meta.active_player = other
