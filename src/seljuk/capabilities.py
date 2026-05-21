"""Arts of War Capability effects — lower card halves (Phase 4).

Capabilities are passive: they are queried at the points where they take effect
(rating lookups, Strike/Protection in combat, Winter, etc.). A Capability is
"in play for a Lord" if its card is a This-Lord card on that Lord's mat, or a
side-wide card in that side's board-edge stack.

This module owns the lookup helpers and the rating modifiers. Combat modifiers
are applied in battle.py (which imports these helpers); other passive effects
hook in at their sites (campaign.py, actions.py).
"""
from __future__ import annotations

from typing import Optional

from . import static_data as sd


def _cap_name(card_id: str) -> str:
    return sd.card(card_id)["capability"]["name"]


def lord_capability_names(gs, lord_id: str) -> set[str]:
    """All Capability names currently affecting this Lord (his This-Lord cards
    plus his side's board-edge cards)."""
    lord = gs.lords[lord_id]
    names = {_cap_name(c) for c in lord.capabilities}
    names |= {_cap_name(c) for c in gs.side_decks(lord.side).capabilities_in_play}
    return names


def lord_has(gs, lord_id: str, cap_name: str) -> bool:
    return cap_name in lord_capability_names(gs, lord_id)


def side_has(gs, side: str, cap_name: str) -> bool:
    return any(_cap_name(c) == cap_name for c in gs.side_decks(side).capabilities_in_play)


# --- rating modifiers -------------------------------------------------------

def _in_roman_empire(gs, lord) -> bool:
    return sd.locale(lord.cylinder)["allegiance"] == "roman"


def _has_supply_route(gs, lord) -> bool:
    from . import campaign
    cost = campaign._min_supply_cost(gs, lord)
    return cost is not None and cost <= campaign._available_carts(gs, lord)


def command_rating(gs, lord_id: str, roller: Optional[object] = None) -> int:
    """Lord's Command rating including Capability bonuses (1.5.3 + Arts of War).

    Conditional bonuses are evaluated now: Centralized Administration (R6) needs
    the Roman Empire + a Supply Route; Support from Aleppo (S14) rolls 1-3 each
    card and so consumes a die when present (hence the roller)."""
    base = sd.lord(lord_id)["ratings"]["command"]
    names = lord_capability_names(gs, lord_id)
    bonus = 0
    lord = gs.lords[lord_id]
    if "Martial Society" in names:        # R8 (Robert/Roussel)
        bonus += 1
    if "The Sickle of Anatolia" in names:  # S12 (Afsin Beg)
        bonus += 1
    if "Centralized Administration" in names:  # R6
        if _in_roman_empire(gs, lord) and _has_supply_route(gs, lord):
            bonus += 1
    if "Support from Aleppo" in names and roller is not None:  # S14: +1 on a 1-3
        if roller.d6() <= 3:
            bonus += 1
    return base + bonus


def lordship_rating(gs, lord_id: str) -> int:
    """Lord's Lordship rating including Capability bonuses (3.4)."""
    base = sd.lord(lord_id)["ratings"]["lordship"]
    bonus = 0
    if lord_has(gs, lord_id, "Reconquista & Sicilian Commanders"):  # R10 (Robert/Roussel)
        bonus += 1
    return base + bonus
