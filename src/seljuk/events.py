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
from .state import GameState, IllegalAction, LordState, ThemataMarker


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


def _record_removed_themata(gs, marker, home_thema):
    """Add an eliminated Themata Service Marker to the removed-from-play pile so
    R13 Thrakion Reinforcements can later return it to its home Thema."""
    gs.meta.themata_removed.append(
        ThemataMarker(unit=marker.unit, symbols=marker.symbols,
                      home_thema=getattr(marker, "home_thema", None) or home_thema))


def _remove_themata(gs: GameState, thema: str, unit: str | None = None) -> dict:
    box = gs.themata.get(thema, [])
    for i, m in enumerate(box):
        if unit is None or m.unit == unit:
            box.pop(i)
            _record_removed_themata(gs, m, thema)
            return {"removed": {"thema": thema, "unit": m.unit}}
    raise IllegalAction("no_themata", f"no matching Themata in {thema}")


# --- per-card resolvers (immediate Events) ----------------------------------

def _wastage_once(gs, lord) -> bool:
    """Use the same qualification, choices and deck routing as Campaign Wastage."""
    from .campaign import _do_one_wastage
    return _do_one_wastage(gs, lord)


def _discard_random_held(gs, side, roller):
    deck = gs.side_decks(side)
    if not deck.held_events:
        return {"no_op": True, "reason": "no Held cards"}
    card = deck.held_events.pop(roller.randbelow(len(deck.held_events)))
    deck.draw_deck.append(card)
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


def muster_penalty_targets(gs: GameState) -> list[str]:
    """R1/R10 repeat: choose a Lord able to Muster, or a Seljuk Lord still in play."""
    from . import actions

    seljuk_lords = sorted(lid for lid, lord in gs.lords.items()
                          if lord.side == "seljuk" and lord.cylinder != "removed")
    # Arts of War precedes the Muster reset. Last Levy's spending, Hold
    # bonuses and arrival flags do not determine this Levy's eligibility.
    able = [lid for lid in seljuk_lords if actions._at_muster_locale(gs, gs.lords[lid])
            and actions._muster_lordship(gs, gs.lords[lid]) > 0]
    return able or seljuk_lords


def _choose_event_lord(gs: GameState, args: dict, targets: list[str]) -> LordState | None:
    if "lord" not in args:
        if not targets:
            return None
        raise IllegalAction("missing_or_bad_arg", "choose an eligible Lord for this Event")
    lid = args["lord"]
    if not isinstance(lid, str) or lid not in gs.lords:
        raise IllegalAction("bad_lord", f"no such Lord {lid!r}")
    if lid not in targets:
        raise IllegalAction("bad_event_target", f"{lid} is ineligible for this Event")
    return gs.lords[lid]


def _seljuk_lord_minus1_lordship(gs, args):
    lord = _choose_event_lord(gs, args, muster_penalty_targets(gs))
    if lord is None:
        return {"already_marked": True, "no_op": True, "reason": "no Seljuk Lord in play"}
    lord.flags["lordship_persist"] = int(lord.flags.get("lordship_persist", 0)) - 1
    return {"already_marked": True, "lordship_penalty": lord.id}


def _ev_flooded_river(gs, args, roller):          # R1*
    if "R1" in gs.meta.asterisks_used:
        return _seljuk_lord_minus1_lordship(gs, args)
    aa = gs.lords["alp_arslan"]
    if args.get("_interactive_wastage"):
        from .campaign import _queue_wastage
        pending = _queue_wastage(gs, aa, times=3, source="R1")
        gs.meta.asterisks_used.append("R1")
        return {"alp_arslan_wastage_times": 0, "wastage_pending": pending}
    n = sum(1 for _ in range(3) if _wastage_once(gs, aa))
    gs.meta.asterisks_used.append("R1")
    return {"alp_arslan_wastage_times": n}


def _ev_chrysoskoulos(gs, args, roller):          # R11
    if gs.lords["arisighi"].side != "roman":
        return {"no_op": True, "reason": "Arisighi not a Roman ally"}
    return _discard_random_held(gs, "seljuk", roller)


def anglo_saxon_targets(gs: GameState) -> list[str]:
    """R16: eligible Roman Lord mats when the physical pool has a Guard."""
    from . import actions

    unit = "varangian_guard"
    if actions._pool_remaining(gs, unit) <= 0:
        return []
    return sorted(lid for lid, lord in gs.lords.items()
                  if lord.side == "roman" and lord.on_map()
                  and lord.cylinder in gs.locales
                  and lid not in ("robert_crepin", "roussel_de_bailleul")
                  and not (lord.forces.get(unit, 0) or lord.routed.get(unit, 0)))


def _ev_anglo_saxon(gs, args, roller):            # R16
    lord = _choose_event_lord(gs, args, anglo_saxon_targets(gs))
    if lord is None:
        return {"no_op": True, "reason": "no Varangian Guard or eligible Roman Lord available"}
    lord.forces["varangian_guard"] = 1
    return {"added_varangian": lord.id}


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
            if args.get("_interactive_wastage"):
                from .campaign import _queue_wastage
                n += int(_queue_wastage(gs, l, source="S25"))
                continue
            if _wastage_once(gs, l):
                n += 1
    if args.get("_interactive_wastage"):
        return {"roman_wastage": 0, "wastage_pending": n}
    return {"roman_wastage": n}


def _ev_peace_offering(gs, args, roller):         # S13
    gs.meta.notes["peace_offering_season"] = True
    if "S13" not in gs.seljuk.capabilities_in_play:
        gs.seljuk.capabilities_in_play.append("S13")  # Gifts Exchanged enters play
    gs.meta.notes["gifts_coins"] = 4                   # 4 Coin on the card
    gs.meta.notes["gifts_taken"] = {"seljuk": 0, "roman": 0}
    return {"this_season": "peace_offering", "gifts_coins": 4}


def _ev_shift_seljuk(gs, args, roller):          # R5 Fatimid Conflict
    return _resolve_calendar_event(gs, "R5", args)


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
    return _resolve_calendar_event(gs, "S12", args)


def _ev_manuel_ill(gs, args, roller):            # S14 Manuel Komnenos Falls Ill
    mk = gs.lords["manuel_komnenos"]
    if not _shiftable(mk):
        return {"no_op": True, "reason": "Manuel Komnenos has no Service Marker or Calendar cylinder to shift"}
    return _shift_calendar(gs, "manuel_komnenos", args.get("what", "service"), args.get("direction", "left"))


def _ev_reinforcements_denied(gs, args, roller):  # S23
    return _resolve_calendar_event(gs, "S23", args)


def _calendar_event_eligible(lord: LordState, card: str) -> bool:
    if card == "R5":
        return lord.side == "seljuk" and not lord.besieged
    return lord.side == "roman"


def calendar_event_targets(gs: GameState, card: str) -> dict[str, list[str]]:
    """Current allegiance and marker choices for R5, S12 and S23."""
    targets = {}
    for lid, lord in gs.lords.items():
        if not _calendar_event_eligible(lord, card):
            continue
        markers = []
        if card != "S23" and lord.cylinder == "calendar" and lord.cylinder_calendar_box is not None:
            markers.append("cylinder")
        if lord.service_box is not None:
            markers.append("service")
        if markers:
            targets[lid] = markers
    return targets


def _resolve_calendar_event(gs: GameState, card: str, args: dict) -> dict:
    if "lord" not in args and not calendar_event_targets(gs, card):
        return {"no_op": True, "reason": f"{card} has no eligible Calendar marker"}
    lid = args["lord"]
    if not isinstance(lid, str) or lid not in gs.lords:
        raise IllegalAction("bad_lord", f"no such Lord {lid!r}")
    if not _calendar_event_eligible(gs.lords[lid], card):
        eligible = "an Unbesieged Seljuk Lord" if card == "R5" else "a Roman Lord"
        raise IllegalAction("bad_event_target", f"{card} must target {eligible}")
    what = args.get("what", "service" if card == "S23" else "cylinder")
    if card == "S23" and what != "service":
        raise IllegalAction("bad_what", "S23 shifts only Service")
    direction = args.get("direction", "left")
    if direction not in ("left", "right"):
        raise IllegalAction("bad_direction", "choose left or right")
    return _shift_calendar(gs, lid, what, direction)


def _ev_afsin_murders(gs, args, roller):         # R10* Afsin Murders Seljuk Officer
    if "R10" in gs.meta.asterisks_used:
        # Already marked: 1 Seljuk Lord -1 Lordship this Muster instead.
        return _seljuk_lord_minus1_lordship(gs, args)
    gs.meta.notes["afsin_fealty_2"] = True
    gs.meta.asterisks_used.append("R10")
    return {"afsin_fealty": 2}


def _ev_thrakion(gs, args, roller):              # R13 Thrakion Reinforcements
    """Return one removed marker to its home Thema, using its current pile index."""
    pile = gs.meta.themata_removed
    if not pile and "marker_index" not in args:
        return {"no_op": True, "reason": "no Themata previously removed from play to return (R13)"}
    thema, unit, symbols = args.get("thema"), args.get("unit"), args.get("symbols")
    matching = [
        i for i, marker in enumerate(pile)
        if (thema is None or marker.home_thema == thema)
        and (unit is None or marker.unit == unit)
        and (symbols is None or marker.symbols == symbols)
    ]
    index = args.get("marker_index", matching[0] if matching else None)
    if type(index) is not int or index not in matching:
        raise IllegalAction("bad_themata_index", "R13 requires a matching removed Themata marker")
    marker = pile[index]
    home = marker.home_thema
    if home is None:
        raise IllegalAction("no_home_thema", "The removed Themata marker has no home Thema")
    pile.pop(index)
    marker.reset_units()
    gs.themata.setdefault(home, []).append(marker)
    return {"returned": {"thema": home, "unit": marker.unit}, "symbols": marker.symbols}


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


def resilient_agriculture_targets(gs: GameState) -> list[str]:
    return [lid for lid, loc in gs.locales.items()
            if loc.ravaged_side == "seljuk" and sd.locale(lid)["allegiance"] == "roman"]


def _ev_resilient_agriculture(gs, args, roller):  # R19
    eligible = resilient_agriculture_targets(gs)
    count = min(2, len(eligible))
    selected = args.get("locales", [])
    if (not isinstance(selected, list) or len(selected) != count
            or any(lid not in eligible for lid in selected) or len(set(selected)) != count):
        raise IllegalAction("bad_ravaged_selection",
                            f"R19 requires exactly {count} distinct eligible Locales")
    for lid in selected:
        gs.locales[lid].ravaged_side = None
    gs.meta.vp = scenarios.score(gs)
    return {"ravaged_removed": count, "cleared_locales": selected}


def armenian_resistance_targets(gs: GameState) -> list[str]:
    from . import actions
    return [loc for loc in ("khliat", "manzikert", "arkesh")
            if actions.current_allegiance(gs, loc) == "seljuk"]


def _ev_armenian_resistance(gs, args, roller):   # R20
    if {"invest", "choice"} & args.keys():
        raise IllegalAction("opponent_input", "The Seljuk player chooses Siege or Bypass after R20")
    eligible = armenian_resistance_targets(gs)
    if not eligible and "locale" not in args:
        return {"no_op": True, "reason": "no eligible Seljuk-friendly Locale (R20)"}
    loc = args["locale"]
    if loc not in eligible:
        raise IllegalAction("bad_locale", f"R20 requires one of {eligible}")
    st = gs.locales[loc]
    st.conquered_side = "roman"
    st.conquered_count = {"fort": 1, "town": 2, "city": 3}[sd.locale(loc)["type"]]
    result = {"roman_conquered": loc}
    # Clarification: a Strategic Objective marker here returns to available -- it
    # is NOT placed in Constantinople as VP.
    if st.strategic_objective:
        st.strategic_objective = False
        gs.holding_boxes.constantinople_strategic_objectives_available = min(
            3, gs.holding_boxes.constantinople_strategic_objectives_available + 1)
        result["strategic_objective_returned"] = True
    # The Seljuk player chooses the new posture at the now-Roman Stronghold.
    seljuk_here = [l.id for l in gs.lords.values()
                   if l.mustered and l.cylinder == loc and l.side == "seljuk"]
    if seljuk_here:
        gs.meta.pending.append({"type": "besiege_or_bypass", "locale": loc,
                                "lords": seljuk_here, "_owed_by": "seljuk", "source": "R20"})
        result["pending"] = "besiege_or_bypass"
    else:
        from .campaign import _refresh_invest
        _refresh_invest(gs, loc)
    gs.meta.vp = scenarios.score(gs)
    return result


def h_armenian_resistance_invest(gs: GameState, action: dict, roller: DiceRoller) -> dict:
    """R20: the Seljuk player places a Siege or Bypass marker during Levy."""
    pending = next((p for p in gs.meta.pending
                    if p["type"] == "besiege_or_bypass" and p.get("source") == "R20"), None)
    if pending is None:
        raise IllegalAction("no_pending", "no Armenian Resistance Siege/Bypass to resolve")
    if action.get("side") not in (None, "seljuk"):
        raise IllegalAction("wrong_actor", "the Seljuk player chooses Siege or Bypass (R20)")
    choice = action.get("choice")
    if choice not in ("besiege", "bypass"):
        raise IllegalAction("bad_choice", "choose 'besiege' or 'bypass' (R20)")
    if {"surprise", "storm_decisions"} & action.keys():
        raise IllegalAction("bad_choice", "R20 places one Siege or Bypass marker during Levy")
    locale = pending["locale"]
    st = gs.locales[locale]
    st.siege_markers = int(choice == "besiege")
    st.bypass = choice == "bypass"
    for lord in gs.lords.values():
        if lord.mustered and lord.cylinder == locale:
            lord.bypassed = st.bypass and lord.side == "seljuk"
            lord.besieged = choice == "besiege" and lord.side == "roman"
    gs.meta.pending.remove(pending)
    return {"ok": True, "action": choice, "locale": locale, "source": "R20"}


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


THEMATIC_DESERT_ARGS = ("source", "thema", "locale", "lord", "marker_index", "unit", "symbols")


def thematic_desert_targets(gs: GameState) -> list[dict[str, Any]]:
    """S15 counter references in Alp Arslan's Thema and at his Locale."""
    from .actions import _on_map, is_commander

    alp = gs.lords["alp_arslan"]
    if not _on_map(alp):
        return []
    locale = alp.cylinder
    thema = sd.locale(locale)["thema"]
    if thema is None:
        return []

    piles = [
        ("unlevied", gs.themata.get(thema, []), {}),
        ("defending", gs.locales[locale].themata_defending, {"locale": locale}),
    ]
    piles.extend(
        ("levied", lord.themata_on_mat, {"locale": locale, "lord": lid})
        for lid, lord in gs.lords.items()
        if lord.mustered and lord.cylinder == locale and lord.side == "roman"
        and is_commander(gs, lid)
    )
    return [
        {"source": source, "thema": thema, **location, "marker_index": index,
         "unit": marker.unit, "symbols": marker.symbols}
        for source, pile, location in piles
        for index, marker in enumerate(pile)
    ]


def _ev_thematic_desert(gs, args, roller):       # S15
    from . import actions, campaign

    selection = {field: value for field, value in args.items() if field != "_interactive_wastage"}
    if selection.keys() - set(THEMATIC_DESERT_ARGS) or any(
        type(selection[field]) is not int for field in ("marker_index", "symbols") if field in selection
    ):
        raise IllegalAction("bad_themata_selection", "S15 requires a valid Themata counter reference")
    targets = thematic_desert_targets(gs)
    if not targets and not selection:
        return {"no_op": True, "reason": "no eligible Levied or Unlevied Themata (S15)"}
    matches = [
        target for target in targets
        if all(field in target and target[field] == value for field, value in selection.items())
    ]
    if not matches:
        raise IllegalAction("bad_themata_selection", "S15 selection matches no eligible Themata counter")
    if len(matches) > 1:
        raise IllegalAction("themata_selection_required", "S15 requires a choice of one eligible Themata counter")
    target = matches[0]
    source, thema, index = target["source"], target["thema"], target["marker_index"]
    lord = None
    if source == "unlevied":
        pile = gs.themata[thema]
    elif source == "defending":
        pile = gs.locales[target["locale"]].themata_defending
    else:
        lord = gs.lords[target["lord"]]
        pile = lord.themata_on_mat

    _record_removed_themata(gs, pile.pop(index), thema)
    result = {"removed": target}
    if lord is not None:
        disband = actions.disband_if_empty(gs, lord)
        if disband is not None:
            campaign._refresh_invest(gs, target["locale"])
            result["disband"] = disband
    return result


def siege_of_bari_targets(gs: GameState) -> tuple[dict[tuple[str, int], ThemataMarker], int]:
    """Unlevied counters by Thema and box index, and the required removal count."""
    targets = {(thema, index): marker for thema, box in gs.themata.items()
               for index, marker in enumerate(box)}
    return targets, min(2, len(targets))


def _ev_siege_of_bari(gs, args, roller):         # S5*
    """Remove two available Unlevied Themata, or all that remain if fewer."""
    if "S5" in gs.meta.asterisks_used:
        # Already marked: instead, 1 Seljuk Lord gains +1 Lordship this Muster.
        lid = args.get("lord")
        l = gs.lords.get(lid)
        if l is None or l.side != "seljuk":
            return {"already_marked": True, "no_op": True,
                    "reason": "need a Seljuk Lord for the +1 Lordship effect"}
        l.flags["lordship_persist"] = int(l.flags.get("lordship_persist", 0)) + 1
        return {"already_marked": True, "lordship_bonus": lid}
    targets, required = siege_of_bari_targets(gs)
    explicit = "markers" in args
    if explicit and ("themata" in args or "unit" in args):
        raise IllegalAction("bad_themata_selection", "Choose markers or the legacy themata/unit fields")
    choices = args.get("markers", args.get("themata", []))
    if not isinstance(choices, list) or len(choices) != required:
        raise IllegalAction("bad_themata_count", f"S5 requires exactly {required} Unlevied Themata")

    unit = args.get("unit")
    selected = {}
    for choice in choices:
        if explicit:
            if (not isinstance(choice, dict) or not isinstance(choice.get("thema"), str)
                    or type(choice.get("marker_index")) is not int):
                raise IllegalAction("bad_themata_selection", "Use {thema, marker_index} for each marker")
            key = (choice["thema"], choice["marker_index"])
            marker = targets.get(key)
            if marker and any(choice.get(field, getattr(marker, field)) != getattr(marker, field)
                              for field in ("unit", "symbols")):
                raise IllegalAction("bad_themata_selection", "Selected marker does not match unit or symbols")
        else:
            key = next((ref for ref, marker in targets.items()
                        if ref[0] == choice and ref not in selected
                        and (unit is None or marker.unit == unit)), None)
        if key is None or key not in targets or key in selected:
            raise IllegalAction("bad_themata_selection", "Choose distinct Unlevied Themata markers")
        selected[key] = targets[key]

    # Box indices refer to the original position. Remove high indices first,
    # then record the counters in the order the player selected them.
    for thema, index in sorted(selected, key=lambda key: key[1], reverse=True):
        gs.themata[thema].pop(index)
    removed = []
    for (thema, _), marker in selected.items():
        _record_removed_themata(gs, marker, thema)
        removed.append({"thema": thema, "unit": marker.unit, "symbols": marker.symbols})
    gs.meta.asterisks_used.append("S5")
    return {"removed": removed}


def merchant_financing_targets(gs: GameState) -> dict[str, dict[str, int]]:
    """S8 eligible Lords and the maximum amount by destination Asset."""
    from .actions import _on_map

    return {
        lid: {"coin": lord.assets.carts, "carts": lord.assets.coin}
        for lid, lord in gs.lords.items() if lord.side == "seljuk" and _on_map(lord)
    }


def _ev_merchant_financing(gs, args, roller):    # S8
    if not (args.keys() - {"_interactive_wastage"}):
        return {"exchanged": 0}
    lid = args.get("lord")
    if not isinstance(lid, str) or lid not in gs.lords:
        raise IllegalAction("bad_lord", f"no such Lord {lid!r}")
    targets = merchant_financing_targets(gs)
    if lid not in targets:
        raise IllegalAction("bad_event_target", "S8 requires a Mustered Seljuk Lord on the map")

    destination = args.get("to")
    if destination not in ("coin", "carts"):
        raise IllegalAction("bad_direction", "S8 exchanges to coin or carts")
    amount = args.get("amount", 0)
    maximum = targets[lid][destination]
    if type(amount) is not int or not 0 <= amount <= maximum:
        raise IllegalAction("bad_amount", f"S8 amount must be an integer from 0 to {maximum}")

    assets = gs.lords[lid].assets
    source = "carts" if destination == "coin" else "coin"
    setattr(assets, source, getattr(assets, source) - amount)
    # 1.7.3: any of the received Asset above eight is immediately lost.
    setattr(assets, destination, min(8, getattr(assets, destination) + amount))
    return {"exchanged": amount, "to": destination}


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


def resolve_event(gs: GameState, card_id: str, args: dict | None, roller: DiceRoller) -> dict[str, Any]:
    pend = next((p for p in gs.meta.pending
                 if p["type"] == "event_pending_resolution" and p["card"] == card_id), None)
    if pend is None:
        raise IllegalAction("no_pending_event", f"no pending Event {card_id}")
    if card_id not in _RESOLVERS:
        # Tracked-but-not-yet-implemented Event: discard with no mechanical effect.
        gs.meta.pending.remove(pend)
        return {"ok": True, "card": card_id, "no_op": True, "reason": "resolver not yet implemented (Phase 4 remainder)"}
    try:
        arguments = {} if args is None else args
        result = _RESOLVERS[card_id](gs, {**arguments, "_interactive_wastage": True}, roller)
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

def _turkic_sources(gs, locale, include_themata):
    """Map target identities to their available quantities before the Events."""
    sources = {}
    for lord in gs.lords.values():
        if not lord.mustered or lord.cylinder != locale:
            continue
        if count := lord.forces.get("turkic_horse", 0):
            sources[lord.id, None, "unit"] = count
        for index, marker in enumerate(lord.themata_on_mat):
            if marker.unit != "turkic_horse":
                continue
            if marker.unrouted_count() > 0:
                sources[lord.id, index, "unit"] = marker.unrouted_count()
            if include_themata:
                sources[lord.id, index, "marker"] = 1
    if include_themata:
        for index, marker in enumerate(gs.locales[locale].themata_defending):
            if marker.unit == "turkic_horse":
                sources[None, index, "marker"] = 1
    return sources


def _plan_turkic_removal(gs, locale, args, include_themata=False, *, owner=None):
    if not isinstance(locale, str) or locale not in gs.locales:
        raise IllegalAction("bad_turkic_target", "Choose the combat Locale for Turkic Horse removal.")
    sources = _turkic_sources(gs, locale, include_themata)
    count = args.get("count", 2)
    if type(count) is not int or not 0 <= count <= 2:
        raise IllegalAction("bad_turkic_count", "Remove zero, one, or two Turkic Horse targets.")

    if "targets" not in args:
        # Older calls specified a count. Infer targets only when the selection
        # is forced. For S21 the old indexed target was a whole marker.
        if include_themata:
            sources = {key: n for key, n in sources.items() if key[1] is None or key[2] == "marker"}
        count = min(count, sum(sources.values()))
        if count == 0:
            return {}
        if any(lid is not None and gs.lords[lid].side == owner for lid, _, _ in sources):
            raise IllegalAction("turkic_targets_required", "Name the targets when friendly Turkic Horse are present.")
        if len(sources) == 1:
            return {next(iter(sources)): count}
        if count == sum(sources.values()):
            return sources
        raise IllegalAction("turkic_targets_required", "Choose the Turkic Horse targets explicitly.")

    targets = args["targets"]
    if not isinstance(targets, list):
        raise IllegalAction("bad_turkic_target", "Supply a list of Turkic Horse targets.")
    selected = {}
    for target in targets:
        if not isinstance(target, dict) or target.keys() - {"lord", "index", "kind", "count"}:
            raise IllegalAction("bad_turkic_target", "Specify a Lord and/or Themata index for each target.")
        lord, index = target.get("lord"), target.get("index")
        kind = target.get("kind", "marker" if include_themata and index is not None else "unit")
        quantity = target.get("count", 1)
        if ((lord is not None and not isinstance(lord, str))
                or (index is not None and type(index) is not int)
                or kind not in ("unit", "marker")
                or type(quantity) is not int or quantity < 1):
            raise IllegalAction("bad_turkic_target", "Invalid Turkic Horse target.")
        key = (lord, index, kind)
        if key in selected or quantity > sources.get(key, 0):
            raise IllegalAction("bad_turkic_target", "Select distinct eligible targets with available units.")
        selected[key] = quantity
    total = sum(selected.values())
    if total > 2 or ("count" in args and total != count):
        raise IllegalAction("bad_turkic_count", "The selected quantities must agree with the removal count of up to two.")
    return selected


def _apply_turkic_removal(gs, locale, selections):
    """Resolve all declarations against their original marker indices."""
    sources = _turkic_sources(gs, locale, include_themata=True)
    used = {}
    for selection in selections:
        for (lid, index, kind), count in selection.items():
            old_kind, old_count = used.get((lid, index), (kind, 0))
            if kind != old_kind or count + old_count > sources[lid, index, kind]:
                raise IllegalAction("bad_turkic_target", "The Events overlap on the same Turkic Horse target.")
            used[lid, index] = (kind, count + old_count)

    # Remove higher indices first so removing a marker never retargets a
    # second declaration. Ordinary forces have no index.
    for (lid, index), (kind, count) in sorted(
            used.items(), key=lambda item: -1 if item[0][1] is None else item[0][1], reverse=True):
        if index is None:
            forces = gs.lords[lid].forces
            forces["turkic_horse"] -= count
            if not forces["turkic_horse"]:
                del forces["turkic_horse"]
            continue
        markers = gs.lords[lid].themata_on_mat if lid is not None else gs.locales[locale].themata_defending
        marker = markers[index]
        if kind == "unit":
            marker.strength = marker.unit_count() - count
        if kind == "marker" or marker.unit_count() == 0:
            markers.pop(index)
            _record_removed_themata(gs, marker, sd.locale(locale)["thema"])
    return {lid for lid, _ in used if lid is not None}


def _remove_turkic_at(gs, locale, count, include_themata=False):
    """Compatibility entry point for an unambiguous count-only removal."""
    selection = _plan_turkic_removal(gs, locale, {"count": count}, include_themata)
    _apply_turkic_removal(gs, locale, [selection])
    return sum(selection.values())


def _disband_turkic_targets(gs, lords):
    from .actions import disband_if_empty

    return [lid for lid in sorted(lords) if disband_if_empty(gs, gs.lords[lid])]


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
    if not aa.mustered or aa.besieged or gs.locales[aa.cylinder].siege_markers <= 1:
        raise IllegalAction("not_applicable", "Alp Arslan must be Besieging at a Locale with >1 Siege marker (R4)")
    gs.locales[aa.cylinder].siege_markers -= 1
    return {"removed_siege_at": aa.cylinder}


def _hold_turkic_removal(gs, args, include_themata):
    loc = args["locale"]
    active = gs.lords.get(gs.meta.active_lord)
    if active is not None and active.cylinder != loc:
        raise IllegalAction("bad_turkic_target", "Choose the Active Lord's Locale.")
    owner = "seljuk" if include_themata else "roman"
    selection = _plan_turkic_removal(gs, loc, args, include_themata, owner=owner)
    affected = _apply_turkic_removal(gs, loc, [selection])
    return {"turkic_removed": sum(selection.values()), "disbanded": _disband_turkic_targets(gs, affected)}


def _hold_nomadic_tribes(gs, args, roller):         # R21 (remove up to 2 Turkic Horse units)
    return _hold_turkic_removal(gs, args, include_themata=False)


def _hold_common_cultural(gs, args, roller):        # S21 (remove up to 2 Turkic Horse markers/units)
    return _hold_turkic_removal(gs, args, include_themata=True)


def _hold_bad_omens(gs, args, roller):              # S24 (inspect top 2 unrevealed Roman Plan cards)
    """Inspect the top 2 Roman Plan cards and replace them in EITHER order (card
    text). The Seljuk player may keep the order (args order="keep") or swap them
    (default)."""
    pp = gs.roman.plan_pointer
    plan = gs.roman.command_plan
    if len(plan) - pp < 2:
        return {"no_op": True, "reason": "fewer than 2 unrevealed Roman cards"}
    if args.get("order") == "keep":
        return {"kept": plan[pp:pp + 2]}
    plan[pp], plan[pp + 1] = plan[pp + 1], plan[pp]
    return {"reordered": plan[pp:pp + 2]}


def _hold_summer_heat(gs, args, roller):            # R3/S4 (enemy Command 1 after reveal)
    from . import campaign
    if gs.meta.subphase != "campaign.command" or gs.meta.active_lord is None:
        raise IllegalAction("wrong_timing", "play after the enemy reveals a Command card (R3/S4)")
    if campaign.season_index(gs.meta.calendar_box) != 1:
        raise IllegalAction("not_summer", "Summer Heat is played in Summer (R3/S4)")
    gs.meta.actions_remaining = min(gs.meta.actions_remaining, 1)  # that Lord is Command 1
    # This modifies the fresh card's rating; it does not spend an action.
    gs.meta.notes["card_full_actions"] = gs.meta.actions_remaining
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
    if card_id in {"R3", "S4"}:
        # Summer Heat is an enemy-reveal reaction, not a way to reset a partly
        # spent card to a fresh Command-1 budget. Validate before consuming it.
        window = next((p for p in gs.meta.pending
                       if p.get("type") == "summer_heat" and p.get("card") == card_id
                       and p.get("reactor") == side), None)
        if (window is None or side == gs.meta.active_player
                or gs.meta.active_lord is None
                or gs.meta.actions_remaining != gs.meta.notes.get("card_full_actions")):
            raise IllegalAction("wrong_timing",
                                "Summer Heat must be played in its enemy Command reveal window (R3/S4)")
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
# Out-of-turn / special-window reactions are NOT in this active-side Hold-Event
# menu, but each IS reachable from the palette through its own decision window:
#   R3/S4 Summer Heat   - a "summer_heat" pending after the enemy reveals a
#                         Command card in Summer; legal_moves offers play/decline.
#   R23 Kleisourai      - a "kleisourai" pending when a Seljuk Lord crosses a
#                         Pass; legal_moves offers play/decline.
#   R21/S21 Turkic rmv  - hinted as _battle_holds_available (approach_response)
#                         and _storm_events_available (cmd_storm); passed via
#                         battle_events / storm_decisions.
#   R14 Imperial Coffers- an "imperial_coffers" pending in the Levy discard
#                         window; legal_moves offers discard/decline.
# They are deliberately kept out of THIS menu (their windows are elsewhere); the
# negative enumerator tests assert they never appear in the normal command menu.

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
            # "Play where Alp Arslan BESIEGING Stronghold with >1 Siege marker"
            # -- Alp must be the (unbesieged) besieger, not himself under Siege.
            aa = gs.lords["alp_arslan"]
            if aa.mustered and not aa.besieged and gs.locales[aa.cylinder].siege_markers > 1:
                out.append({"type": "play_hold_event", "card": "R4",
                            "_desc": f"Hold Event R4 Sultan's Horse: remove 1 Siege at {aa.cylinder}"})
    return out
