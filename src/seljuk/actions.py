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
from .state import GameState, IllegalAction, LordState, VassalSlot

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
        lord.flags.pop("lordship_bonus", None)


def lordship_remaining(gs: GameState, lord: LordState) -> int:
    rating = capabilities.lordship_rating(gs, lord.id) + int(lord.flags.get("lordship_bonus", 0))
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
        _muster_lord_onto_map(gs, lord, seats[0])
        lord.flags.pop("treachery_reentry_box", None)
        lord.flags.pop("mustered_this_segment", None)
        placed.append({"lord": lid, "seat": seats[0], "side": lord.side})
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
                _classify_drawn_event(gs, side, cid)
    gs.meta.notes["first_aow_done"] = True
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


def _classify_drawn_event(gs: GameState, side: str, card_id: str) -> None:
    tags = sd.card(card_id)["event"]["tags"]
    decks = gs.side_decks(side)
    if "hold" in tags:
        decks.held_events.append(card_id)
    elif "this_campaign" in tags:
        decks.this_campaign_events.append(card_id)
    else:
        # immediate / treachery / asterisk: effect resolution is Phase 4.
        gs.meta.pending.append({"type": "event_pending_resolution", "side": side, "card": card_id, "tags": tags})


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
                out.append({"type": "cta_loot", "lord": lid, "direction": "left",
                            "_desc": "Spend 1 Loot to shift a Ready Seljuk Lord's cylinder 1 box (3.5.2)"})
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
                    if loc["allegiance"] == "seljuk" and loc.get("is_stronghold") and not gs.locales[locid].strategic_objective:
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
            gs.locales[target].strategic_objective = True
            placed_on = {"locale": target}
        else:
            raise IllegalAction("bad_so_target", "unknown Strategic Objective target")
        gs.holding_boxes.constantinople_strategic_objectives_available -= 1
        _cta_done(gs)
        return {"ok": True, "action": "cta_strategic_objective", "mode": "place", **placed_on}
    raise IllegalAction("bad_mode", "Strategic Objective mode must be 'take' or 'place'")


# --- Loyalty Check (1.4) ----------------------------------------------------

def resolve_loyalty_check(gs: GameState, target_id: str, revealing_side: str,
                          roller: DiceRoller, coins_for: int = 0, coins_against: int = 0) -> dict[str, Any]:
    """1.4.1: roll d6 + (coins_for - coins_against). Natural 1 always fails,
    natural 6 always succeeds. If the modified result is GREATER than the
    target Lord's Fealty, he switches sides (1.4.2)."""
    if target_id not in gs.lords:
        raise IllegalAction("bad_lord", f"no such Lord {target_id}")
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
