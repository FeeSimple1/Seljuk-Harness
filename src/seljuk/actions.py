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
from . import capabilities
from .rng import DiceRoller
from .state import GameState, IllegalAction, LordState, VassalSlot, shift_vassal_service

OFF_RIGHT = 13  # Service Marker shifted right beyond box 12 sits off-board (2.2.3)


# --- shared predicates ------------------------------------------------------

def is_commander(gs: GameState, lord_id: str) -> bool:
    """Whether this Lord is currently his side's Commander (1.5.1)."""
    c = sd.lord(lord_id).get("commander")
    if c == "always":
        return True
    if c == "conditional":  # Manuel Komnenos: Commander only if Romanos is not on the map (1.5.1)
        rom = gs.lords.get("romanos_diogenes")
        return not (rom is not None and _on_map(rom))
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
    if locale_id == "aleppo" and gs.meta.notes.get("aleppo_friendly_both"):
        return True  # R14 Aleppo Independence: Friendly to both sides
    return current_allegiance(gs, locale_id) == side


def _on_map(lord: LordState) -> bool:
    return lord.mustered and lord.cylinder not in ("calendar", "offboard", "removed")


def _shift_service_right(gs: GameState, lord: LordState, amount: int) -> None:
    if lord.service_box is None:
        raise IllegalAction("no_service_marker", f"{lord.id} has no Service Marker to shift")
    lord.service_box = min(lord.service_box + amount, OFF_RIGHT)
    shift_vassal_service(gs, lord, amount)  # 6.2: Vassals shift with their Lord


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
    if gs.meta.subphase not in ("levy.pay", "campaign.fpd_pay"):
        raise IllegalAction("wrong_step", "Pay is legal in the Levy Pay step (3.2) or campaign Feed/Pay/Disband (4.6.2)")
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
    _shift_service_right(gs, tgt, amount)
    return {"ok": True, "payer": pid, "target": tid, "asset": asset, "amount": amount,
            "service_box": [before, tgt.service_box]}


def h_pass_step(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    from . import engine  # local import to avoid a cycle
    side = gs.meta.active_player
    if (gs.meta.subphase == "levy.muster" and side == "roman"
            and capabilities.side_has(gs, "roman", "Imperial Rivalry")
            and not gs.meta.notes.get("imperial_rivalry_attempted")
            and any(m.get("type") == "levy_lord" and m.get("target") == "andronikos_doukas"
                    for m in enumerate_muster(gs))):
        raise IllegalAction("imperial_rivalry",
                            "Romans must attempt to Muster Andronikos Doukas this Levy (S9)")
    engine.note_pass(gs)
    return {"ok": True, "passed": side, "now": {"subphase": gs.meta.subphase, "active": gs.meta.active_player}}


# --- Disband (3.3) ----------------------------------------------------------

def _return_capabilities_to_deck(gs: GameState, lord: LordState) -> None:
    """Return a Lord's 'This Lord' Capability cards to their AoW decks (3.3).
    Route each card by its PRINTED side, not the Lord's current allegiance: a
    Lord who switched sides on a Loyalty Check (1.4.2) must not migrate a Seljuk
    Capability into the Roman deck (or vice versa)."""
    for cid in lord.capabilities:
        deck = gs.side_decks(sd.card(cid)["side"]).draw_deck
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
    events.extend(_disband_expired_vassals(gs, side))  # 6.2 (before Lord Disband)
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


def _disband_expired_vassals(gs: GameState, side: str) -> list[dict[str, Any]]:
    """6.2: at each Disband step, Vassals at or beyond their Service limit return
    to their Lord's mat Coat-of-Arms down (Unready); their Forces go back to the
    pool (as able). A Lord left with no Forces Disbands (1.6/3.3.2)."""
    if not gs.meta.options.get("vassal_service"):
        return []
    box = gs.meta.calendar_box
    out: list[dict[str, Any]] = []
    for lord in gs.lords.values():
        if lord.side != side or not lord.mustered:
            continue
        for v in lord.vassals:
            if not (v.levied and v.service_box is not None and v.service_box <= box):
                continue
            for u, n in v.forces.items():           # return Forces to the pool (as able)
                have = lord.forces.get(u, 0)
                if have:
                    lord.forces[u] = have - min(have, n)
                    if lord.forces[u] <= 0:
                        lord.forces.pop(u, None)
            v.levied = False
            v.unready = True
            v.service_box = None
            out.append({"lord": lord.id, "vassal_disband": v.special_name or list(v.forces)})
        if lord.mustered and not lord.forces and lord.service_box is not None:  # 1.6 empty -> Disband
            out.append(_disband_at_limit(gs, lord))
    return out


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
    gs.meta.notes.pop("imperial_rivalry_attempted", None)  # S9: re-arm the obligation each Levy
    vs_on = gs.meta.options.get("vassal_service")
    for lord in gs.lords.values():
        lord.flags.pop("lordship_spent", None)
        lord.flags.pop("mustered_this_segment", None)
        lord.flags.pop("lordship_bonus", None)
        lord.flags.pop("restored_this_muster", None)
        if vs_on:  # 6.2: after Vassal Muster, flip Coat-of-Arms-down Markers up (Ready)
            for v in lord.vassals:
                v.unready = False


def lordship_remaining(gs: GameState, lord: LordState) -> int:
    # lordship_persist is a signed delta from immediate Events (R1 -1, S5 +1)
    # that must survive reset_muster_segment; it is cleared when a new Levy
    # phase begins (engine.start_levy).
    rating = (capabilities.lordship_rating(gs, lord.id)
              + int(lord.flags.get("lordship_bonus", 0))
              + int(lord.flags.get("lordship_persist", 0)))
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
    # A dual-allegiance Lord uses his alignment-specific Seat when set (e.g.
    # Arisighi's Seat is the Constantinople Holding Box when Roman-aligned),
    # not his printed (primary-side) Seat (1.4.2 / Map Reference).
    aligned = info.get(f"seat_when_{side}_aligned")
    candidates = [aligned] if aligned else list(info.get("seats", []))
    if side == "seljuk":
        # D-002-Marwanid (3.5.1.1, adjudicated 2026-07-06): an activated
        # Marwanid Locale is "a Seat for Seljuk Lords" -- nothing prohibits
        # Muster there, so it is allowed (Lords Reference lists Amid?/
        # Mayyafariqin? on every Seljuk Lord's Seats line). Winter-Quarters
        # return remains printed-Seats-only (the Playbook Winter example lists
        # Alp's Quarters options exhaustively WITHOUT the active Amid).
        candidates += [s for s in gs.meta.notes.get("marwanid_seats", []) if s not in candidates]
    free = [s for s in candidates if _seat_is_free(gs, side, s)]
    if free:
        return free
    # Holding-box fallback for Arisighi / Robert / Roussel (1.4.2)
    if lord_id == "arisighi" and side == "roman":
        return ["to_constantinople"]
    if lord_id in ("robert_crepin", "roussel_de_bailleul") and side == "seljuk":
        return ["to_mosul_and_baghdad"]
    return []


# Unit component pool (Rules 1.6 manifest): "85 Horse unit wedges (5 Norman
# Knights, 47 Turkic Horse, 25 Tagmata, 6 Ghulam, 2 Scholai/Hetaireia); 65 Foot
# unit bars (52 Infantry, 11 Militia, 2 Varangian Guard)." The pool is a hard
# limit on play (Muster 3.4.1-.2): if too few pieces remain, the Lord does not
# receive those units.
_UNIT_POOL = {
    "norman_knights": 5, "turkic_horse": 47, "tagmata": 25, "ghulam_cavalry": 6,
    "scholai_hetaireia": 2, "infantry": 52, "militia": 11, "varangian_guard": 2,
}


def _units_in_play(gs: GameState) -> dict[str, int]:
    """Count every unit piece currently on the board: Lords' Forces and Routed
    units, plus Themata markers on mats, defending, and in Thema boxes. (Garrison
    units exist only transiently during a Storm, never at Muster time, so they
    are not counted.) This is an exact tally of components NOT in the pool, so the
    derived availability never over-counts and so never wrongly blocks a Muster."""
    c: dict[str, int] = {}
    def _add(u, n):
        c[u] = c.get(u, 0) + n
    for l in gs.lords.values():
        for u, n in l.forces.items():
            _add(u, n)
        for u, n in l.routed.items():
            _add(u, n)
        for tm in l.themata_on_mat:
            _add(tm.unit, tm.symbols)
    for loc in gs.locales.values():
        for tm in loc.themata_defending:
            _add(tm.unit, tm.symbols)
    for box in gs.themata.values():
        for tm in box:
            _add(tm.unit, tm.symbols)
    return c


def _pool_remaining(gs: GameState, unit: str) -> int:
    return _UNIT_POOL.get(unit, 1 << 30) - _units_in_play(gs).get(unit, 0)


def _alloc_from_pool(gs: GameState, want: dict[str, int]) -> dict[str, int]:
    """Clamp a desired {unit: count} to what the component pool can still supply
    (1.6); units with no pieces left are simply not received."""
    inplay = _units_in_play(gs)
    out: dict[str, int] = {}
    for u, n in want.items():
        avail = _UNIT_POOL.get(u, 1 << 30) - inplay.get(u, 0)
        got = max(0, min(n, avail))
        if got > 0:
            out[u] = got
    return out


def _muster_lord_onto_map(gs: GameState, lord: LordState, seat: str) -> None:
    info = sd.lord(lord.id)
    from .state import Assets
    slots, _ = scenarios._build_vassals(lord.id, [])
    lord.mustered = True
    lord.cylinder = seat
    lord.cylinder_calendar_box = None
    lord.forces = _alloc_from_pool(gs, info["starting_forces"])  # 1.6 pool cap
    lord.routed = {}
    a = info["starting_assets"]
    lord.assets = Assets(**{k: a.get(k, 0) for k in ("carts", "provender", "coin", "loot")})
    lord.vassals = slots
    sr = info["ratings"]["service"]
    lord.service_box = min(gs.meta.calendar_box + sr, OFF_RIGHT)
    lord.flags["mustered_this_segment"] = True


def resolve_treachery_reentry(gs: GameState) -> list[dict[str, Any]]:
    """1.4.2 + errata (Rulebook p6, 1.4.2 Ex#3): a Lord who failed a Loyalty
    Check, switched sides, and went off-map rejoins under his new owner, placed
    at a free Seat at the start of the FOLLOWING season's Levy, before the Pay
    phase. If no Seat is free yet, he waits and retries the next season."""
    placed: list[dict[str, Any]] = []
    for lid, lord in gs.lords.items():
        box = lord.flags.get("treachery_reentry_box")
        if box is None or lord.mustered or lord.cylinder != "offboard":
            continue
        if gs.meta.calendar_box <= box:
            continue  # not until the following season's Levy
        seats = _muster_seats(gs, lid, lord.side)
        if not seats:
            continue  # no free Seat yet; retry next season
        seat = seats[0]
        _muster_lord_onto_map(gs, lord, seat)
        # 1.4.2: place the new side's Conquered markers on the Seat Stronghold (or
        # remove the previous side's if the Lord returns to his original allegiance).
        info = sd.locale(seat)
        if info.get("is_stronghold"):
            loc = gs.locales[seat]
            if info["allegiance"] == lord.side:
                loc.conquered_side = None
                loc.conquered_count = 0
            else:
                loc.conquered_side = lord.side
                loc.conquered_count = {"fort": 1, "town": 2, "city": 3}.get(info["type"], 0)
            gs.meta.vp = scenarios.score(gs)
        lord.flags.pop("treachery_reentry_box", None)
        lord.flags.pop("mustered_this_segment", None)
        placed.append({"lord": lid, "seat": seat, "side": lord.side})
    return placed


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
    if target.id == "andronikos_doukas" and levyer.side == "roman":
        gs.meta.notes["imperial_rivalry_attempted"] = True  # S9 obligation satisfied
    fealty = capabilities.fealty_rating(gs, target.id)
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
        _maybe_add_special_vassal(gs, lord, card_id)  # R2/R7/R17/S20 add the Vassal slot
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
    v = lord.vassals[int(idx)]
    if gs.meta.options.get("vassal_service") and v.unready:
        raise IllegalAction("vassal_unready", "an Unready (Coat-of-Arms down) Vassal may not Muster (6.2)")
    _spend_lordship(lord, 1)
    v.levied = True
    added = _alloc_from_pool(gs, v.forces)  # 1.6 pool cap: unavailable pieces are not added
    for u, n in added.items():
        lord.forces[u] = lord.forces.get(u, 0) + n
    if gs.meta.options.get("vassal_service"):  # 6.2: place the Vassal's Service Marker like a Lord (3.4.1)
        v.service_box = min(gs.meta.calendar_box + int(v.service or 0), OFF_RIGHT)
    return {"ok": True, "action": "levy_vassal", "lord": lord.id, "vassal_index": int(idx),
            "forces_added": added, "vassal_service_box": v.service_box}


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
            _seats = _muster_seats(gs, tid, t.side)
            if not _seats:
                continue
            if len(_seats) == 1:
                out.append({"type": "levy_lord", "levyer": lid, "target": tid,
                            "_desc": f"{sd.lord(lid)['name']} rolls Fealty to Muster {sd.lord(tid)['name']} (3.4.1)"})
            else:
                # 3.3.2/3.4.1: the Lord Musters "at one of his free Seats" -- when
                # more than one is free (e.g. Alp Arslan: Ani or the Mosul &
                # Baghdad box) the OWNER chooses; enumerate one move per Seat.
                for _st in _seats:
                    out.append({"type": "levy_lord", "levyer": lid, "target": tid, "seat": _st,
                                "_desc": f"{sd.lord(lid)['name']} rolls Fealty to Muster "
                                         f"{sd.lord(tid)['name']} at {sd.locale(_st)['name']} (3.4.1)"})
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
                # One option per distinct marker kind: the box mixes unit types
                # (Tagmata / Infantry / Militia), and the Commander chooses which
                # Themata Service Marker to take (3.4.5).
                _tkinds: set = set()
                for _ti, _tm in enumerate(gs.themata[thema]):
                    if (_tm.unit, _tm.symbols) in _tkinds:
                        continue
                    _tkinds.add((_tm.unit, _tm.symbols))
                    out.append({"type": "levy_themata", "lord": lid, "thema": thema,
                                "marker_index": _ti,
                                "_desc": f"{sd.lord(lid)['name']} Levies a {_tm.unit} Themata "
                                         f"(x{_tm.symbols}) in {thema} (3.4.5)"})
    # S5 Forced Conscription / S19 Baghdad Reinforcements: a Lord with the
    # Capability, at an Unbesieged Friendly Locale, may restore 1 of his Lost
    # units (free, once per Muster phase).
    for lid, lord in gs.lords.items():
        if lord.side != side or not _on_map(lord) or lord.besieged:
            continue
        if not (capabilities.lord_has(gs, lid, "Forced Conscription")
                or capabilities.lord_has(gs, lid, "Baghdad Reinforcements")):
            continue
        if not is_friendly_locale(gs, lord.cylinder, side) or lord.flags.get("restored_this_muster"):
            continue
        for unit, n in lord.lost.items():
            if n > 0:
                out.append({"type": "muster_restore", "lord": lid, "unit": unit,
                            "_desc": f"{sd.lord(lid)['name']} restores a Lost {unit} (S5/S19)"})

    return out


# --- Arts of War draw (3.1) -------------------------------------------------
# Phase 2 implements the DRAW mechanic and card classification only. Per-card
# EVENT/CAPABILITY EFFECTS are Phase 4 (BRIEF.md): immediate Events are queued
# in meta.pending for the consumer/Phase 4 to resolve; Hold and This-Campaign
# Events are filed; first-Levy This-Lord Capabilities awaiting assignment are
# queued as deploy decisions.

def resolve_arts_of_war(gs: GameState, roller: DiceRoller) -> dict[str, Any]:
    """3.1.1 shuffle + draw 2 per side. First Levy of the scenario deploys
    Capabilities (3.1.2); later Levies reveal Events (3.1.3)."""
    first = not gs.meta.notes.get("first_aow_done")
    drawn_log: dict[str, list[str]] = {}
    for side in ("seljuk", "roman"):
        deck = gs.side_decks(side).draw_deck
        roller.shuffle(deck)
        drawn = [deck.pop() for _ in range(min(2, len(deck)))]
        drawn_log[side] = drawn
        for cid in drawn:
            if first:
                _deploy_first_levy_capability(gs, side, cid)
            else:
                _classify_drawn_event(gs, side, cid, roller)
    gs.meta.notes["first_aow_done"] = True
    # R14 Imperial Coffers: after both sides draw/resolve Events, the Roman player
    # may discard the deployed Capability for a Loyalty Check (card clarification:
    # "after both players have resolved their Events"). Offer only when usable;
    # the menu re-checks targets, and the decision blocks before the Pay step.
    if not first and "R14" in gs.roman.capabilities_in_play:
        from . import campaign
        if campaign.imperial_coffers_targets(gs):
            gs.meta.pending.append({"type": "imperial_coffers", "side": "roman"})
    return {"step": "arts_of_war", "first_levy": first, "drawn": drawn_log}


def _eligible_mustered_for_this_lord(gs: GameState, side: str, card_id: str) -> list[str]:
    cap = sd.card(card_id)["capability"]
    elig = cap["eligible_lords"]
    out = []
    for lid, l in gs.lords.items():
        if l.side != side or not l.mustered:
            continue
        if elig is not None and lid not in elig:
            continue
        names = {sd.card(c)["capability"]["name"] for c in l.capabilities}
        if len(l.capabilities) < 2 and cap["name"] not in names:
            out.append(lid)
    return out


def _deploy_first_levy_capability(gs: GameState, side: str, card_id: str) -> None:
    cap = sd.card(card_id)["capability"]
    if cap["scope"] == "side_wide":
        gs.side_decks(side).capabilities_in_play.append(card_id)
        return
    # This-Lord: assign to a Mustered eligible Lord, else return to deck (3.1.2/3.4.4).
    eligible = _eligible_mustered_for_this_lord(gs, side, card_id)
    if not eligible:
        gs.side_decks(side).draw_deck.append(card_id)
        return
    gs.meta.pending.append({"type": "deploy_capability", "side": side, "card": card_id, "eligible": eligible})


def _classify_drawn_event(gs: GameState, side: str, card_id: str, roller: DiceRoller | None = None) -> None:
    tags = sd.card(card_id)["event"]["tags"]
    decks = gs.side_decks(side)
    if "hold" in tags:
        decks.held_events.append(card_id)
    elif "this_campaign" in tags:
        # File the card for end-of-Campaign discard (4.7.5) AND establish its
        # This-Campaign effect now (3.1.3) -- e.g. S9 Moustache sets the
        # Forage -2 flag that h_cmd_forage reads.
        decks.this_campaign_events.append(card_id)
        from . import events as _events
        if card_id in _events._RESOLVERS:
            _events._RESOLVERS[card_id](gs, {}, roller)
    else:
        # immediate / treachery / asterisk: effect resolution is Phase 4.
        gs.meta.pending.append({"type": "event_pending_resolution", "side": side, "card": card_id, "tags": tags})


def h_discard_nomisma(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """R19 Nomisma Debased: discard during the Levy Pay step to shift ALL Roman
    Service Markers 1 box RIGHT (later), capped at box 12. 'All' bypasses Pay's
    eligibility plumbing (Coin co-location / Loot Locale rules) and ignores
    location/Siege status. Under Vassal Service (6.2) Vassal Markers shift too.
    The permanent cost -- Non-Commander Roman Lords may not Tax -- is the
    nomisma_debased_used mark. Once per game (asterisk)."""
    if "R19" not in gs.roman.capabilities_in_play:
        raise IllegalAction("not_in_play", "Nomisma Debased is not in play")
    if gs.meta.notes.get("nomisma_debased_used"):
        raise IllegalAction("already_used", "Nomisma Debased has already been triggered (once per game)")
    use_vassals = bool((gs.meta.options or {}).get("vassal_service"))
    shifted = []
    for l in gs.lords.values():
        if l.side != "roman" or l.service_box is None:
            continue
        l.service_box = min(12, l.service_box + 1)               # shift right (later), cap box 12
        if use_vassals:
            for v in l.vassals:                                  # 6.2: Vassal Markers are Roman Service
                if v.levied and v.service_box is not None:
                    v.service_box = min(12, v.service_box + 1)
        shifted.append(l.id)
    gs.meta.notes["nomisma_debased_used"] = True                 # permanent Tax prohibition + once-per-game
    gs.roman.capabilities_in_play.remove("R19")
    gs.roman.draw_deck.append("R19")
    if "R19" not in gs.meta.asterisks_used:
        gs.meta.asterisks_used.append("R19")
    return {"ok": True, "action": "discard_nomisma", "shifted": shifted}


def h_deploy_capability(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """Resolve a queued first-Levy This-Lord Capability deployment (3.1.2)."""
    card_id = action.get("card")
    lord_id = action.get("lord")
    pend = next((p for p in gs.meta.pending if p.get("type") == "deploy_capability" and p.get("card") == card_id), None)
    if pend is None:
        raise IllegalAction("no_such_pending", f"no pending deployment for {card_id}")
    if lord_id not in pend["eligible"]:
        raise IllegalAction("ineligible_lord", f"{lord_id} may not receive {card_id}")
    gs.lords[lord_id].capabilities.append(card_id)
    gs.meta.pending.remove(pend)
    return {"ok": True, "deployed": card_id, "lord": lord_id}


# --- Call to Arms (3.5) -----------------------------------------------------
# Self-contained options implemented here: Loot (3.5.2) and Strategic Objective
# (3.5.3). The Capability-driven options (Marwanid 3.5.1.1, Empress 3.5.1.2,
# Deep Raids) are Phase 4. Each side may complete at most ONE option per Call
# to Arms (3.5), then it passes to the other side.

def _cta_done(gs: GameState) -> None:
    from . import engine
    engine.note_pass(gs)


def enumerate_call_to_arms(gs: GameState) -> list[dict[str, Any]]:
    side = gs.meta.active_player
    out: list[dict[str, Any]] = []
    if side == "seljuk" and gs.holding_boxes.mosul_baghdad_loot > 0:
        for lid, l in gs.lords.items():
            if l.side == "seljuk" and l.cylinder == "calendar":
                if (l.cylinder_calendar_box or 0) > 0:
                    out.append({"type": "cta_loot", "lord": lid, "direction": "left",
                                "_desc": "Spend 1 Loot to shift a Ready Seljuk Lord's cylinder 1 box left (3.5.2)"})
                # D-003 (adjudicated 2026-07-06): "shift" is directionless --
                # a right shift (delaying Readiness) is equally legal.
                if (l.cylinder_calendar_box or 0) < OFF_RIGHT:
                    out.append({"type": "cta_loot", "lord": lid, "direction": "right",
                                "_desc": "Spend 1 Loot to shift a Ready Seljuk Lord's cylinder 1 box right (3.5.2)"})
    if side == "seljuk" and capabilities.side_has(gs, "seljuk", "Marwanid Alliance"):
        active = set(gs.meta.notes.get("marwanid_seats", []))
        card_coins = gs.seljuk.capability_coins.get("S8", 0)
        aa = gs.lords.get("alp_arslan")
        # Transfer 1 Coin from Alp Arslan onto the card (3.5.1.1).
        if aa is not None and aa.assets.coin > 0:
            out.append({"type": "cta_marwanid_bank",
                        "_desc": "Transfer 1 Coin from Alp Arslan onto the Marwanid Alliance card (3.5.1.1)"})
        # Spend Coin from the card to activate Amid and/or Mayyafariqin (one option,
        # any number of card Coins).
        avail = [loc for loc in ("amid", "mayyafariqin") if loc not in active and not gs.locales[loc].ruins]
        if card_coins >= 1 and avail:
            out.append({"type": "cta_marwanid", "locales": avail[:card_coins],
                        "_desc": f"Spend Card Coin to activate {avail[:card_coins]} as Seljuk Seats (3.5.1.1)"})
            if card_coins >= 1:
                for loc in avail:  # also offer activating just one
                    out.append({"type": "cta_marwanid", "locales": [loc],
                                "_desc": f"Spend 1 Card Coin to activate {loc} as a Seljuk Seat (3.5.1.1)"})
    if side == "seljuk":
        for lid, l in gs.lords.items():
            if (l.side == "seljuk" and l.mustered and l.cylinder in ("ikonion", "western_anatolia")
                    and capabilities.lord_has(gs, lid, "Deep Raids")):
                loot = 2 if l.cylinder == "ikonion" else 3
                out.append({"type": "cta_deep_raids", "lord": lid,
                            "_desc": f"Deep Raids: Disband {lid} at {l.cylinder} for {loot} Loot/VP (S17)"})
    if side == "roman" and capabilities.side_has(gs, "roman", "Empress Eudokia Makrembolitissa"):
        token = gs.meta.notes.get("empress_token", "card")
        if token != "card":
            out.append({"type": "cta_empress", "mode": "place_on_card",
                        "_desc": "Place the Empress token back on the card (3.5.1.2)"})
        else:
            for lid, l in gs.lords.items():
                if l.side == "roman" and l.cylinder == "calendar" and l.cylinder_calendar_box is not None:
                    if l.cylinder_calendar_box > 0:
                        out.append({"type": "cta_empress", "mode": "use", "effect": "shift_cylinder",
                                    "lord": lid, "direction": "left",
                                    "_desc": f"Empress: shift {lid}'s cylinder 1 box left (3.5.1.2)"})
                    if l.cylinder_calendar_box < OFF_RIGHT:  # D-003: either direction is legal
                        out.append({"type": "cta_empress", "mode": "use", "effect": "shift_cylinder",
                                    "lord": lid, "direction": "right",
                                    "_desc": f"Empress: shift {lid}'s cylinder 1 box right (3.5.1.2)"})
            rom = gs.lords.get("romanos_diogenes")
            if rom is not None and rom.service_box is not None:
                for lid in ("manuel_komnenos", "andronikos_doukas", "joseph_tarchaneiotes", "nikephoros_bryennios"):
                    l = gs.lords.get(lid)
                    if l is not None and l.service_box is not None and l.service_box > 0:
                        out.append({"type": "cta_empress", "mode": "use", "effect": "transfer_service",
                                    "lord": lid, "_desc": f"Empress: move 1 Service from {lid} to Romanos (3.5.1.2)"})
    if side == "roman":
        rom = gs.lords.get("romanos_diogenes")
        man = gs.lords.get("manuel_komnenos")
        commander_in_cple = any(
            l and l.mustered and l.cylinder == "to_constantinople" and is_commander(gs, l.id)
            for l in (rom, man)
        )
        if commander_in_cple:
            if gs.holding_boxes.constantinople_strategic_objectives_available < 3:
                out.append({"type": "cta_strategic_objective", "mode": "take",
                            "_desc": "Take a Strategic Objective marker from supply (3.5.3)"})
            if gs.holding_boxes.constantinople_strategic_objectives_available > 0:
                # SMOKE-001: enumerate CONCRETE place targets (a Mustered enemy
                # Seljuk Lord, or an Enemy Stronghold in the Sultanate). The
                # round-trip sweep caught the previous arg-less "place" move
                # being inapplicable by the handler (3.5.3).
                for tid, tl in gs.lords.items():
                    if tl.side == "seljuk" and tl.mustered and not tl.strategic_objective:
                        out.append({"type": "cta_strategic_objective", "mode": "place", "target": tid,
                                    "_desc": f"Place a Strategic Objective on {sd.lord(tid)['name']} (3.5.3)"})
                for locid in sd.all_locale_ids():
                    loc = sd.locale(locid)
                    if (loc["allegiance"] == "seljuk" and loc.get("is_stronghold")
                            and not gs.locales[locid].strategic_objective
                            and current_allegiance(gs, locid) == "seljuk"):
                        out.append({"type": "cta_strategic_objective", "mode": "place", "target": locid,
                                    "_desc": f"Place a Strategic Objective at {loc['name']} (3.5.3)"})
    return out


def h_cta_loot(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    if gs.meta.subphase != "levy.call_to_arms" or gs.meta.active_player != "seljuk":
        raise IllegalAction("wrong_step", "Loot option is a Seljuk Call to Arms action (3.5.2)")
    if gs.holding_boxes.mosul_baghdad_loot <= 0:
        raise IllegalAction("no_loot", "no Loot in the Mosul & Baghdad box (3.5.2)")
    lord = gs.lords.get(action.get("lord"))
    if lord is None or lord.side != "seljuk" or lord.cylinder != "calendar" or lord.cylinder_calendar_box is None:
        raise IllegalAction("bad_lord", "Loot shifts a Ready Seljuk Lord's cylinder (3.5.2)")
    direction = action.get("direction", "left")
    delta = -1 if direction == "left" else 1
    new_box = max(0, min(lord.cylinder_calendar_box + delta, OFF_RIGHT))
    lord.cylinder_calendar_box = new_box
    gs.holding_boxes.mosul_baghdad_loot -= 1
    gs.meta.vp = scenarios.score(gs)
    _cta_done(gs)
    return {"ok": True, "action": "cta_loot", "lord": lord.id, "cylinder_box": new_box}


def h_cta_strategic_objective(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.5.3 (errata): Roman Commander must be in Constantinople; take from
    supply OR place an available marker — never both in one Call to Arms."""
    if gs.meta.subphase != "levy.call_to_arms" or gs.meta.active_player != "roman":
        raise IllegalAction("wrong_step", "Strategic Objective is a Roman Call to Arms action (3.5.3)")
    rom = gs.lords.get("romanos_diogenes")
    man = gs.lords.get("manuel_komnenos")
    if not any(l and l.mustered and l.cylinder == "to_constantinople" and is_commander(gs, l.id) for l in (rom, man)):
        raise IllegalAction("commander_not_in_constantinople", "Roman Commander must be in Constantinople (3.5.3 errata)")
    mode = action.get("mode")
    if mode == "take":
        if gs.holding_boxes.constantinople_strategic_objectives_available >= 3:
            raise IllegalAction("so_supply_empty", "all three Strategic Objective markers are out (3.5.3)")
        gs.holding_boxes.constantinople_strategic_objectives_available += 1
        _cta_done(gs)
        return {"ok": True, "action": "cta_strategic_objective", "mode": "take",
                "available": gs.holding_boxes.constantinople_strategic_objectives_available}
    if mode == "place":
        if gs.holding_boxes.constantinople_strategic_objectives_available <= 0:
            raise IllegalAction("no_so_available", "no available Strategic Objective marker to place (3.5.3)")
        target = action.get("target")
        if target in gs.lords:
            tl = gs.lords[target]
            if tl.side == "roman" or not tl.mustered:
                raise IllegalAction("bad_so_target", "must place on a Mustered enemy (Seljuk) Lord (3.5.3)")
            tl.strategic_objective = True
            placed_on = {"lord": target}
        elif target in gs.locales:
            if sd.locale(target)["allegiance"] != "seljuk":
                raise IllegalAction("bad_so_target", "Stronghold target must be an Enemy Stronghold in the Sultanate (3.5.3)")
            if not sd.locale(target).get("is_stronghold"):
                raise IllegalAction("bad_so_target", "target must be a Stronghold (3.5.3)")
            if current_allegiance(gs, target) != "seljuk":
                raise IllegalAction("bad_so_target", "Stronghold is not currently Seljuk-controlled (3.5.3 errata)")
            gs.locales[target].strategic_objective = True
            placed_on = {"locale": target}
        else:
            raise IllegalAction("bad_so_target", "unknown Strategic Objective target")
        gs.holding_boxes.constantinople_strategic_objectives_available -= 1
        _cta_done(gs)
        return {"ok": True, "action": "cta_strategic_objective", "mode": "place", **placed_on}
    raise IllegalAction("bad_mode", "Strategic Objective mode must be 'take' or 'place'")


def _marwanid_in_play(gs: GameState) -> None:
    if gs.meta.subphase != "levy.call_to_arms" or gs.meta.active_player != "seljuk":
        raise IllegalAction("wrong_step", "Marwanid actions are Seljuk Call to Arms actions (3.5.1.1)")
    if not capabilities.side_has(gs, "seljuk", "Marwanid Alliance"):
        raise IllegalAction("no_marwanid", "Marwanid Alliance (S8) is not in play")


def h_cta_marwanid_bank(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.5.1.1: transfer 1 Coin from Alp Arslan's Assets onto the Marwanid card."""
    _marwanid_in_play(gs)
    aa = gs.lords.get("alp_arslan")
    if aa is None or aa.assets.coin <= 0:
        raise IllegalAction("no_coin", "Alp Arslan has no Coin to transfer")
    aa.assets.coin -= 1
    gs.seljuk.capability_coins["S8"] = gs.seljuk.capability_coins.get("S8", 0) + 1
    _cta_done(gs)
    return {"ok": True, "action": "cta_marwanid_bank", "card_coins": gs.seljuk.capability_coins["S8"]}


def h_cta_marwanid(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.5.1.1: spend Coin FROM THE CARD (1 per Locale) to activate Amid and/or
    Mayyafariqin as Seats for all Seljuk Lords until the end of the next Winter."""
    _marwanid_in_play(gs)
    locales = action.get("locales") or ([action["locale"]] if action.get("locale") else [])
    active = gs.meta.notes.setdefault("marwanid_seats", [])
    for loc in locales:
        if loc not in ("amid", "mayyafariqin"):
            raise IllegalAction("bad_locale", "Marwanid activates Amid or Mayyafariqin (3.5.1.1)")
        if loc in active:
            raise IllegalAction("already_active", f"{loc} is already an activated Marwanid Seat")
        if gs.locales[loc].ruins:
            raise IllegalAction("ruined", f"{loc} is Ruined and cannot be activated as a Seat")
    if not locales:
        raise IllegalAction("no_locale", "name the Locale(s) to activate")
    if gs.seljuk.capability_coins.get("S8", 0) < len(locales):
        raise IllegalAction("no_coin", "not enough Coin on the Marwanid Alliance card (Coin must be banked first)")
    gs.seljuk.capability_coins["S8"] -= len(locales)
    active.extend(locales)
    _cta_done(gs)
    return {"ok": True, "action": "cta_marwanid", "locales": locales, "active_seats": list(active)}


def h_cta_deep_raids(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """S17 Deep Raids: in Call to Arms, Disband a Seljuk Lord (with the
    Capability) in Ikonion for 2 VP or Western Anatolia for 3 VP, placing that
    much Loot in the Mosul & Baghdad Holding Box."""
    if gs.meta.subphase != "levy.call_to_arms" or gs.meta.active_player != "seljuk":
        raise IllegalAction("wrong_step", "Deep Raids is a Seljuk Call to Arms action (S17)")
    lid = action.get("lord")
    lord = gs.lords.get(lid)
    if lord is None or lord.side != "seljuk" or not lord.mustered:
        raise IllegalAction("bad_lord", "Deep Raids needs a Mustered Seljuk Lord")
    if not capabilities.lord_has(gs, lid, "Deep Raids"):
        raise IllegalAction("no_deep_raids", f"{lid} does not have Deep Raids (S17)")
    loot = {"ikonion": 2, "western_anatolia": 3}.get(lord.cylinder)
    if loot is None:
        raise IllegalAction("bad_locale", "Deep Raids Disbands at Ikonion (2) or Western Anatolia (3) (S17)")
    gs.holding_boxes.mosul_baghdad_loot += loot
    _disband_at_limit(gs, lord)
    gs.meta.vp = scenarios.score(gs)
    _cta_done(gs)
    return {"ok": True, "action": "cta_deep_raids", "lord": lid, "loot": loot}


def h_muster_restore(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """S5 Forced Conscription / S19 Baghdad Reinforcements: restore 1 Lost unit
    for free during Muster (once per Muster phase)."""
    if gs.meta.subphase != "levy.muster":
        raise IllegalAction("wrong_step", "restore is a Muster action (3.4)")
    lid = action.get("lord")
    lord = gs.lords.get(lid)
    if lord is None or lord.side != gs.meta.active_player:
        raise IllegalAction("bad_lord", "not an active-side Lord")
    if not (capabilities.lord_has(gs, lid, "Forced Conscription")
            or capabilities.lord_has(gs, lid, "Baghdad Reinforcements")):
        raise IllegalAction("no_restore_capability", f"{lid} cannot restore Lost units (S5/S19)")
    if not _on_map(lord) or lord.besieged or not is_friendly_locale(gs, lord.cylinder, lord.side):
        raise IllegalAction("bad_location", "must be at an Unbesieged Friendly Locale (S5/S19)")
    if lord.flags.get("restored_this_muster"):
        raise IllegalAction("already_restored", "already restored a unit this Muster phase (S5/S19)")
    unit = action.get("unit")
    if lord.lost.get(unit, 0) <= 0:
        raise IllegalAction("no_lost_unit", f"{lid} has no Lost {unit} to restore")
    if _pool_remaining(gs, unit) <= 0:
        raise IllegalAction("pool_empty", f"no {unit} pieces remain in the pool to restore (1.6)")
    lord.lost[unit] -= 1
    lord.forces[unit] = lord.forces.get(unit, 0) + 1
    lord.flags["restored_this_muster"] = True
    return {"ok": True, "action": "muster_restore", "lord": lid, "unit": unit}


_CONSTANTINOPLE_SEAT = {"romanos_diogenes", "manuel_komnenos", "andronikos_doukas",
                        "joseph_tarchaneiotes", "nikephoros_bryennios"}


def h_cta_empress(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """3.5.1.2 Empress Eudokia (R12): in Call to Arms the Roman player may either
    PLACE the Empress token on the card (ready it) or, if it is on the card, MOVE
    it to Constantinople and choose one effect: shift a Roman Lord's cylinder 1
    box, or move 1 Service from a Constantinople-Seat Lord to Romanos."""
    if gs.meta.subphase != "levy.call_to_arms" or gs.meta.active_player != "roman":
        raise IllegalAction("wrong_step", "Empress Eudokia is a Roman Call to Arms action (3.5.1.2)")
    if not capabilities.side_has(gs, "roman", "Empress Eudokia Makrembolitissa"):
        raise IllegalAction("no_empress", "Empress Eudokia (R12) is not in play")
    token = gs.meta.notes.get("empress_token", "card")
    mode = action.get("mode")
    if mode == "place_on_card":
        gs.meta.notes["empress_token"] = "card"
        _cta_done(gs)
        return {"ok": True, "action": "cta_empress", "mode": "place_on_card"}
    if mode == "use":
        if token != "card":
            raise IllegalAction("token_not_on_card", "the Empress token is not on the card (3.5.1.2)")
        effect = action.get("effect")
        if effect == "shift_cylinder":
            l = gs.lords.get(action.get("lord"))
            if l is None or l.side != "roman" or l.cylinder != "calendar" or l.cylinder_calendar_box is None:
                raise IllegalAction("bad_lord", "shift a Ready Roman Lord's cylinder (3.5.1.2)")
            delta = -1 if action.get("direction", "left") == "left" else 1
            l.cylinder_calendar_box = max(0, min(l.cylinder_calendar_box + delta, OFF_RIGHT))
        elif effect == "transfer_service":
            l = gs.lords.get(action.get("lord"))
            rom = gs.lords.get("romanos_diogenes")
            if (l is None or action.get("lord") not in _CONSTANTINOPLE_SEAT or action.get("lord") == "romanos_diogenes"
                    or l.service_box is None or rom is None or rom.service_box is None):
                raise IllegalAction("bad_lord", "decrease a Constantinople-Seat Lord's Service to raise Romanos (3.5.1.2)")
            l.service_box = max(0, l.service_box - 1)
            shift_vassal_service(gs, l, -1)               # 6.2
            rom.service_box = min(rom.service_box + 1, OFF_RIGHT)
            shift_vassal_service(gs, rom, 1)              # 6.2
        else:
            raise IllegalAction("bad_effect", "Empress effect must be 'shift_cylinder' or 'transfer_service'")
        gs.meta.notes["empress_token"] = "constantinople"
        _cta_done(gs)
        return {"ok": True, "action": "cta_empress", "mode": "use", "effect": effect}
    raise IllegalAction("bad_mode", "Empress mode must be 'place_on_card' or 'use'")


# --- Loyalty Check (1.4) ----------------------------------------------------

def _spend_loyalty_coins(gs: GameState, side: str, target_id: str, n: int) -> None:
    """Spend n Coin for a Loyalty Check from the side's Commander and/or its
    Lords co-located with the target (Unbesieged) (1.4.1)."""
    if n <= 0:
        return
    target = gs.lords[target_id]
    sources = [l for lid, l in gs.lords.items()
               if l.side == side and _on_map(l) and not l.besieged
               and (is_commander(gs, lid) or l.cylinder == target.cylinder)]
    if sum(s.assets.coin for s in sources) < n:
        raise IllegalAction("insufficient_coin",
                            f"{side} lacks {n} Coin from its Commander / co-located Lords (1.4.1)")
    for srcl in sources:
        if n <= 0:
            break
        take = min(srcl.assets.coin, n)
        srcl.assets.coin -= take
        n -= take


def loyalty_coin_budget(gs: GameState, side: str, target_id: str) -> int:
    """1.4.1: Coin available to a side for a Loyalty Check vs ``target_id`` --
    from its Commander and/or its Lords co-located with the target (Unbesieged).
    Used for the palette's _max_coins_for/_max_coins_against hints."""
    target = gs.lords[target_id]
    return sum(l.assets.coin for lid, l in gs.lords.items()
               if l.side == side and _on_map(l) and not l.besieged
               and (is_commander(gs, lid) or l.cylinder == target.cylinder))


def resolve_loyalty_check(gs: GameState, target_id: str, revealing_side: str,
                          roller: DiceRoller, coins_for: int = 0, coins_against: int = 0) -> dict[str, Any]:
    """1.4.1: roll d6 + (coins_for - coins_against). Natural 1 always fails,
    natural 6 always succeeds. If the modified result is GREATER than the
    target Lord's Fealty, he switches sides (1.4.2)."""
    if target_id not in gs.lords:
        raise IllegalAction("bad_lord", f"no such Lord {target_id}")
    target = gs.lords[target_id]
    if coins_against and target.besieged:
        raise IllegalAction("besieged_no_resist", "the owner may not spend Coin to resist for a Besieged Lord (1.4.1)")
    _spend_loyalty_coins(gs, revealing_side, target_id, coins_for)   # checking side spends +1 each
    _spend_loyalty_coins(gs, target.side, target_id, coins_against)  # owner spends -1 each to resist
    fealty = capabilities.fealty_rating(gs, target_id)
    nat = roller.d6()
    modified = nat + coins_for - coins_against
    if nat == 1:
        switched = False
    elif nat == 6:
        switched = True
    else:
        switched = modified > fealty
    result = {"target": target_id, "natural": nat, "modified": modified, "fealty": fealty, "switched": switched}
    if switched:
        _switch_side(gs, gs.lords[target_id])
        result["new_side"] = gs.lords[target_id].side
    return result


def _switch_side(gs: GameState, lord: LordState) -> None:
    """1.4.2: a Lord who fails a Loyalty Check switches sides and is Disbanded
    (rejoining under the new owner). Phase 2 flips allegiance and removes him
    from the map; precise re-placement timing is handled by the Pay phase in
    later phases."""
    lord.side = "roman" if lord.side == "seljuk" else "seljuk"
    _return_capabilities_to_deck(gs, lord)
    _return_themata_home(gs, lord)
    _strip_lord(lord)
    lord.mustered = False
    lord.strategic_objective = False
    if lord.cylinder == "calendar":
        pass  # cylinder stays on the Calendar, now the other color
    else:
        lord.cylinder = "offboard"  # rejoins at his Seat next Levy, before Pay (1.4.2 + errata p6)
        lord.cylinder_calendar_box = None
        lord.flags["treachery_reentry_box"] = gs.meta.calendar_box


def h_resolve_event(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """Resolve a queued immediate Event (Phase 4). See events.py."""
    from . import events
    return events.resolve_event(gs, action.get("card"), action.get("args"), roller)


_SPECIAL_VASSAL_BY_CARD = {"R2": "oghuz_mercenaries", "R7": "emperors_retinue",
                           "R17": "scholai", "S20": "elite_ghulam_cavalry"}


def _maybe_add_special_vassal(gs: GameState, lord: LordState, card_id: str) -> None:
    """3.4.2 / Capability text: levying a special-Vassal-adder Capability (R2,
    R7, R17, S20) puts the special Vassal's Service Marker on this Lord's mat,
    if it is not already there (e.g. Oghuz Mercenaries has no printed home)."""
    key = _SPECIAL_VASSAL_BY_CARD.get(card_id)
    if key is None:
        return
    if any(v.requires_capability == card_id for v in lord.vassals):
        return  # printed slot already on this Lord's mat
    roster = sd.lords()["special_vassals_roster"][key]
    lord.vassals.append(VassalSlot(forces=dict(roster["forces"]), service=roster.get("service"),
                                   special_name=key, requires_capability=card_id))


def h_play_hold_event(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    from . import events
    return events.play_hold_event(gs, action.get("card"), action.get("args"), roller)
