"""Optional Rules (Rulebook 6.0).

These are off by default -- the designer notes they are "not the 'real' way to
play." Players agree on any optional rules before setup (7.0). A front-end / LLM
driver should present :data:`OPTIONAL_RULES` at the outset and pass the player's
choices to :func:`seljuk.scenarios.load_scenario` via ``options=``.
"""
from __future__ import annotations

from typing import Any

OPTIONAL_RULES: list[dict[str, Any]] = [
    {
        "key": "hidden_mats", "rule": "6.1", "name": "Hidden Mats",
        "type": "bool", "default": False,
        "summary": "Fog of war: each side's Mustered Lord mats (Forces, Assets, "
                   "Vassals, This-Lord Capabilities) are hidden from the opponent "
                   "except when that Lord is in Battle or Storm.",
    },
    {
        "key": "vassal_service", "rule": "6.2", "name": "Vassal Service",
        "type": "bool", "default": False,
        "summary": "Track each Vassal's Service on the Calendar (like a Lord): a "
                   "Mustering Vassal's marker is placed by its Service Rating, "
                   "shifts with its Lord's marker, and Disbands at its Service limit.",
    },
    {
        "key": "simultaneous_horse", "rule": "6.3", "name": "Simultaneous Horse Combat",
        "type": "choice", "choices": ["off", "melee", "missiles", "both"], "default": "off",
        "summary": "In Battle (not Storm), Horse units' Strikes resolve "
                   "simultaneously for both sides -- removing the fire-first "
                   "advantage. Choose Melee, Missiles, or Both.",
    },
    {
        "key": "deadlier_seljuk_missiles", "rule": "6.4", "name": "Deadlier Seljuk Missiles",
        "type": "bool", "default": False,
        "summary": "In Battle, Seljuk Missiles always Strike first, regardless of "
                   "who is Attacker or Defender.",
    },
]

DEFAULTS: dict[str, Any] = {r["key"]: r["default"] for r in OPTIONAL_RULES}
_BY_KEY: dict[str, dict[str, Any]] = {r["key"]: r for r in OPTIONAL_RULES}


def normalize(options: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a partial player selection onto the standard-rules defaults,
    validating keys and values. Unknown keys / bad choice values raise."""
    merged = dict(DEFAULTS)
    if not options:
        return merged
    for k, v in options.items():
        spec = _BY_KEY.get(k)
        if spec is None:
            raise ValueError(f"unknown optional rule {k!r}; valid: {sorted(DEFAULTS)}")
        if spec["type"] == "bool":
            merged[k] = bool(v)
        else:
            if v not in spec["choices"]:
                raise ValueError(f"{k!r} must be one of {spec['choices']}, got {v!r}")
            merged[k] = v
    return merged


def any_enabled(options: dict[str, Any]) -> bool:
    return options != DEFAULTS


def describe(options: dict[str, Any]) -> list[str]:
    """Human-readable list of the optional rules currently in effect."""
    out = []
    for r in OPTIONAL_RULES:
        v = options.get(r["key"], r["default"])
        if v != r["default"]:
            label = r["name"] if r["type"] == "bool" else f"{r['name']} ({v})"
            out.append(f"{r['rule']} {label}")
    return out
