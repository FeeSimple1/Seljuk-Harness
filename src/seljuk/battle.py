"""Battle / Storm / Sally resolution (Phase 3b/3c).

Increment 1 records a triggered Battle as a pending sub-decision; the full
resolution engine (Array, Strike initiative, Flanking, Pursuit, Losses, Spoils,
Service, Aftermath) lands in the next increment per BRIEF.md.
"""
from __future__ import annotations

from typing import Any

from .state import GameState


def begin_battle(gs: GameState, attackers: list[str], defenders: list[str], locale: str) -> dict[str, Any]:
    gs.meta.pending.append({
        "type": "battle", "locale": locale,
        "attackers": list(attackers), "defenders": list(defenders),
    })
    return {"pending": "battle", "locale": locale, "attackers": list(attackers), "defenders": list(defenders)}
