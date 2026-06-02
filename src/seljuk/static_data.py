"""Loaders for static reference data (Phase 1).

Reads the JSON under ``data/static/`` (encoded faithfully from the curated
``reference/`` files, errata applied). Results are cached. Per
CROSS_PROJECT_LESSONS.md section 7, callers in the enumerator should wrap these
in try/except so a data-shape error suppresses an option rather than crashing;
the loaders themselves raise loudly so data problems surface in tests.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_STATIC = Path(__file__).resolve().parent / "data" / "static"


def _load(name: str) -> dict[str, Any]:
    path = _STATIC / name
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def forces() -> dict[str, Any]:
    return _load("forces.json")


@lru_cache(maxsize=None)
def strongholds() -> dict[str, Any]:
    return _load("strongholds.json")


@lru_cache(maxsize=None)
def game_map() -> dict[str, Any]:
    return _load("map.json")


@lru_cache(maxsize=None)
def lords() -> dict[str, Any]:
    return _load("lords.json")


@lru_cache(maxsize=None)
def themata() -> dict[str, Any]:
    return _load("themata.json")


@lru_cache(maxsize=None)
def cards() -> dict[str, Any]:
    return _load("cards.json")


@lru_cache(maxsize=None)
def command_decks() -> dict[str, Any]:
    return _load("command_decks.json")


# ---- convenience accessors -------------------------------------------------

def lord(lord_id: str) -> dict[str, Any]:
    return lords()["lords"][lord_id]


def all_lord_ids() -> list[str]:
    return list(lords()["lords"].keys())


def lord_ids_for_side(side: str) -> list[str]:
    """Native Lords of a side (by their primary/listed side in lords.json)."""
    return [lid for lid, v in lords()["lords"].items() if v["side"] == side]


def locale(locale_id: str) -> dict[str, Any]:
    return game_map()["locales"][locale_id]


def all_locale_ids() -> list[str]:
    return list(game_map()["locales"].keys())


def ways() -> list[dict[str, Any]]:
    return game_map()["ways"]


def card(card_id: str) -> dict[str, Any]:
    return cards()["cards"][card_id]


def card_ids_for_side(side: str) -> list[str]:
    return [cid for cid, v in cards()["cards"].items() if v["side"] == side]


def stronghold_profile(locale_id: str) -> dict[str, Any] | None:
    """Return the Stronghold profile for a Locale, honoring the Aleppo override.

    Returns None for non-Stronghold Locales (wilderness / unfortified
    settlement / holding box).
    """
    loc = locale(locale_id)
    if not loc.get("is_stronghold"):
        return None
    sh = strongholds()
    if locale_id == "aleppo":
        base = dict(sh["types"]["city"])
        base.update(
            {
                "surrender_dice": sh["aleppo_overrides"]["surrender_dice"],
                "garrison_column_forced": sh["aleppo_overrides"]["garrison_column"],
                "special_rules": sh["aleppo_overrides"]["special_rules"],
            }
        )
        return base
    # Return a copy so callers cannot mutate the lru_cached static data.
    return dict(sh["types"][loc["type"]])
