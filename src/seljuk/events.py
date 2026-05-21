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
        lord.capabilities.pop()
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
            gs.lords[lid].flags["lordship_spent"] = int(gs.lords[lid].flags.get("lordship_spent", 0)) + 1
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


def _ev_peace_offering(gs, args, roller):         # S13 (This Season; coin-gate is a noted partial)
    gs.meta.notes["peace_offering_season"] = True
    if "S13" not in gs.seljuk.capabilities_in_play:
        gs.seljuk.capabilities_in_play.append("S13")  # Gifts Exchanged enters play
    return {"this_season": "peace_offering", "note": "Approach/Storm/Siege coin-gate is a documented partial"}


def _ev_shift_seljuk(gs, args, roller):          # R5 Fatimid Conflict
    return _shift_calendar(gs, args["lord"], args.get("what", "cylinder"), args.get("direction", "left"))


def _ev_afsin_recalled(gs, args, roller):        # R12
    return _shift_calendar(gs, "afsin_beg", args.get("what", "service"), args.get("direction", "left"))


def _ev_doukai(gs, args, roller):                # S12 Doukai Court Intrigues
    return _shift_calendar(gs, args["lord"], args.get("what", "cylinder"), args.get("direction", "left"))


def _ev_manuel_ill(gs, args, roller):            # S14 Manuel Komnenos Falls Ill
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
    gs.locales[loc].conquered_side = "roman"
    gs.locales[loc].conquered_count = {"fort": 1, "town": 2, "city": 3}[sd.locale(loc)["type"]]
    gs.meta.vp = scenarios.score(gs)
    return {"roman_conquered": loc}


def _ev_deserters(gs, args, roller):             # S7 (remove 1 Themata from a border Thema)
    thema = args["thema"]
    if thema not in ("Iberia", "Mesopotamia", "Melitene", "Antiocheia"):
        raise IllegalAction("bad_thema", "must be a border Thema (S7)")
    return _remove_themata(gs, thema, args.get("unit"))


def _ev_thematic_desert(gs, args, roller):       # S15 (Alp Arslan in a Thema removes 1 Themata there)
    aa = gs.lords["alp_arslan"]
    thema = sd.locale(aa.cylinder)["thema"] if aa.mustered else None
    if thema is None:
        return {"no_op": True, "reason": "Alp Arslan not in a Thema"}
    return _remove_themata(gs, thema, args.get("unit"))


def _ev_siege_of_bari(gs, args, roller):         # S5* (remove up to 2 Unlevied Themata)
    removed = []
    for thema in args.get("themata", []):
        try:
            removed.append(_remove_themata(gs, thema, args.get("unit"))["removed"])
        except IllegalAction:
            pass
        if len(removed) >= 2:
            break
    if "S5" not in gs.meta.asterisks_used:
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


def _ev_consolidates_power(gs, args, roller):    # S20 (lower Seljuk Unity by # permanently disbanded Seljuk Lords)
    disbanded = sum(1 for lid, l in gs.lords.items()
                    if sd.lord(lid)["side"] == "seljuk" and l.cylinder == "removed")
    for box, val in list(gs.meta.seljuk_unity_targets.items()):
        gs.meta.seljuk_unity_targets[box] = max(0, val - disbanded)
    return {"unity_lowered_by": disbanded}


def _ev_massacre(gs, args, roller):              # S22 (a Seljuk Lord at an Enemy Locale +1 Loot)
    lord = gs.lords[args["lord"]]
    from . import actions
    if actions.current_allegiance(gs, lord.cylinder) == "seljuk":
        raise IllegalAction("not_enemy", "Lord must be at an Enemy Locale (S22)")
    lord.assets.loot = min(8, lord.assets.loot + 1)
    return {"loot_added": lord.id}


_RESOLVERS = {
    "R5": _ev_shift_seljuk, "R10": _ev_afsin_murders, "R12": _ev_afsin_recalled,
    "R13": _ev_thrakion, "R14": _ev_aleppo_independence, "R19": _ev_resilient_agriculture,
    "R20": _ev_armenian_resistance,
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
    return {"command_1": gs.meta.active_lord}


def _hold_kleisourai(gs, args, roller):             # R23 (1 Hit on a moving Seljuk Lord crossing a Pass)
    from . import capabilities
    lord = gs.lords[args["lord"]]
    if lord.side != "seljuk":
        raise IllegalAction("bad_target", "Kleisourai hits a moving Seljuk Lord (R23)")
    avail = [u for u, n in lord.forces.items() if n > 0]
    if not avail:
        return {"no_op": True}
    unit = args.get("unit", avail[0])
    lo, hi = capabilities.protection_range(gs, lord.id, unit, "melee", storm=False)  # treated as a Battle Hit
    roll = roller.d6()
    if not (lo <= roll <= hi):
        lord.forces[unit] -= 1  # eliminated, no recovery (clarification)
        return {"eliminated": unit, "roll": roll}
    return {"protected": unit, "roll": roll}


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
