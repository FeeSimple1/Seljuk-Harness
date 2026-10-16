"""Decision ownership shared by player-facing views (never changes game state).

Priority mirrors engine.legal_moves / campaign.legal_moves_campaign, not the
order in which pending records happened to be appended. In particular a
reactor is not necessarily meta.active_player or the besieging side.
"""
from __future__ import annotations

from copy import deepcopy
from ..state import GameState

SIDES = ("seljuk", "roman")
LEVY_PRIORITY = ("deploy_capability", "event_pending_resolution", "imperial_coffers")
CAMPAIGN_PRIORITY = (
    "retain_themata", "kleisourai", "summer_heat", "basil_response",
    "winter_quarters", "loyalty_check", "assign_themata_defenders",
    "approach_response", "besiege_or_bypass", "ravage_defence",
)


def check_side(side: str) -> str:
    if side not in SIDES:
        raise ValueError("side must be 'seljuk' or 'roman'")
    return side


def other(side: str) -> str:
    return "roman" if check_side(side) == "seljuk" else "seljuk"


def pending_owner(gs: GameState, pending: dict) -> str:
    for key in ("_owed_by", "reactor"):
        if pending.get(key) in SIDES:
            return pending[key]
    kind = pending.get("type")
    if (kind == "event_pending_resolution" and pending.get("card") in ("R1", "R10")
            and pending["card"] in gs.meta.asterisks_used):
        return "seljuk"  # repeated event: Seljuk chooses the Lord losing Lordship
    if kind in ("retain_themata", "kleisourai", "basil_response",
                "assign_themata_defenders", "ravage_defence", "imperial_coffers"):
        return "roman"
    if pending.get("side") in SIDES:
        return pending["side"]
    if kind == "approach_response" and pending.get("defenders"):
        return gs.lords[pending["defenders"][0]].side
    if kind == "winter_quarters" and pending.get("lord") in gs.lords:
        return gs.lords[pending["lord"]].side
    if kind == "besiege_or_bypass" and pending.get("lords"):
        return gs.lords[pending["lords"][0]].side
    return gs.meta.active_player


def current_pending(gs: GameState) -> dict | None:
    priority = LEVY_PRIORITY if gs.meta.phase == "levy" else CAMPAIGN_PRIORITY
    for kind in priority:
        for pending in gs.meta.pending:
            if pending.get("type") == kind:
                return pending
    return gs.meta.pending[0] if gs.meta.pending else None


def decision_side(gs: GameState) -> str:
    pending = current_pending(gs)
    return pending_owner(gs, pending) if pending else gs.meta.active_player


def visible_pending(gs: GameState, side: str) -> list[dict]:
    """Keep the owner's decision constraints, not private deferred scripts."""
    check_side(side)
    out = []
    for pending in gs.meta.pending:
        owner = pending_owner(gs, pending)
        if owner != side:
            out.append({"type": "opponent_decision", "owed_by": owner})
            continue
        item = {k: deepcopy(v) for k, v in pending.items()
                if not k.startswith("_") and k not in ("storm_decisions", "battle_decisions", "battle_events")}
        item["owed_by"] = owner
        if pending.get("_surprise_storm"):
            item["continuation"] = "Surprise Storm after this assignment; committed inputs remain private."
        out.append(item)
    return out
