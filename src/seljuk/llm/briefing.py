"""Compact, curated state briefing for the LLM consumer (Phase 5).

Aims for a small, decision-ready summary (well under a few KB): the scenario
clock, VP, the active side's situation, and what is currently being decided.
Built on render.summary; never prescribes an action (BRIEF.md no-agent rule).
"""
from __future__ import annotations

from .. import render, engine
from ..state import GameState


def briefing(gs: GameState) -> str:
    lines = [render.summary(gs)]
    lines.append(f"\nPhase: {gs.meta.phase}" + (f" / {gs.meta.subphase}" if gs.meta.subphase else ""))
    from .. import options as _options
    _opts = _options.describe(gs.meta.options)
    if _opts:
        lines.append("Optional Rules: " + ", ".join(_opts))
    if gs.meta.pending:
        owed = ", ".join(f"{p['type']}" + (f"(owed by {p.get('_owed_by')})" if p.get('_owed_by') else "")
                         for p in gs.meta.pending)
        lines.append(f"Pending decisions: {owed}")
    moves = engine.legal_moves(gs)
    if moves:
        kinds: dict[str, int] = {}
        for m in moves:
            kinds[m["type"]] = kinds.get(m["type"], 0) + 1
        lines.append("Legal move types: " + ", ".join(f"{k}x{v}" for k, v in kinds.items()))
    if gs.history:
        last = gs.history[-3:]
        lines.append("Recent: " + "; ".join(str(h["action"].get("type")) for h in last))
    return "\n".join(lines)
