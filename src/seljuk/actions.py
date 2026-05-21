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


# --- Muster (3.4) -----------------------------------------------------------
# Each on-map Lord may spend Lordship to Levy other Lords, Vassals, Transport,
# Capabilities, or (Roman Commander) Themata. Lords brought on this segment may
# not themselves Levy until Call to Arms (3.4).

def reset_muster_segment(gs: GameState) -> None:
    for lord in gs.lords.values():
        lord.flags.pop("lordship_spent", None)
        lord.flags.pop("mustered_this_segment", None)


def lordship_remaining(gs: GameState, lord: LordState) -> int:
    rating = sd.lord(lord.id)["ratings"]["lordship"]
    return rating - int(lord.flags.get("lordship_spent", 0))


def _spend_lordship(lord: LordState, n: int = 1) -> None:
    lord.flags["lordship_spent"] = int(lord.flags.get("lordship_spent", 0)) + n


def _can_act_in_muster(gs: GameState, lord: LordState) -> bool:
    """3.4: a Lord must have begun Muster at an Unbesieged Friendly Locale
    (incl. Holding Box), have Lordship left, and not be freshly Mustered."""
    if not _on_map(lord) or lord.side != gs.meta.active_player:
        return False
    if lord.besieged or lord.flags.get("mustered_this_segment"):
        return False
    if lordship_remaining(gs, lord) <= 0:
        return False
    return is_friendly_locale(gs, lord.cylinder, lord.side)


def _seat_is_free(gs: GameState, side: str, seat: str) -> bool:
    """3.4.1: a Seat is free if it has no enemy Lord and no enemy Conquered
    markers (it may be Bypassed or Ravaged)."""
    enemy = "roman" if side == "seljuk" else "seljuk"
    loc = gs.locales[seat]
    if loc.conquered_side == enemy:
        return False
    for l in gs.lords.values():
        if l.mustered and l.cylinder == seat and l.side == enemy:
            return False
    return True


def _muster_seats(gs: GameState, lord_id: str, side: str) -> list[str]:
    """Free Seats where this Lord could Muster, with the dual-allegiance
    Holding-Box fallback (1.4.2)."""
    info = sd.lord(lord_id)
    free = [s for s in info.get("seats", []) if _seat_is_free(gs, side, s)]
    if free:
        return free
    # Holding-box fallback for Arisighi / Robert / Roussel (1.4.2)
    if lord_id == "arisighi" and side == "roman":
        return ["to_constantinople"]
    if lord_id in ("robert_crepin", "roussel_de_bailleul") and side == "seljuk":
        return ["to_mosul_and_baghdad"]
    return []


def _muster_lord_onto_map(gs: GameState, lord: LordState, seat: str) -> None:
    info = sd.lord(lord.id)
    from .state import Assets
    slots, _ = scenarios._build_vassals(lord.id, [])
    lord.mustered = True
    lord.cylinder = seat
    lord.cylinder_calendar_box = None
    lord.forces = dict(info["starting_forces"])
    lord.routed = {}
    a = info["starting_assets"]
    lord.assets = Assets(**{k: a.get(k, 0) for k in ("carts", "provender", "coin", "loot")})
    lord.vassals = slots
    sr = info["ratings"]["service"]
    lord.service_box = min(gs.meta.calendar_box + sr, OFF_RIGHT)
    lord.flags["mustered_this_segment"] = True


def h_levy_lord(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.4.1 Levy Other Lords: spend 1 Lordship, roll Fealty for a Ready Lord."""
    if gs.meta.subphase != "levy.muster":
        raise IllegalAction("wrong_step", "Muster actions only in the Levy Muster step (3.4)")
    levyer = gs.lords.get(action.get("levyer"))
    target = gs.lords.get(action.get("target"))
    if levyer is None or target is None:
        raise IllegalAction("bad_lord", "levyer/target not found")
    if not _can_act_in_muster(gs, levyer):
        raise IllegalAction("cannot_levy", f"{levyer.id} cannot take a Levy action now (3.4)")
    if target.mustered or target.cylinder != "calendar" or target.cylinder_calendar_box is None:
        raise IllegalAction("target_not_ready", f"{target.id} is not Ready to Muster")
    if target.cylinder_calendar_box > gs.meta.calendar_box:
        raise IllegalAction("target_not_ready", f"{target.id} is not yet Ready (2.2)")
    seats = _muster_seats(gs, target.id, target.side)
    seat = action.get("seat")
    if seat is not None and seat not in seats:
        raise IllegalAction("seat_not_free", f"{seat} is not a free Seat for {target.id}")
    if seat is None:
        if not seats:
            raise IllegalAction("no_free_seat", f"{target.id} has no free Seat (3.4.1)")
        seat = seats[0]
    _spend_lordship(levyer, 1)
    fealty = sd.lord(target.id)["ratings"]["fealty"]
    roll = roller.d6()
    success = roll <= fealty
    if success:
        _muster_lord_onto_map(gs, target, seat)
    return {"ok": True, "action": "levy_lord", "levyer": levyer.id, "target": target.id,
            "roll": roll, "fealty": fealty, "success": success,
            "seat": seat if success else None}


def h_levy_transport(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.4.3 Levy Transport: a Lord at a Friendly Locale adds one Cart."""
    if gs.meta.subphase != "levy.muster":
        raise IllegalAction("wrong_step", "Muster actions only in the Levy Muster step (3.4)")
    lord = gs.lords.get(action.get("lord"))
    if lord is None or not _can_act_in_muster(gs, lord):
        raise IllegalAction("cannot_levy", "Lord cannot take a Levy action now (3.4)")
    _spend_lordship(lord, 1)
    lord.assets.carts = min(lord.assets.carts + 1, 8)  # 8-cap (1.7.3)
    return {"ok": True, "action": "levy_transport", "lord": lord.id, "carts": lord.assets.carts}


def _capability_eligible(gs: GameState, lord: LordState, card_id: str) -> bool:
    cdata = sd.card(card_id)
    if cdata["side"] != lord.side:
        return False
    if card_id not in gs.side_decks(lord.side).draw_deck:
        return False
    cap = cdata["capability"]
    if cap["scope"] == "this_lord":
        elig = cap["eligible_lords"]
        if elig is not None and lord.id not in elig:
            return False
        if len(lord.capabilities) >= 2:
            return False
        names = {sd.card(c)["capability"]["name"] for c in lord.capabilities}
        if cap["name"] in names:  # no duplicate name (3.4.4)
            return False
    return True


def h_levy_capability(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.4.4 Levy Capabilities: 1 Lordship per card; respects scope/eligibility."""
    if gs.meta.subphase != "levy.muster":
        raise IllegalAction("wrong_step", "Muster actions only in the Levy Muster step (3.4)")
    lord = gs.lords.get(action.get("lord"))
    card_id = action.get("card")
    if lord is None or not _can_act_in_muster(gs, lord):
        raise IllegalAction("cannot_levy", "Lord cannot take a Levy action now (3.4)")
    if card_id is None or not _capability_eligible(gs, lord, card_id):
        raise IllegalAction("ineligible_capability", f"{lord.id} may not Levy {card_id} (3.4.4)")
    _spend_lordship(lord, 1)
    gs.side_decks(lord.side).draw_deck.remove(card_id)
    cap = sd.card(card_id)["capability"]
    if cap["scope"] == "this_lord":
        lord.capabilities.append(card_id)
        placement = "this_lord_mat"
    else:
        gs.side_decks(lord.side).capabilities_in_play.append(card_id)
        placement = "board_edge"
    return {"ok": True, "action": "levy_capability", "lord": lord.id, "card": card_id, "placement": placement}


def _vassal_levyable(gs: GameState, lord: LordState, idx: int) -> bool:
    if idx < 0 or idx >= len(lord.vassals):
        return False
    v = lord.vassals[idx]
    if v.levied:
        return False
    if v.requires_capability:  # Special Vassal: its Capability must be in play
        in_play = v.requires_capability in lord.capabilities or \
            v.requires_capability in gs.side_decks(lord.side).capabilities_in_play
        if not in_play:
            return False
    return True


def h_levy_vassal(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.4.2 Levy Vassals: 1 Lordship; slide a ready Vassal's Forces onto the mat."""
    if gs.meta.subphase != "levy.muster":
        raise IllegalAction("wrong_step", "Muster actions only in the Levy Muster step (3.4)")
    lord = gs.lords.get(action.get("lord"))
    idx = action.get("vassal_index")
    if lord is None or not _can_act_in_muster(gs, lord):
        raise IllegalAction("cannot_levy", "Lord cannot take a Levy action now (3.4)")
    if idx is None or not _vassal_levyable(gs, lord, int(idx)):
        raise IllegalAction("vassal_unavailable", f"{lord.id} cannot Levy that Vassal (3.4.2)")
    _spend_lordship(lord, 1)
    v = lord.vassals[int(idx)]
    v.levied = True
    for u, n in v.forces.items():
        lord.forces[u] = lord.forces.get(u, 0) + n
    return {"ok": True, "action": "levy_vassal", "lord": lord.id, "vassal_index": int(idx), "forces_added": v.forces}


def h_levy_themata(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.4.5 Levy Themata: the Roman Commander spends 1 Lordship in his current
    Thema to take a Themata Service Marker (and its units) onto his mat."""
    if gs.meta.subphase != "levy.muster":
        raise IllegalAction("wrong_step", "Muster actions only in the Levy Muster step (3.4)")
    lord = gs.lords.get(action.get("lord"))
    if lord is None or not _can_act_in_muster(gs, lord):
        raise IllegalAction("cannot_levy", "Lord cannot take a Levy action now (3.4)")
    if lord.side != "roman" or not is_commander(gs, lord.id):
        raise IllegalAction("not_roman_commander", "only the Roman Commander may Levy Themata (3.4.5)")
    thema = sd.locale(lord.cylinder)["thema"]
    if thema is None or not gs.themata.get(thema):
        raise IllegalAction("no_themata_here", "no available Themata in this Lord's Thema (3.4.5)")
    idx = int(action.get("marker_index", 0))
    box = gs.themata[thema]
    if idx < 0 or idx >= len(box):
        raise IllegalAction("bad_themata_index", "no such Themata marker")
    _spend_lordship(lord, 1)
    marker = box.pop(idx)
    marker.home_thema = thema
    lord.themata_on_mat.append(marker)
    return {"ok": True, "action": "levy_themata", "lord": lord.id, "thema": thema,
            "marker": {"unit": marker.unit, "symbols": marker.symbols}}


def enumerate_muster(gs: GameState) -> list[dict[str, Any]]:
    side = gs.meta.active_player
    out: list[dict[str, Any]] = []
    actors = [(lid, l) for lid, l in gs.lords.items() if _can_act_in_muster(gs, l)]
    ready = [(tid, t) for tid, t in gs.lords.items()
             if not t.mustered and t.cylinder == "calendar"
             and t.cylinder_calendar_box is not None and t.cylinder_calendar_box <= gs.meta.calendar_box
             and t.side == side]
    for lid, lord in actors:
        for tid, t in ready:
            if _muster_seats(gs, tid, t.side):
                out.append({"type": "levy_lord", "levyer": lid, "target": tid,
                            "_desc": f"{sd.lord(lid)['name']} rolls Fealty to Muster {sd.lord(tid)['name']} (3.4.1)"})
        out.append({"type": "levy_transport", "lord": lid, "_desc": f"{sd.lord(lid)['name']} Levies a Cart (3.4.3)"})
        for cid in gs.side_decks(side).draw_deck:
            if _capability_eligible(gs, lord, cid):
                out.append({"type": "levy_capability", "lord": lid, "card": cid,
                            "_desc": f"{sd.lord(lid)['name']} Levies Capability {cid} (3.4.4)"})
        for i in range(len(lord.vassals)):
            if _vassal_levyable(gs, lord, i):
                out.append({"type": "levy_vassal", "lord": lid, "vassal_index": i,
                            "_desc": f"{sd.lord(lid)['name']} Levies Vassal #{i} (3.4.2)"})
        if lord.side == "roman" and is_commander(gs, lid):
            thema = sd.locale(lord.cylinder)["thema"]
            if thema and gs.themata.get(thema):
                out.append({"type": "levy_themata", "lord": lid, "thema": thema,
                            "_desc": f"{sd.lord(lid)['name']} Levies Themata in {thema} (3.4.5)"})
    return out
