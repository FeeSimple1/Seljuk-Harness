"""Compact, curated state briefing for the LLM consumer (Phase 5).

Aims for a small, decision-ready summary (well under a few KB): the scenario
clock, VP, the active side's situation, and what is currently being decided.
Built on render.summary; never prescribes an action (BRIEF.md no-agent rule).
"""
from __future__ import annotations

from .. import render, engine
from ..state import GameState
from .routing import decision_side, visible_pending, check_side


def briefing(gs: GameState, side: str | None = None, moves: list[dict] | None = None, owner: str | None = None) -> str:
    side = check_side(side or decision_side(gs))
    lines = [render.summary(gs, viewing_side=side)]
    lines.append(f"Decision owner: {owner or decision_side(gs)} | Viewing: {side}")
    lines.append(f"\nPhase: {gs.meta.phase}" + (f" / {gs.meta.subphase}" if gs.meta.subphase else ""))
    from .. import options as _options
    _opts = _options.describe(gs.meta.options)
    if _opts:
        lines.append("Optional Rules: " + ", ".join(_opts))
    if gs.meta.pending:
        owed = ", ".join(f"{p['type']}" + (f"(owed by {p.get('owed_by')})" if p.get('owed_by') else "")
                         for p in visible_pending(gs, side))
        lines.append(f"Pending decisions: {owed}")
    if moves is None:
        moves = engine.legal_moves(gs) if side == decision_side(gs) else []
    if moves:
        kinds: dict[str, int] = {}
        for m in moves:
            kinds[m["type"]] = kinds.get(m["type"], 0) + 1
        lines.append("Legal move types: " + ", ".join(f"{k}x{v}" for k, v in kinds.items()))
    if gs.history:
        last = gs.history[-3:]
        lines.append("Recent: " + "; ".join(str(h["action"].get("type")) for h in last))
    return "\n".join(lines)
