"""Hidden-information filter for the LLM consumer (Phase 5).

Strips the opposing side's secret state before serialization: its draw deck and
held Events, and the unrevealed portion of its Campaign Plan. A player may
inspect their own Plan and the opponent's *played* (revealed) Command cards, but
not unused ones (4.1.2); held Events and deck contents are hidden (1.9).
"""
from __future__ import annotations

from typing import Any

from ..state import GameState, public_vassal_service
from .routing import check_side, visible_pending


def filtered_state(gs: GameState, viewing_side: str) -> dict[str, Any]:
    check_side(viewing_side)
    d = gs.model_dump()
    enemy = "roman" if viewing_side == "seljuk" else "seljuk"
    es = d[enemy]
    es["draw_deck"] = ["<hidden>"] * len(es["draw_deck"])
    es["held_events"] = ["<hidden>"] * len(es["held_events"])
    pp = es.get("plan_pointer", 0)
    plan = es["command_plan"]
    es["command_plan"] = plan[:pp] + ["<hidden>"] * max(0, len(plan) - pp)  # only revealed cards shown
    # Vassal Service markers on the Calendar are public even with Hidden Mats (6.2).
    for lid, ld in d["lords"].items():
        markers = public_vassal_service(gs, gs.lords[lid])
        if markers:
            ld["public_vassal_service"] = markers
    # The opponent's own card counts remain visible (legal information); only
    # identities of unrevealed/secret cards are masked.
    # 6.1 Hidden Mats: hide the enemy's Mustered Lord mats (Forces, Assets,
    # Vassals, This-Lord Capabilities). Board-visible state -- the Lord's Locale,
    # Service marker and Besieged/Bypassed status -- stays public. During a
    # committed Battle or Storm only participating mats are revealed.
    if gs.meta.options.get("hidden_mats"):
        for lid, ld in d["lords"].items():
            if ld["side"] != enemy or not ld["mustered"]:
                continue
            ld["flags"] = "<hidden>"
            if gs.mat_hidden_from(gs.lords[lid], viewing_side):
                for field in ("forces", "routed", "lost", "vassals", "capabilities",
                              "themata_on_mat", "assets"):
                    ld[field] = "<hidden>"
    # The replay history is private engine state, not a public event log. It
    # includes whole build_plan actions/results, future orders, and (with 6.1)
    # hidden mats. Expose only the public action-type summary, as briefing does.
    d["history"] = [{"action": {"type": h.get("action", {}).get("type")}}
                    for h in gs.history]
    # Revealing the seeded random stream also makes hidden future draws inferable.
    d["meta"].pop("rng_state", None)
    d["meta"].pop("seed", None)
    d["meta"]["pending"] = visible_pending(gs, viewing_side)
    # Deferred scripts and Winter holders are private engine bookkeeping, not
    # public notes. Known ongoing effects remain intact and inspectable.
    notes = d["meta"]["notes"]
    for key in list(notes):
        if key.startswith("_"):
            del notes[key]
    if "winter_holders" in notes:
        notes["winter_holders"] = [s for s in notes["winter_holders"] if s == viewing_side]
    if gs.meta.options.get("hidden_mats") and viewing_side != "roman":
        for key in ("retained_themata", "pressed_levy_used"):
            if key in notes:
                notes[key] = "<hidden>"
    d["_viewing_side"] = viewing_side
    return d
