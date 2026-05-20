"""Map graph helpers: adjacency, Way lookup, and topology queries (Phase 1).

Reads the static map (44 Locales; 15 Pass + 47 Road Ways; 4 whole-Command-card
routes) and exposes read-only queries. No movement rules live here yet (March
cost, Supply routing, Approach come in Phase 3); these are the primitives those
phases build on.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from . import static_data as sd


@lru_cache(maxsize=None)
def _adjacency() -> dict[str, list[dict[str, Any]]]:
    """locale_id -> list of {to, type, whole_command_card} edges (undirected)."""
    adj: dict[str, list[dict[str, Any]]] = {lid: [] for lid in sd.all_locale_ids()}
    for w in sd.ways():
        adj[w["a"]].append({"to": w["b"], "type": w["type"], "whole_command_card": w["whole_command_card"]})
        adj[w["b"]].append({"to": w["a"], "type": w["type"], "whole_command_card": w["whole_command_card"]})
    return adj


def neighbors(locale_id: str) -> list[str]:
    """Adjacent Locale ids (linked by any Way)."""
    return [e["to"] for e in _adjacency()[locale_id]]


def ways_from(locale_id: str) -> list[dict[str, Any]]:
    """All edges leaving a Locale: {to, type, whole_command_card}."""
    return list(_adjacency()[locale_id])


def ways_between(a: str, b: str) -> list[dict[str, Any]]:
    """All Ways directly linking a and b (typically 0 or 1 in Seljuk)."""
    return [e for e in _adjacency()[a] if e["to"] == b]


def is_adjacent(a: str, b: str) -> bool:
    return any(e["to"] == b for e in _adjacency()[a])


def adjacent_to_pass(locale_id: str) -> bool:
    """True if any Way connected to this Locale is a Pass (R2 / S2 Mountain
    Ambush trigger). Holding Boxes do not count as Pass-adjacent for that
    purpose even though their March takes a whole card."""
    return any(e["type"] == "pass" for e in _adjacency()[locale_id])


def allegiance(locale_id: str) -> str:
    return sd.locale(locale_id)["allegiance"]


def thema_of(locale_id: str) -> str | None:
    return sd.locale(locale_id)["thema"]
