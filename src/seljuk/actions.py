"""Levy-phase action handlers (Phase 2): Pay (3.2) and Disband (3.3) so far.

Handlers validate against the rules and either mutate ``gs`` or raise
IllegalAction with a code and rule citation. The enumerator counterparts
(``enumerate_*``) MUST mirror these pre-checks (CROSS_PROJECT_LESSONS.md 1-2).
Muster, Call to Arms, Arts of War draw, and Loyalty Checks arrive in later
Phase 2 commits.
"""
from __future__ import annotations

from typing import Any

from . import scenarios, static_data as sd
from .rng import DiceRoller
from .state import GameState, IllegalAction, LordState

OFF_RIGHT = 13  # Service Marker shifted right beyond box 12 sits off-board (2.2.3)


# --- shared predicates ------------------------------------------------------

def is_commander(gs: GameState, lord_id: str) -> bool:
    """Whether this Lord is currently his side's Commander (1.5.1)."""
    c = sd.lord(lord_id).get("commander")
    if c == "always":
        return True
    if c == "conditional":  # Manuel Komnenos: Commander only if Romanos is off the map
        rom = gs.lords.get("romanos_diogenes")
        return not (rom and rom.mustered)
    return False


def current_allegiance(gs: GameState, locale_id: str) -> str:
    """The side a Locale is currently Friendly to (1.3.1). Conquered flips it;
    Fatimid Locales are Friendly to the Roman side by default."""
    loc = gs.locales[locale_id]
    if loc.conquered_side:
        return loc.conquered_side
    base = sd.locale(locale_id)["allegiance"]
    return "seljuk" if base == "seljuk" else "roman"


def is_friendly_locale(gs: GameState, locale_id: str, side: str) -> bool:
    return current_allegiance(gs, locale_id) == side


def _on_map(lord: LordState) -> bool:
    return lord.mustered and lord.cylinder not in ("calendar", "offboard", "removed")


def _shift_service_right(lord: LordState, amount: int) -> None:
    if lord.service_box is None:
        raise IllegalAction("no_service_marker", f"{lord.id} has no Service Marker to shift")
    lord.service_box = min(lord.service_box + amount, OFF_RIGHT)


# --- Pay (3.2) --------------------------------------------------------------

def _pay_targets(gs: GameState, payer_id: str, payer: LordState, asset: str) -> list[str]:
    """Lords whose Service this payer may shift with one asset type (3.2.1-.2)."""
    side = payer.side
    targets: set[str] = {payer_id}  # own Service Marker always allowed
    # co-located friendly Lords on the map
    for lid, l in gs.lords.items():
        if lid != payer_id and l.side == side and _on_map(l) and l.cylinder == payer.cylinder:
            targets.add(lid)
    # Commander Coin: any Unbesieged friendly Lord, any distance (3.2.1)
    if asset == "coin" and is_commander(gs, payer_id) and not payer.besieged:
        for lid, l in gs.lords.items():
            if l.side == side and _on_map(l) and not l.besieged:
                targets.add(lid)
    return sorted(targets)


def _payer_can_use_loot(gs: GameState, payer: LordState) -> bool:
    """3.2.2: Loot Pays only at a Friendly Locale free of Siege (may be Bypassed)."""
    if payer.cylinder not in gs.locales:
        return False
    if gs.locales[payer.cylinder].siege_markers > 0:
        return False
    return is_friendly_locale(gs, payer.cylinder, payer.side)


def enumerate_pay(gs: GameState) -> list[dict[str, Any]]:
    side = gs.meta.active_player
    out: list[dict[str, Any]] = []
    for pid, payer in gs.lords.items():
        if payer.side != side or not _on_map(payer):
            continue
        for asset in ("coin", "loot"):
            have = getattr(payer.assets, asset)
            if have <= 0:
                continue
            if asset == "loot" and not _payer_can_use_loot(gs, payer):
                continue
            for tid in _pay_targets(gs, pid, payer, asset):
                tgt = gs.lords[tid]
                if tgt.service_box is None:
                    continue
                out.append({
                    "type": "pay", "payer": pid, "target": tid, "asset": asset,
                    "amount": 1, "_max": have,
                    "_desc": f"{sd.lord(pid)['name']} pays {asset} to shift {sd.lord(tid)['name']}'s Service right (3.2)",
                })
    return out


def h_pay(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    if gs.meta.subphase != "levy.pay":
        raise IllegalAction("wrong_step", "Pay is only legal in the Levy Pay step (3.2)")
    pid = action.get("payer")
    tid = action.get("target")
    asset = action.get("asset", "coin")
    amount = int(action.get("amount", 1))
    if pid not in gs.lords or tid not in gs.lords:
        raise IllegalAction("bad_lord", "payer/target not found")
    payer = gs.lords[pid]
    if payer.side != gs.meta.active_player:
        raise IllegalAction("not_active_side", f"{pid} is not on the active side")
    if not _on_map(payer):
        raise IllegalAction("payer_not_on_map", f"{pid} is not Mustered on the map")
    if asset not in ("coin", "loot"):
        raise IllegalAction("bad_asset", "may only Pay with Coin or Loot (3.2)")
    if amount < 1 or getattr(payer.assets, asset) < amount:
        raise IllegalAction("insufficient_asset", f"{pid} lacks {amount} {asset}")
    if asset == "loot" and not _payer_can_use_loot(gs, payer):
        raise IllegalAction("loot_location", "Loot Pays only at a Friendly Locale free of Siege (3.2.2)")
    if tid not in _pay_targets(gs, pid, payer, asset):
        raise IllegalAction("bad_pay_target", f"{tid} is not a legal Pay target for {pid} (3.2)")
    tgt = gs.lords[tid]
    if tgt.service_box is None:
        raise IllegalAction("target_no_service", f"{tid} has no Service Marker")
    setattr(payer.assets, asset, getattr(payer.assets, asset) - amount)
    before = tgt.service_box
    _shift_service_right(tgt, amount)
    return {"ok": True, "payer": pid, "target": tid, "asset": asset, "amount": amount,
            "service_box": [before, tgt.service_box]}


def h_pass_step(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    from . import engine  # local import to avoid a cycle
    side = gs.meta.active_player
    engine.note_pass(gs)
    return {"ok": True, "passed": side, "now": {"subphase": gs.meta.subphase, "active": gs.meta.active_player}}


# --- Disband (3.3) ----------------------------------------------------------

def _return_capabilities_to_deck(gs: GameState, lord: LordState) -> None:
    """Return a Lord's 'This Lord' Capability cards to that side's AoW deck (3.3)."""
    deck = gs.side_decks(lord.side).draw_deck
    for cid in lord.capabilities:
        if cid not in deck:
            deck.append(cid)
    lord.capabilities = []


def _return_themata_home(gs: GameState, lord: LordState) -> None:
    """Errata (3.3.2): a Roman Commander Disbanding returns Themata on his mat
    to their home Thema box."""
    for marker in lord.themata_on_mat:
        home = marker.home_thema
        if home and home in gs.themata:
            marker.home_thema = None
            gs.themata[home].append(marker)
    lord.themata_on_mat = []


def _strip_lord(lord: LordState) -> None:
    lord.forces = {}
    lord.routed = {}
    from .state import Assets
    lord.assets = Assets()
    lord.vassals = []
    lord.service_box = None
    lord.moved_fought = False
    lord.besieged = False
    lord.bypassed = False
    lord.lieutenant_of = None
    lord.lower_lord = None


def resolve_disband(gs: GameState, side: str) -> list[dict[str, Any]]:
    """3.3: for the given side, remove Lords beyond Service (permanent) and
    Disband Lords at Service limit (re-Muster later). Returns per-Lord events."""
    events: list[dict[str, Any]] = []
    box = gs.meta.calendar_box
    for lid, lord in list(gs.lords.items()):
        if lord.side != side or not lord.mustered or lord.service_box is None:
            continue
        if lord.service_box < box:
            events.append(_disband_beyond(gs, lord))
        elif lord.service_box == box:
            events.append(_disband_at_limit(gs, lord))
    if events:
        gs.meta.vp = scenarios.score(gs)
    return events


def _disband_beyond(gs: GameState, lord: LordState) -> dict[str, Any]:
    """3.3.1 Beyond Service Limit: permanent removal."""
    claimed_so = False
    if lord.side == "seljuk" and lord.strategic_objective:
        gs.holding_boxes.constantinople_roman_vp_markers += 1
        lord.strategic_objective = False
        claimed_so = True
    _return_capabilities_to_deck(gs, lord)
    _return_themata_home(gs, lord)
    _strip_lord(lord)
    lord.mustered = False
    lord.cylinder = "removed"
    lord.cylinder_calendar_box = None
    return {"lord": lord.id, "disband": "beyond_service_permanent",
            "strategic_objective_claimed_by_roman": claimed_so}


def _disband_at_limit(gs: GameState, lord: LordState) -> dict[str, Any]:
    """3.3.2 At Service Limit: Disband but may Muster again later."""
    service_rating = sd.lord(lord.id)["ratings"]["service"]
    target = gs.meta.calendar_box + service_rating
    new_box = min(target, OFF_RIGHT)
    _return_capabilities_to_deck(gs, lord)
    _return_themata_home(gs, lord)
    _strip_lord(lord)
    lord.mustered = False
    lord.cylinder = "calendar"
    lord.cylinder_calendar_box = new_box
    return {"lord": lord.id, "disband": "at_limit_recyclable", "placed_calendar_box": new_box}
