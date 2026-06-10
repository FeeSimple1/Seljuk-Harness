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

from . import actions, campaign, events
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
    "muster_restore": actions.h_muster_restore,
    "deploy_capability": actions.h_deploy_capability,
    "cta_loot": actions.h_cta_loot,
    "cta_strategic_objective": actions.h_cta_strategic_objective,
    "cta_marwanid": actions.h_cta_marwanid,
    "cta_marwanid_bank": actions.h_cta_marwanid_bank,
    "cta_deep_raids": actions.h_cta_deep_raids,
    "cta_empress": actions.h_cta_empress,
    "pass_step": actions.h_pass_step,
    "resolve_event": actions.h_resolve_event,
    "discard_imperial_coffers": campaign.h_discard_imperial_coffers,
    "pass_imperial_coffers": campaign.h_pass_imperial_coffers,
    "discard_nomisma": actions.h_discard_nomisma,
    "play_hold_event": actions.h_play_hold_event,
}

_CAMPAIGN_HANDLERS: dict[str, Callable[[GameState, dict, DiceRoller], dict]] = {
    "build_plan": campaign.h_build_plan,
    "cmd_pass": campaign.h_cmd_pass,
    "cmd_take_gift_coin": campaign.h_cmd_take_gift_coin,
    "cmd_fort": campaign.h_cmd_fort,
    "cmd_encamp": campaign.h_cmd_encamp,
    "cmd_sortie": campaign.h_cmd_sortie,
    "end_activation": campaign.h_end_activation,
    "pay": actions.h_pay,                 # 4.6.2 campaign Feed/Pay/Disband Pay
    "fpd_done": campaign.h_fpd_done,
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
    "resolve_event": actions.h_resolve_event,
    "resolve_loyalty": campaign.h_resolve_loyalty,
    "basil_response": campaign.h_basil_response,
    "decline_summer_heat": campaign.h_decline_summer_heat,
    "play_kleisourai": campaign.h_play_kleisourai,
    "decline_kleisourai": campaign.h_decline_kleisourai,
    "winter_activate": campaign.h_winter_activate,
    "winter_proceed": campaign.h_winter_proceed,
    "discard_imperial_coffers": campaign.h_discard_imperial_coffers,
    "play_hold_event": actions.h_play_hold_event,
}


def _handlers_for_phase(phase: str) -> dict[str, Callable[[GameState, dict, DiceRoller], dict]]:
    if phase == "levy":
        return _HANDLERS
    if phase in ("campaign", "winter"):
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


# Moves the consumer must parameterise before they can be applied (they carry
# only `_`-prefixed hints, not a ready action), so they cannot be probed as-is
# and are kept marked unvalidated (Nevsky advisory §2).
_PALETTE_TEMPLATES = {"build_plan", "resolve_event", "respond_approach",
                      "assign_themata_defenders"}


def validated_legal_moves(gs: GameState) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Agent-facing palette (Nevsky advisory §2): probe every concrete enumerated
    move on a discarded deep copy and DROP any the handler rejects, so an agent
    never sees an over-enumerated (illegal) move. Each drop is returned as a
    structured diagnostic (the root menu bug still gets found). Templated moves
    are kept and flagged ``_unvalidated``. Safe because the RNG lives in the
    state: probing advances only the copy's rng_state, never the real game's.
    This is the slow, correct path for the interactive/LLM menu; hot loops
    (sweeps, fuzzers) should keep calling ``legal_moves``.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for mv in legal_moves(gs):
        if mv.get("type") in _PALETTE_TEMPLATES:
            kept.append({**mv, "_unvalidated": True})
            continue
        concrete = {k: v for k, v in mv.items() if not k.startswith("_")}
        probe = GameState.from_json(gs.to_json())
        try:
            apply_action(probe, concrete)
        except IllegalAction as e:
            dropped.append({"action": concrete, "code": e.code, "reason": e.message,
                            "subphase": gs.meta.subphase, "active": gs.meta.active_player})
        else:
            kept.append(mv)
    return kept, dropped


def legal_moves(gs: GameState) -> list[dict[str, Any]]:
    if gs.meta.phase in ("campaign", "winter"):
        return campaign.legal_moves_campaign(gs)
    if gs.meta.phase != "levy":
        return []
    # SMOKE-008: surface owed Arts-of-War sub-decisions in the Levy menu, the way
    # legal_moves_campaign surfaces campaign pendings. Without this a menu-driven
    # agent at levy.pay sees only pay/pass_step and CANNOT resolve an owed
    # deploy_capability / immediate Event, stranding it (under-enumeration).
    dc = next((p for p in gs.meta.pending if p["type"] == "deploy_capability"), None)
    if dc is not None:
        return [{"type": "deploy_capability", "card": dc["card"], "lord": lid,
                 "_desc": f"Deploy first-Levy Capability {dc['card']} to {lid} (3.1.2)"}
                for lid in dc["eligible"]]
    ev = next((p for p in gs.meta.pending if p["type"] == "event_pending_resolution"), None)
    if ev is not None:
        return [{"type": "resolve_event", "card": ev["card"], "_args_per_card": True,
                 "_desc": f"Resolve immediate Event {ev['card']} (3.1.3); args per card text"}]
    ic = next((p for p in gs.meta.pending if p["type"] == "imperial_coffers"), None)
    if ic is not None:
        # R14 discard window: after both sides resolved Events, before Pay.
        moves = [{"type": "discard_imperial_coffers", "target": t,
                  "_desc": f"Discard Imperial Coffers (R14): Loyalty Check vs {t} (1.4.1)"}
                 for t in campaign.imperial_coffers_targets(gs)]
        moves.append({"type": "pass_imperial_coffers",
                      "_desc": "Decline to discard Imperial Coffers (R14)"})
        return moves
    step = gs.meta.subphase
    if step == "levy.pay":
        moves = actions.enumerate_pay(gs)
        if (gs.meta.active_player == "roman" and "R19" in gs.roman.capabilities_in_play
                and not gs.meta.notes.get("nomisma_debased_used")):
            moves.append({"type": "discard_nomisma",
                          "_desc": "Discard Nomisma Debased (R19): shift all Roman Service +1 box (later); "
                                   "then Non-Commander Roman Lords may not Tax (mark)"})
        moves.append({"type": "pass_step", "_desc": "Finish Pay for this side (3.2)"})
        return moves
    if step == "levy.muster":
        moves = events.held_event_menu(gs) + actions.enumerate_muster(gs)
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
    # Clear any persistent per-Lord Lordship deltas from a prior turn's immediate
    # Events (R1 -1 / S5 +1); the current turn's Events will set them afresh.
    for lord in gs.lords.values():
        lord.flags.pop("lordship_persist", None)
    _enter_step(gs, LEVY_STEPS[0])


def _enter_step(gs: GameState, step: str) -> None:
    gs.meta.subphase = f"levy.{step}"
    gs.meta.active_player = "seljuk"
    gs.meta.levy_step_passed = {}
    if step == "pay":
        # Treachery re-entry (1.4.2 + errata p6): switched Lords rejoin at a
        # free Seat before this season's Pay phase.
        actions.resolve_treachery_reentry(gs)
    elif step == "disband":
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
