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


# --- combat Protection modifiers (Battle/Storm) -----------------------------

_ARMORED = {"tagmata": (1, 3), "norman_knights": (1, 4), "scholai_hetaireia": (1, 4),
            "ghulam_cavalry": (1, 4), "varangian_guard": (1, 4), "infantry": (1, 3)}


def lamellar_active(gs, lord_id: str) -> bool:
    """Lamellar Armor (S1/S2) gives Turkic Horse Armor 1-3 until 3 of this
    Lord's Turkic Horse Rout in the Battle (S1/S2 clarification)."""
    if not lord_has(gs, lord_id, "Lamellar Armor"):
        return False
    return int(gs.lords[lord_id].flags.get("turkic_routed_battle", 0)) < 3


def protection_range(gs, lord_id: str, unit: str, hit_type: str, storm: bool = False) -> tuple[int, int]:
    """Protection range that NEGATES a Hit (4.8.2), including Capabilities.

    Turkic Horse: Lamellar Armor -> Armor 1-3; else Unarmored vs Missiles and
    (Battle only) Evade 1-3 vs Melee; in Storm, Evade is not used. Klibanophoroi
    -> Tagmata 1-4; Syndosis -> Militia 1-2; Steeled Resolve -> Infantry 1-4.
    """
    names = lord_capability_names(gs, lord_id)
    if unit == "turkic_horse":
        if lamellar_active(gs, lord_id):
            return (1, 3)
        if storm:
            return (1, 1)  # no Evade in Storm
        return (1, 1) if hit_type == "missile" else (1, 3)  # Unarmored vs Missiles, Evade vs Melee
    if unit == "militia":
        return (1, 2) if "Syndosis" in names else (1, 1)
    if unit == "tagmata":
        return (1, 4) if "Klibanophoroi" in names else (1, 3)
    if unit == "infantry":
        return (1, 4) if "Steeled Resolve" in names else (1, 3)
    return _ARMORED[unit]


def fealty_rating(gs, lord_id: str) -> int:
    """Fealty including Event modifiers (R10 Afsin Murders -> Afsin Beg Fealty 2)."""
    base = sd.lord(lord_id)["ratings"]["fealty"]
    if lord_id == "afsin_beg" and gs.meta.notes.get("afsin_fealty_2"):
        return 2
    return base
