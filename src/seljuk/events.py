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
    result = _RESOLVERS[card_id](gs, args or {}, roller)
    gs.meta.pending.remove(pend)
    # Return the card to its deck (immediate Events are not held).
    side = pend["side"]
    if card_id not in gs.side_decks(side).draw_deck:
        gs.side_decks(side).draw_deck.append(card_id)
    return {"ok": True, "action": "resolve_event", "card": card_id, **result}
