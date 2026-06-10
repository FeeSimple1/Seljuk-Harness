"""Arts of War Event resolvers — upper card halves (Phase 4).

Immediate Events drawn during Levy are queued in ``meta.pending`` as
``event_pending_resolution`` and resolved here via the ``resolve_event`` action
(the player supplies any choices in ``args``). This module covers the
mechanically self-contained immediate Events: Calendar shifts, Themata
removals/returns, marker/VP changes, Asset exchanges, and once-per-game marks.

Not yet wired (a documented Phase 4 remainder): Hold Events that are *played*
at a specific later moment (in Battle/Storm/Muster/Winter), and the Treachery
Events (R8/S16/S19) that add a Treachery card to the Plan and trigger Loyalty
Checks. Those need play-time hooks at their sites; the Loyalty-Check resolver
itself already exists in actions.resolve_loyalty_check.
"""
from __future__ import annotations

from typing import Any

from . import scenarios, static_data as sd
from .rng import DiceRoller
from .state import GameState, IllegalAction


def _shift_calendar(gs: GameState, lord_id: str, what: str, direction: str) -> dict:
    if lord_id not in gs.lords:
        raise IllegalAction("bad_lord", f"no such Lord {lord_id}")
    lord = gs.lords[lord_id]
    delta = -1 if direction == "left" else 1
    if what == "cylinder":
        if lord.cylinder != "calendar" or lord.cylinder_calendar_box is None:
            raise IllegalAction("not_on_calendar", f"{lord_id}'s cylinder is not on the Calendar")
        lord.cylinder_calendar_box = max(0, min(13, lord.cylinder_calendar_box + delta))
        return {"shifted": "cylinder", "box": lord.cylinder_calendar_box}
    if what == "service":
        if lord.service_box is None:
            raise IllegalAction("no_service", f"{lord_id} has no Service Marker")
        lord.service_box = max(0, min(13, lord.service_box + delta))
        from .state import shift_vassal_service
        shift_vassal_service(gs, lord, delta)  # 6.2
        return {"shifted": "service", "box": lord.service_box}
    raise IllegalAction("bad_what", "shift 'cylinder' or 'service'")


def _remove_themata(gs: GameState, thema: str, unit: str | None = None) -> dict:
    box = gs.themata.get(thema, [])
    for i, m in enumerate(box):
        if unit is None or m.unit == unit:
            box.pop(i)
            return {"removed": {"thema": thema, "unit": m.unit}}
    raise IllegalAction("no_themata", f"no matching Themata in {thema}")


# --- per-card resolvers (immediate Events) ----------------------------------

def _wastage_once(gs, lord) -> bool:
    """Discard one excess Asset (or a This-Lord Capability) if the Lord qualifies (4.7.4)."""
    assets = {"carts": lord.assets.carts, "provender": lord.assets.provender,
              "coin": lord.assets.coin, "loot": lord.assets.loot}
    top = max(assets, key=lambda k: assets[k])
    if assets[top] > 1:
        setattr(lord.assets, top, assets[top] - 1)
        return True
    if len(lord.capabilities) > 1:
        card = lord.capabilities.pop()
        gs.side_decks(sd.card(card)["side"]).draw_deck.append(card)  # route by printed side (4.7.4/3.4.4)
        return True
    return False


def _discard_random_held(gs, side, roller):
    held = gs.side_decks(side).held_events
    if not held:
        return {"no_op": True, "reason": "no Held cards"}
    idx = roller.d6() % len(held)
    card = held.pop(idx)
    gs.side_decks(side).draw_deck.append(card)
    return {"discarded_held": card}


def _distance_within(gs, a, b, n):
    from . import map as gmap
    from collections import deque
    seen = {a}; dq = deque([(a, 0)])
    while dq:
        cur, d = dq.popleft()
        if cur == b:
            return True
        if d >= n:
            continue
        for e in gmap.ways_from(cur):
            if e["to"] not in seen:
                seen.add(e["to"]); dq.append((e["to"], d + 1))
    return False


def _set_treachery(gs, side):
    """A Treachery Event adds that side's Treachery card to this Season's Plan
    and the opponent adds a No Command (4.1/1.4). Only one per Arts of War phase."""
    if gs.meta.notes.get("treachery_side"):
        return {"no_op": True, "reason": "a Treachery Event already occurred this Arts of War phase"}
    gs.meta.notes["treachery_side"] = side
    gs.meta.notes["treachery_no_command_side"] = "roman" if side == "seljuk" else "seljuk"
    return {"treachery_added_for": side}


def _ev_roman_persuasion(gs, args, roller):       # R8
    return _set_treachery(gs, "roman")


def _ev_norman_extortion(gs, args, roller):       # S16
    return _set_treachery(gs, "seljuk")


def _ev_norman_pay_revolt(gs, args, roller):      # S19
    return _set_treachery(gs, "seljuk")


def _ev_flooded_river(gs, args, roller):          # R1*
    if "R1" in gs.meta.asterisks_used:
        lid = args.get("lord")
        if lid in gs.lords:
            # -1 Lordship this Muster. Use a persistent flag that survives the
            # muster-segment reset (set here during Arts of War, applied at Muster).
            gs.lords[lid].flags["lordship_persist"] = int(gs.lords[lid].flags.get("lordship_persist", 0)) - 1
        return {"already_marked": True, "lordship_penalty": lid}
    aa = gs.lords["alp_arslan"]
    n = sum(1 for _ in range(3) if _wastage_once(gs, aa))
    gs.meta.asterisks_used.append("R1")
    return {"alp_arslan_wastage_times": n}


def _ev_chrysoskoulos(gs, args, roller):          # R11
    if gs.lords["arisighi"].side != "roman":
        return {"no_op": True, "reason": "Arisighi not a Roman ally"}
    return _discard_random_held(gs, "seljuk", roller)


def _ev_anglo_saxon(gs, args, roller):            # R16
    lid = args["lord"]; l = gs.lords[lid]
    if l.side != "roman" or lid in ("robert_crepin", "roussel_de_bailleul") or l.forces.get("varangian_guard", 0) > 0:
        return {"no_op": True}
    if sum(x.forces.get("varangian_guard", 0) for x in gs.lords.values()) >= 2:
        return {"no_op": True, "reason": "no Varangian Guard available"}
    l.forces["varangian_guard"] = l.forces.get("varangian_guard", 0) + 1
    return {"added_varangian": lid}


def _ev_assassination(gs, args, roller):          # R22
    ik = gs.lords["ibn_khan"]
    if ik.mustered and _distance_within(gs, ik.cylinder, "aleppo", 2):
        return _shift_calendar(gs, "ibn_khan", "service", args.get("direction", "left"))
    if ik.mustered:
        from . import actions
        actions._disband_beyond(gs, ik)
        return {"disbanded": "ibn_khan"}
    return {"no_op": True, "reason": "Ibn Khan not Mustered (R22)"}


def _ev_norman_scheming(gs, args, roller):        # S11
    if gs.lords["robert_crepin"].side != "seljuk" and gs.lords["roussel_de_bailleul"].side != "seljuk":
        return {"no_op": True, "reason": "no Seljuk-allied Norman"}
    return _discard_random_held(gs, "roman", roller)


def _ev_moustache(gs, args, roller):              # S9 (This Campaign)
    gs.meta.notes["moustache_campaign"] = True
    return {"this_campaign": "alp_arslan_forage_minus2"}


def _ev_mercenary_discipline(gs, args, roller):   # S25
    n = 0
    for l in gs.lords.values():
        if l.side == "roman" and l.mustered and gs.locales[l.cylinder].ravaged_side is not None:
            if _wastage_once(gs, l):
                n += 1
    return {"roman_wastage": n}


def _ev_peace_offering(gs, args, roller):         # S13
    gs.meta.notes["peace_offering_season"] = True
    if "S13" not in gs.seljuk.capabilities_in_play:
        gs.seljuk.capabilities_in_play.append("S13")  # Gifts Exchanged enters play
    gs.meta.notes["gifts_coins"] = 4                   # 4 Coin on the card
    gs.meta.notes["gifts_taken"] = {"seljuk": 0, "roman": 0}
    return {"this_season": "peace_offering", "gifts_coins": 4}


def _ev_shift_seljuk(gs, args, roller):          # R5 Fatimid Conflict
    return _shift_calendar(gs, args["lord"], args.get("what", "cylinder"), args.get("direction", "left"))


def _shiftable(lord) -> bool:
    """A Lord can be shifted on the Calendar only if he has a Service Marker or a
    cylinder currently on the Calendar. A permanently removed/disbanded Lord has
    neither, so a Calendar-shift Event targeting him has no effect."""
    on_calendar = lord.cylinder == "calendar" and lord.cylinder_calendar_box is not None
    return lord.service_box is not None or on_calendar


def _ev_afsin_recalled(gs, args, roller):        # R12
    afsin = gs.lords["afsin_beg"]
    if not _shiftable(afsin):
        # Afsin Beg permanently removed: nothing to shift, the Event has no
        # effect (the card does not call for a replacement Event draw).
        return {"no_op": True, "reason": "Afsin Beg has no Service Marker or Calendar cylinder to shift"}
    return _shift_calendar(gs, "afsin_beg", args.get("what", "service"), args.get("direction", "left"))


def _ev_doukai(gs, args, roller):                # S12 Doukai Court Intrigues
    return _shift_calendar(gs, args["lord"], args.get("what", "cylinder"), args.get("direction", "left"))


def _ev_manuel_ill(gs, args, roller):            # S14 Manuel Komnenos Falls Ill
    mk = gs.lords["manuel_komnenos"]
    if not _shiftable(mk):
        return {"no_op": True, "reason": "Manuel Komnenos has no Service Marker or Calendar cylinder to shift"}
    return _shift_calendar(gs, "manuel_komnenos", args.get("what", "service"), args.get("direction", "left"))


def _ev_reinforcements_denied(gs, args, roller):  # S23
    return _shift_calendar(gs, args["lord"], "service", args.get("direction", "left"))


def _ev_afsin_murders(gs, args, roller):         # R10* Afsin Murders Seljuk Officer
    gs.meta.notes["afsin_fealty_2"] = True
    if "R10" not in gs.meta.asterisks_used:
        gs.meta.asterisks_used.append("R10")
    return {"afsin_fealty": 2}


def _ev_thrakion(gs, args, roller):              # R13 Thrakion Reinforcements (return a removed Themata)
    from .state import ThemataMarker
    thema = args["thema"]; unit = args["unit"]
    gs.themata.setdefault(thema, []).append(ThemataMarker(unit=unit, symbols=args.get("symbols", 1)))
    return {"returned": {"thema": thema, "unit": unit}}


def _ev_aleppo_independence(gs, args, roller):   # R14
    if gs.locales["aleppo"].conquered_side is not None:
        return {"no_op": True, "reason": "Aleppo already Conquered"}
    gs.meta.aleppo_independence_played = True
    gs.meta.notes["aleppo_friendly_both"] = True
    return {"aleppo_independence": True}


def _draw_replacement_event(gs, side, roller):
    """Card-text "discard and draw a new Event": draw the next Arts-of-War card
    for ``side`` and classify it (immediate -> a fresh pending, Hold -> held,
    This-Campaign -> filed/applied), as at the normal AoW draw (3.1.3)."""
    deck = gs.side_decks(side).draw_deck
    if not deck:
        return None
    if roller is not None:
        roller.shuffle(deck)
    card = deck.pop()
    from . import actions
    actions._classify_drawn_event(gs, side, card, roller)
    return card


def _ev_emir_spurns(gs, args, roller):           # R15* (Emir of Aleppo Spurns Alp Arslan)
    """If Aleppo is Seljuk-Conquered with no Siege marker: place Independent
    Aleppo (or, if it is already present, make Aleppo Roman-Conquered); adjust
    VP; mark the once-per-game Calendar. Otherwise (already triggered, an enemy
    Seljuk Lord is in Aleppo, or Aleppo is Roman-Conquered) the Event has no
    effect: discard and draw a replacement Event."""
    aleppo = gs.locales["aleppo"]
    seljuk_lord_in_aleppo = any(l.mustered and l.cylinder == "aleppo" and l.side == "seljuk"
                                for l in gs.lords.values())
    eligible = (aleppo.conquered_side == "seljuk" and aleppo.siege_markers == 0)
    if ("R15" in gs.meta.asterisks_used or aleppo.conquered_side == "roman"
            or seljuk_lord_in_aleppo or not eligible):
        return {"no_op": True, "reason": "Aleppo not an eligible Seljuk conquest / already triggered",
                "replacement": _draw_replacement_event(gs, "roman", roller)}
    if not gs.meta.independent_aleppo_on_map:
        gs.meta.independent_aleppo_on_map = True   # place Independent Aleppo (no longer Seljuk-held)
        aleppo.conquered_side = None
        aleppo.conquered_count = 0
        result = {"independent_aleppo": True}
    else:
        gs.meta.independent_aleppo_on_map = False   # already present -> Roman Conquered instead
        aleppo.conquered_side = "roman"
        aleppo.conquered_count = {"fort": 1, "town": 2, "city": 3}[sd.locale("aleppo")["type"]]
        result = {"roman_conquered": "aleppo"}
    gs.meta.asterisks_used.append("R15")            # once-per-game (mark the Calendar)
    gs.meta.vp = scenarios.score(gs)                # adjust VP
    return result


def _ev_resilient_agriculture(gs, args, roller):  # R19 (remove up to 2 Seljuk Ravaged in the Roman Empire)
    removed = 0
    for lid, loc in gs.locales.items():
        if removed >= 2:
            break
        if loc.ravaged_side == "seljuk" and sd.locale(lid)["allegiance"] == "roman":
            loc.ravaged_side = None
            removed += 1
    gs.meta.vp = scenarios.score(gs)
    return {"ravaged_removed": removed}


def _ev_armenian_resistance(gs, args, roller):   # R20
    loc = args["locale"]
    if loc not in ("khliat", "manzikert", "arkesh"):
        raise IllegalAction("bad_locale", "choose Khliat, Manzikert, or Arkesh (R20)")
    from . import actions
    if actions.current_allegiance(gs, loc) != "seljuk":
        return {"no_op": True, "reason": f"{loc} is not Seljuk friendly (R20)"}
    gs.locales[loc].conquered_side = "roman"
    gs.locales[loc].conquered_count = {"fort": 1, "town": 2, "city": 3}[sd.locale(loc)["type"]]
    gs.meta.vp = scenarios.score(gs)
    return {"roman_conquered": loc}


_S7_BORDER_THEMATA = ("Iberia", "Mesopotamia", "Melitene", "Antiocheia")


def _ev_deserters(gs, args, roller):             # S7 (remove 1 Themata from a border Thema)
    thema = args.get("thema")
    if thema is not None and thema not in _S7_BORDER_THEMATA:
        raise IllegalAction("bad_thema", "must be a border Thema (S7)")
    # No valid target is a no-op, not an unresolvable Event (matches R11/R16/S11/
    # S22 etc.): if no border Thema has a marker the Event has no effect.
    if not any(gs.themata.get(t) for t in _S7_BORDER_THEMATA):
        return {"no_op": True, "reason": "no border Themata to remove (S7)"}
    if thema is None or not gs.themata.get(thema):
        thema = next(t for t in _S7_BORDER_THEMATA if gs.themata.get(t))
    return _remove_themata(gs, thema, args.get("unit"))


def _ev_thematic_desert(gs, args, roller):       # S15 (Alp Arslan in a Thema removes 1 Themata there)
    """Alp Arslan in a Thema removes 1 Levied or Unlevied Themata Service marker
    there (card clarification: Unlevied in the Thema box -- even Besieged/
    defending a Stronghold -- or Levied onto the Roman Commander's mat). Search
    all three: the Unlevied box, defending markers at his Locale, and Levied
    markers on Lord mats at his Locale."""
    aa = gs.lords["alp_arslan"]
    if not aa.mustered:
        return {"no_op": True, "reason": "Alp Arslan not in a Thema"}
    thema = sd.locale(aa.cylinder)["thema"]
    if thema is None:
        return {"no_op": True, "reason": "Alp Arslan not in a Thema"}
    unit = args.get("unit")
    loc = aa.cylinder
    src = args.get("source")  # optional: "unlevied" | "defending" | "levied"

    def _match(m):
        return unit is None or m.unit == unit

    if src in (None, "unlevied"):
        box = gs.themata.get(thema, [])
        for i, m in enumerate(box):
            if _match(m):
                box.pop(i)
                return {"removed": {"thema": thema, "unit": m.unit, "source": "unlevied"}}
    if src in (None, "defending"):
        deff = gs.locales[loc].themata_defending
        for i, m in enumerate(deff):
            if _match(m):
                mk = deff.pop(i)
                return {"removed": {"thema": thema, "unit": mk.unit, "source": "defending", "locale": loc}}
    if src in (None, "levied"):
        for l in gs.lords.values():
            if l.cylinder != loc:
                continue
            for i, m in enumerate(l.themata_on_mat):
                if _match(m):
                    mk = l.themata_on_mat.pop(i)
                    return {"removed": {"thema": thema, "unit": mk.unit, "source": "levied", "lord": l.id}}
    # No matching marker in the box, defending, or on co-located mats: no effect
    # (do not raise -- an immediate Event that can never resolve stalls the Levy).
    return {"no_op": True, "reason": f"no Levied/Unlevied Themata to remove in {thema} / at {loc}"}


def _ev_siege_of_bari(gs, args, roller):         # S5* (remove up to 2 Unlevied Themata)
    if "S5" in gs.meta.asterisks_used:
        # Already marked: instead, 1 Seljuk Lord gains +1 Lordship this Muster.
        lid = args.get("lord")
        l = gs.lords.get(lid)
        if l is None or l.side != "seljuk":
            return {"already_marked": True, "no_op": True,
                    "reason": "need a Seljuk Lord for the +1 Lordship effect"}
        l.flags["lordship_persist"] = int(l.flags.get("lordship_persist", 0)) + 1
        return {"already_marked": True, "lordship_bonus": lid}
    removed = []
    for thema in args.get("themata", []):
        try:
            removed.append(_remove_themata(gs, thema, args.get("unit"))["removed"])
        except IllegalAction:
            pass
        if len(removed) >= 2:
            break
    gs.meta.asterisks_used.append("S5")
    return {"removed": removed}


def _ev_merchant_financing(gs, args, roller):    # S8 (exchange Carts <-> Coin for one Seljuk Lord)
    lord = gs.lords[args["lord"]]
    n = int(args.get("amount", 0))
    if args.get("to") == "coin":
        n = min(n, lord.assets.carts)
        lord.assets.carts -= n; lord.assets.coin = min(8, lord.assets.coin + n)
    else:
        n = min(n, lord.assets.coin)
        lord.assets.coin -= n; lord.assets.carts = min(8, lord.assets.carts + n)
    return {"exchanged": n, "to": args.get("to")}


def _ev_consolidates_power(gs, args, roller):    # S20 (lower THIS YEAR's Seljuk Unity threshold)
    """Lower this year's Seljuk Unity threshold by the number of *permanently
    disbanded* Seljuk Lords (card + clarification: no permanently disbanded ->
    no effect). 'Permanently disbanded' excludes scenario setup-removed Lords
    (matches campaign._permanently_disbanded), and only this year's threshold box
    -- the upcoming Winter box (3/6/9) -- is lowered, not every year's."""
    disbanded = sum(1 for lid, l in gs.lords.items()
                    if sd.lord(lid)["side"] == "seljuk"
                    and l.cylinder == "removed" and not l.flags.get("setup_removed"))
    if disbanded == 0:
        return {"no_op": True, "reason": "no permanently disbanded Seljuk Lords (S20)"}
    boxes = sorted(int(b) for b in gs.meta.seljuk_unity_targets)
    this_year = next((b for b in boxes if b >= gs.meta.calendar_box), None)
    if this_year is None:
        return {"no_op": True, "reason": "no Seljuk Unity threshold remaining this game (S20)"}
    key = str(this_year)
    gs.meta.seljuk_unity_targets[key] = max(0, gs.meta.seljuk_unity_targets[key] - disbanded)
    return {"unity_lowered_by": disbanded, "box": this_year,
            "threshold": gs.meta.seljuk_unity_targets[key]}


def _ev_massacre(gs, args, roller):              # S22 (a Seljuk Lord at an Enemy Locale +1 Loot)
    from . import actions
    # "no valid target" is a no-op, not an error the consumer must hand-skip
    # (matches R11/R16/S11/R14). Eligible: a Mustered Seljuk Lord on the map at a
    # Locale not Friendly to Seljuk -- counts even if Besieged (card text).
    eligible = [lid for lid, l in gs.lords.items()
                if l.side == "seljuk" and l.mustered and l.cylinder in gs.locales
                and actions.current_allegiance(gs, l.cylinder) != "seljuk"]
    if not eligible:
        return {"no_op": True, "reason": "no Seljuk Lord at an Enemy Locale (S22)"}
    lid = args.get("lord")
    if lid is None:
        raise IllegalAction("need_target", f"S22: choose a Seljuk Lord at an Enemy Locale {eligible}")
    if lid not in eligible:
        raise IllegalAction("not_enemy", f"S22: {lid} is not a Seljuk Lord at an Enemy Locale")
    gs.lords[lid].assets.loot = min(8, gs.lords[lid].assets.loot + 1)
    return {"loot_added": lid}


def _ev_unpredictable_weather(gs, playing_side: str) -> dict:
    """R17/S17 (This Campaign): Spring/Autumn -> Passes blocked for Supply/March/
    Avoid/Retreat; Summer -> Plan stack 9 and the enemy must use 1 No Command."""
    season = (gs.meta.calendar_box - 1) % 3  # 0 Spring, 1 Summer, 2 Autumn
    if season == 1:
        enemy = "seljuk" if playing_side == "roman" else "roman"
        gs.meta.notes["weather_plan9"] = True
        gs.meta.notes["weather_no_command_side"] = enemy
        return {"weather": "summer", "plan_stack": 9, "enemy_no_command": enemy}
    gs.meta.notes["weather_pass_block"] = True
    return {"weather": "spring_autumn", "passes_blocked": True}


def _ev_weather_roman(gs, args, roller):          # R17
    return _ev_unpredictable_weather(gs, "roman")


def _ev_weather_seljuk(gs, args, roller):         # S17
    return _ev_unpredictable_weather(gs, "seljuk")


_RESOLVERS = {
    "R17": _ev_weather_roman, "S17": _ev_weather_seljuk,
    "R5": _ev_shift_seljuk, "R10": _ev_afsin_murders, "R12": _ev_afsin_recalled,
    "R13": _ev_thrakion, "R14": _ev_aleppo_independence, "R19": _ev_resilient_agriculture,
    "R15": _ev_emir_spurns, "R20": _ev_armenian_resistance,
    "S5": _ev_siege_of_bari, "S7": _ev_deserters, "S8": _ev_merchant_financing,
    "S12": _ev_doukai, "S14": _ev_manuel_ill, "S15": _ev_thematic_desert,
    "S20": _ev_consolidates_power, "S22": _ev_massacre, "S23": _ev_reinforcements_denied,
    "R8": _ev_roman_persuasion, "S16": _ev_norman_extortion, "S19": _ev_norman_pay_revolt,
    "R1": _ev_flooded_river, "R11": _ev_chrysoskoulos, "R16": _ev_anglo_saxon,
    "R22": _ev_assassination, "S9": _ev_moustache, "S11": _ev_norman_scheming,
    "S13": _ev_peace_offering, "S25": _ev_mercenary_discipline,
}


def resolvable() -> set[str]:
    return set(_RESOLVERS)


def resolve_event(gs: GameState, card_id: str, args: dict, roller: DiceRoller) -> dict[str, Any]:
    pend = next((p for p in gs.meta.pending
                 if p["type"] == "event_pending_resolution" and p["card"] == card_id), None)
    if pend is None:
        raise IllegalAction("no_pending_event", f"no pending Event {card_id}")
    if card_id not in _RESOLVERS:
        # Tracked-but-not-yet-implemented Event: discard with no mechanical effect.
        gs.meta.pending.remove(pend)
        return {"ok": True, "card": card_id, "no_op": True, "reason": "resolver not yet implemented (Phase 4 remainder)"}
    try:
        result = _RESOLVERS[card_id](gs, args or {}, roller)
    except (KeyError, IndexError, TypeError) as e:
        raise IllegalAction("missing_or_bad_arg", f"Event {card_id} needs a valid argument ({e})")
    gs.meta.pending.remove(pend)
    # Return the card to its deck (immediate Events are not held).
    side = pend["side"]
    if card_id not in gs.side_decks(side).draw_deck:
        gs.side_decks(side).draw_deck.append(card_id)
    return {"ok": True, "action": "resolve_event", "card": card_id, **result}


# === Hold Events played at a later moment (4.1.3 / 3.1.3) ===================
# Self-contained timing hooks here; the Battle-order Hold Events (Mountain
# Ambush, Cavalry Charge, Command Confusion, Betrayal) are applied inside the
# Battle engine via begin_battle/resolve_storm 'events' arguments.

def _remove_turkic_at(gs, locale, count):
    removed = 0
    for l in gs.lords.values():
        if removed >= count:
            break
        if l.mustered and l.cylinder == locale:
            while removed < count and l.forces.get("turkic_horse", 0) > 0:
                l.forces["turkic_horse"] -= 1
                removed += 1
    return removed


def _hold_michael_attaleiates(gs, args, roller):   # R6 (Muster, on Romanos)
    if gs.meta.subphase != "levy.muster":
        raise IllegalAction("wrong_timing", "play during Muster (R6)")
    rom = gs.lords["romanos_diogenes"]
    if not rom.mustered:
        raise IllegalAction("not_available", "Romanos is not Mustered")
    rom.flags["lordship_bonus"] = int(rom.flags.get("lordship_bonus", 0)) + 1
    return {"romanos_lordship": "+1"}


def _hold_eastern_rebellions(gs, args, roller):     # S10 (Muster, on Alp Arslan)
    if gs.meta.subphase != "levy.muster":
        raise IllegalAction("wrong_timing", "play during Muster (S10)")
    aa = gs.lords["alp_arslan"]
    if not aa.mustered:
        raise IllegalAction("not_available", "Alp Arslan is not Mustered")
    aa.flags["lordship_bonus"] = int(aa.flags.get("lordship_bonus", 0)) + 1
    return {"alp_arslan_lordship": "+1"}


def _hold_sultans_horse(gs, args, roller):          # R4 (remove 1 Siege where Alp Arslan besieging >1)
    aa = gs.lords["alp_arslan"]
    if not aa.mustered or gs.locales[aa.cylinder].siege_markers <= 1:
        raise IllegalAction("not_applicable", "Alp Arslan must be at a Locale with >1 Siege marker (R4)")
    gs.locales[aa.cylinder].siege_markers -= 1
    return {"removed_siege_at": aa.cylinder}


def _hold_nomadic_tribes(gs, args, roller):         # R21 (remove up to 2 Turkic at a Locale)
    n = _remove_turkic_at(gs, args["locale"], min(2, int(args.get("count", 2))))
    return {"turkic_removed": n}


def _hold_common_cultural(gs, args, roller):        # S21 (remove up to 2 Turkic at a Locale)
    n = _remove_turkic_at(gs, args["locale"], min(2, int(args.get("count", 2))))
    return {"turkic_removed": n}


def _hold_bad_omens(gs, args, roller):              # S24 (reorder top 2 unrevealed Roman Plan cards)
    pp = gs.roman.plan_pointer
    plan = gs.roman.command_plan
    if len(plan) - pp >= 2:
        plan[pp], plan[pp + 1] = plan[pp + 1], plan[pp]
        return {"reordered": plan[pp:pp + 2]}
    return {"no_op": True, "reason": "fewer than 2 unrevealed Roman cards"}


def _hold_summer_heat(gs, args, roller):            # R3/S4 (enemy Command 1 after reveal)
    from . import campaign
    if gs.meta.subphase != "campaign.command" or gs.meta.active_lord is None:
        raise IllegalAction("wrong_timing", "play after the enemy reveals a Command card (R3/S4)")
    if campaign.season_index(gs.meta.calendar_box) != 1:
        raise IllegalAction("not_summer", "Summer Heat is played in Summer (R3/S4)")
    gs.meta.actions_remaining = min(gs.meta.actions_remaining, 1)  # that Lord is Command 1
    gs.meta.pending[:] = [p for p in gs.meta.pending if p["type"] != "summer_heat"]
    return {"command_1": gs.meta.active_lord}


def kleisourai_hit(gs, lord, roller, unit=None):
    """Apply Kleisourai's 1 Battle Hit to a moving Seljuk Lord (R23): roll
    Protection for the assigned unit; on failure the unit is eliminated with no
    recovery (clarification). Shared by the standalone resolver and the
    pass-crossing reaction window."""
    from . import capabilities
    avail = [u for u, n in lord.forces.items() if n > 0]
    if not avail:
        return {"lord": lord.id, "no_op": True}
    unit = unit or avail[0]
    lo, hi = capabilities.protection_range(gs, lord.id, unit, "melee", storm=False)  # treated as a Battle Hit
    roll = roller.d6()
    if not (lo <= roll <= hi):
        lord.forces[unit] -= 1  # eliminated, no recovery (clarification)
        return {"lord": lord.id, "eliminated": unit, "roll": roll}
    return {"lord": lord.id, "protected": unit, "roll": roll}


def _hold_kleisourai(gs, args, roller):             # R23 (1 Hit on a moving Seljuk Lord crossing a Pass)
    lord = gs.lords[args["lord"]]
    if lord.side != "seljuk":
        raise IllegalAction("bad_target", "Kleisourai hits a moving Seljuk Lord (R23)")
    res = kleisourai_hit(gs, lord, roller, args.get("unit"))
    return {k: v for k, v in res.items() if k != "lord"}


_HOLD_RESOLVERS = {
    "R6": _hold_michael_attaleiates, "S10": _hold_eastern_rebellions, "R4": _hold_sultans_horse,
    "R21": _hold_nomadic_tribes, "S21": _hold_common_cultural, "S24": _hold_bad_omens,
    "R3": _hold_summer_heat, "S4": _hold_summer_heat, "R23": _hold_kleisourai,
}


def play_hold_event(gs: GameState, card_id: str, args: dict, roller: DiceRoller) -> dict[str, Any]:
    side = sd.card(card_id)["side"]
    if card_id not in gs.side_decks(side).held_events:
        raise IllegalAction("not_held", f"{card_id} is not a Held Event for {side}")
    if card_id not in _HOLD_RESOLVERS:
        raise IllegalAction("hold_not_implemented",
                            f"{card_id} is a Battle/timing Hold Event without a self-contained hook yet")
    try:
        result = _HOLD_RESOLVERS[card_id](gs, args or {}, roller)
    except (KeyError, IndexError, TypeError) as e:
        raise IllegalAction("missing_or_bad_arg", f"Hold Event {card_id} needs a valid argument ({e})")
    gs.side_decks(side).held_events.remove(card_id)
    gs.side_decks(side).draw_deck.append(card_id)
    return {"ok": True, "action": "play_hold_event", "card": card_id, **result}


# --- Hold Event menu enumeration (SMOKE-008 follow-up) -----------------------
# Surface the self-contained Hold Events whose play window coincides with a
# decision point the engine actually reaches AND where the card's owner is the
# active player. Each predicate is at least as strict as the resolver's own
# validation, so every offered entry round-trips through play_hold_event.
#
# Representable now (active-player menu point in-window):
#   R6  Michael Attaleiates  - Roman Muster, on Romanos (Lordship +1)
#   S10 Eastern Rebellions    - Seljuk Muster, on Alp Arslan (Lordship +1)
#   S24 Bad Omens             - on a freshly-revealed Seljuk Command card,
#                               before any Command action (reorder Roman Plan)
#   R4  Sultan's Horse        - Roman Command turn, Alp Arslan Besieging a
#                               Locale with >1 Siege marker (remove 1 Siege)
#
# Deferred (no decision window modelled yet -> would be over-enumeration):
#   R3/S4 Summer Heat, R23 Kleisourai  - out-of-turn reactions to the enemy
#   R21/S21 Turkic removal             - Battle/Storm "play events" step
#   R14 Imperial Coffers (discard)     - Arts of War (auto-resolved) step
# These remain reachable via the documented do/apply action; the negative
# enumerator tests assert they never appear in the normal menu.

def _holds(gs: GameState, side: str) -> set[str]:
    return set(gs.side_decks(side).held_events)


def held_event_menu(gs: GameState) -> list[dict[str, Any]]:
    """Playable Hold Events at the current decision point, for the active side."""
    out: list[dict[str, Any]] = []
    meta = gs.meta
    side = meta.active_player

    # --- Muster window (R6 Roman, S10 Seljuk) ---------------------------------
    if meta.subphase == "levy.muster":
        held = _holds(gs, side)
        if side == "roman" and "R6" in held and gs.lords["romanos_diogenes"].mustered:
            out.append({"type": "play_hold_event", "card": "R6",
                        "_desc": "Hold Event R6 Michael Attaleiates: Romanos Lordship +1 (Muster)"})
        if side == "seljuk" and "S10" in held and gs.lords["alp_arslan"].mustered:
            out.append({"type": "play_hold_event", "card": "S10",
                        "_desc": "Hold Event S10 Eastern Rebellions: Alp Arslan Lordship +1 (Muster)"})

    # --- Command window (S24 Seljuk before acting, R4 Roman turn) -------------
    if meta.subphase == "campaign.command" and meta.active_lord is not None:
        held = _holds(gs, side)
        if side == "seljuk" and "S24" in held:
            # "immediately after revealing a Seljuk Command card, before taking
            # any Command actions" -> no action spent yet, and >=2 unrevealed
            # Roman Plan cards remain to reorder (else it is a pure no-op).
            no_action_yet = meta.actions_remaining == meta.notes.get("card_full_actions")
            roman_unrevealed = len(gs.roman.command_plan) - gs.roman.plan_pointer
            if no_action_yet and roman_unrevealed >= 2:
                out.append({"type": "play_hold_event", "card": "S24",
                            "_desc": "Hold Event S24 Bad Omens: inspect/reorder top 2 Roman Plan cards"})
        if side == "roman" and "R4" in held:
            aa = gs.lords["alp_arslan"]
            if aa.mustered and gs.locales[aa.cylinder].siege_markers > 1:
                out.append({"type": "play_hold_event", "card": "R4",
                            "_desc": f"Hold Event R4 Sultan's Horse: remove 1 Siege at {aa.cylinder}"})
    return out
