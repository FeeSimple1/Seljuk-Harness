"""Hidden-information filter for the LLM consumer (Phase 5).

Strips the opposing side's secret state before serialization: its draw deck and
held Events, and the unrevealed portion of its Campaign Plan. A player may
inspect their own Plan and the opponent's *played* (revealed) Command cards, but
not unused ones (4.1.2); held Events and deck contents are hidden (1.9).
"""
from __future__ import annotations

from typing import Any

from ..state import GameState


def filtered_state(gs: GameState, viewing_side: str) -> dict[str, Any]:
    d = gs.model_dump()
    enemy = "roman" if viewing_side == "seljuk" else "seljuk"
    es = d[enemy]
    es["draw_deck"] = ["<hidden>"] * len(es["draw_deck"])
    es["held_events"] = ["<hidden>"] * len(es["held_events"])
    pp = es.get("plan_pointer", 0)
    plan = es["command_plan"]
    es["command_plan"] = plan[:pp] + ["<hidden>"] * max(0, len(plan) - pp)  # only revealed cards shown
    # The opponent's own card counts remain visible (legal information); only
    # identities of unrevealed/secret cards are masked.
    # 6.1 Hidden Mats: hide the enemy's Mustered Lord mats (Forces, Assets,
    # Vassals, This-Lord Capabilities). Board-visible state -- the Lord's Locale,
    # Service marker, Besieged/Bypassed status -- stays public. (Combat reveals
    # mats during a Battle/Storm, but those resolve atomically inside an action,
    # so there is no persistent in-battle window to expose here.)
    if gs.meta.options.get("hidden_mats"):
        _HIDDEN = "<hidden>"
        for lid, ld in d["lords"].items():
            if ld["side"] != enemy or not ld["mustered"]:
                continue
            for field in ("forces", "routed", "lost", "vassals", "capabilities",
                          "themata_on_mat"):
                ld[field] = _HIDDEN
            ld["assets"] = _HIDDEN
    d["_viewing_side"] = viewing_side
    return d
