"""On-demand lookups for the LLM consumer (Phase 5): cards, Lords, Locales.

These return the project's own structured data (not copyrighted rules text);
the curated reference .txt files remain the authority for full rule wording.
"""
from __future__ import annotations

from typing import Any

from .. import static_data as sd


def lookup_card(card_id: str) -> dict[str, Any]:
    return {"id": card_id, **sd.card(card_id)}


def lookup_lord(lord_id: str) -> dict[str, Any]:
    return {"id": lord_id, **sd.lord(lord_id)}


def lookup_locale(locale_id: str) -> dict[str, Any]:
    out = {"id": locale_id, **sd.locale(locale_id)}
    prof = sd.stronghold_profile(locale_id)
    if prof:
        out["stronghold"] = prof
    return out


def list_cards_for_side(side: str) -> list[dict[str, Any]]:
    return [{"id": cid, "event": sd.card(cid)["event"]["name"],
             "capability": sd.card(cid)["capability"]["name"]}
            for cid in sd.card_ids_for_side(side)]
