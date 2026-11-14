"""Decision help derived from the engine, with no choice made for the player."""
from __future__ import annotations

import ast
import inspect
import textwrap
from copy import deepcopy
from functools import lru_cache

from .. import battle, campaign, engine, events, map as gmap, static_data as sd
from ..state import IllegalAction
from .routing import current_pending, other

HIT_DECISION_HELP = {
    "hit_absorption": 'The receiving player can use ["hit_absorption", "unit_id"] '
                      'for a Lord or Storm Garrison. Garrison units must absorb before Lords.',
    "protection_type": 'Against an Armor penalty in field Melee, the Turkic Horse owner '
                       'can choose ["protection_type", "evade"] or '
                       '["protection_type", "armor"] while Lamellar Armor is active. '
                       'Evade is unavailable against Missiles and in Storm.',
    "select_target_unit": 'The striking player can use ["select_target_unit", "unit_id"] '
                          'for Parthian Shot in Battle or Garrison Missiles in Storm.',
    "norman_reroll": 'The Norman owner can use ["norman_reroll", false] after a failed '
                    'Armor roll to save the reroll for a later Hit. R5 allows one Missile and '
                    'one Melee reroll per Lord per Round.',
}

FIELD_DECISION_HELP = {
    "strike_order": 'Use ["strike_order", "target_lord_id"] to choose the next '
                    'Lord or combined Flanking group within your Strike step.',
    "reserve_advance": 'From Round 2, use ["reserve_advance", "lord_id"] to advance '
                       'a Reserve Lord, then optionally ["reserve_advance_slot", "right"] '
                       'to select an open Front slot. Use ["reserve_advance", null] '
                       'to finish advancing for that Round. Center still fills from a wing.',
    "retreat": 'Use ["retreat", "withdraw"], ["retreat", ["retreat", "locale_id"]], '
               'or ["retreat", "removed"] for the next losing Lord. A pair that '
               'stays in play must Withdraw together or Retreat to the same Locale.',
}


@lru_cache(maxsize=None)
def parameter_names(fn, argument="action") -> list[str]:
    """Discover direct keys and keys in helpers receiving the same input object.

    Public installed source only; no evaluation of expressions or game state.
    Hand-written shape/constraint help below complements these exact key names.
    """
    return sorted(_parameter_names(fn, argument, set()))


def _parameter_names(fn, argument, visited):
    pair = (fn, argument)
    if pair in visited:
        return set()
    visited.add(pair)
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError):
        return set()
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == argument
                and node.func.attr == "get" and node.args and isinstance(node.args[0], ast.Constant)):
            found.add(node.args[0].value)
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == argument and isinstance(node.slice, ast.Constant)):
            found.add(node.slice.value)
        if not isinstance(node, ast.Call):
            continue
        target = None
        if isinstance(node.func, ast.Name):
            target = fn.__globals__.get(node.func.id)
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            obj = fn.__globals__.get(node.func.value.id)
            if inspect.ismodule(obj):
                target = getattr(obj, node.func.attr, None)
        if not inspect.isfunction(target) or not target.__module__.startswith("seljuk."):
            continue
        names = list(inspect.signature(target).parameters)
        for index, value in enumerate(node.args):
            if isinstance(value, ast.Name) and value.id == argument and index < len(names):
                found |= _parameter_names(target, names[index], visited)
        for keyword in node.keywords:
            if isinstance(keyword.value, ast.Name) and keyword.value.id == argument and keyword.arg:
                found |= _parameter_names(target, keyword.arg, visited)
    return {k for k in found if isinstance(k, str)}


def visible_move(gs, move, side):
    """Project a complete internal row without disclosing the opponent's hand.

    Normalized fields/descriptions do not leak a secret through key presence.
    Every base action remains; joint inputs are collected from their owner.
    """
    out = deepcopy(move)
    kind = move["type"]
    if kind in ("respond_approach", "cmd_storm", "cmd_sally"):
        att = (gs.lords[current_pending(gs)["attackers"][0]].side
               if kind == "respond_approach" else gs.lords[move["lord"]].side)
        own_role = "attacker" if side == att else "defender"
        allowed = {"R21", "S21"} if kind == "cmd_storm" else battle._BATTLE_HOLDS
        own = battle.held_combat_events(gs, side, allowed)
        for key in ("_battle_holds_available", "_storm_events_available", "_r4_sultans_horse_available"):
            out.pop(key, None)
        out["_combat_inputs"] = {"your_role": own_role, "your_held_events": own,
                                 "opponent": "Private input collected before resolution, including a decline."}
        out["_desc"] = {
            "cmd_storm": "Storm the Stronghold (4.5.2)",
            "cmd_sally": "Sally against the Besiegers (4.5.3)",
            "respond_approach": "Each defending Lord chooses Avoid, Withdraw, or Stand (4.3.4)",
        }[kind]
        if side == "roman" and kind == "cmd_storm":
            out["_your_sultans_horse_held"] = "R4" in gs.roman.held_events
    if kind in ("resolve_loyalty", "discard_imperial_coffers") and gs.meta.options.get("hidden_mats"):
        out["_max_coins_against"] = "Opponent supplies privately"
        out["_desc"] = "Loyalty Check (1.4.1): your payment, then the opponent's counterpayment."
    return out


def siege_formation_help(gs, move, side):
    kind = move.get("type")
    if kind not in ("cmd_storm", "cmd_sally"):
        return {}
    lord = gs.lords[move["lord"]]
    storm = kind == "cmd_storm"
    inside = other(lord.side) if storm else lord.side
    return {"formation": {
        "your_role": "attacker" if lord.side == side else "defender",
        "your_lords": [ld.id for ld in gs.lords.values() if ld.side == side and ld.mustered
                       and ld.cylinder == lord.cylinder and ld.besieged == (side == inside)],
        "script": "storm_decisions" if storm else "battle_decisions",
        "initial_placement_defender": 'The Defender can choose the initial Front with '
                                      '["initial_placement_defender", "lord_id"].',
        "reserve_advance": 'From Round 2, use ["reserve_advance", "lord_id"] to advance one '
                           'Lord within Stronghold Size. Use ["reserve_advance", null] to '
                           'decline when optional.',
        "mandatory_advance": ("Fill an empty Front or match an open opposing Front position."
                              if storm else "Replace a wholly Routed Front when Reserve remains."),
    }}


def combat_event_help(gs, move, side, held):
    out = {}
    if "S3" in held:
        out["betrayal"] = ('Use {"card":"S3","lord":"lord_id"} in your battle_events. '
                           'After Reposition, at least two Roman Lords must remain in combat '
                           'and the selected Lord must be a non-Commander in the Front. '
                           'S3 stays Held until it moves the selected Lord to Reserve.')
    cards = sorted(set(held) & battle._TURKIC_REMOVAL_HOLDS)
    if not cards:
        return out
    avoiding = set()
    if move["type"] == "respond_approach":
        pending = current_pending(gs)
        locale = pending["locale"]
        choices, _ = campaign._approach_choices(gs, pending, move)
        avoiding = {lid for lid, choice in choices.items() if choice.get("action") == "avoid"}
    else:
        locale = gs.lords[move["lord"]].cylinder
    screened = {lid for lid, lord in gs.lords.items()
                if gs.meta.options.get("hidden_mats") and lord.mustered and lord.cylinder == locale
                and lord.side != side and lid not in gs._revealed_combat_lords and lid not in avoiding}
    options = {}
    for card in cards:
        options[card] = [
            {"lord": lid, "index": index, "kind": kind, "available": available}
            for (lid, index, kind), available in events._turkic_sources(gs, locale, card == "S21").items()
            if lid not in screened and lid not in avoiding
        ]
    out["turkic_removal"] = {
        "visible_targets": options,
        "screened_lords": sorted(screened),
        "input": "Use {card, targets: [{lord, index, kind, count}]}. Omit index for ordinary units, "
                 "omit lord for a defending Themata marker. Count defaults to 1. Select up to two. "
                 "You may nominate a screened Lord at this Locale.",
    }
    return out


def contract(gs, move, side):
    kind = move["type"]
    fn = engine._handlers_for_phase(gs.meta.phase).get(kind)
    keys = parameter_names(fn) if fn else []
    fixed = {k for k in move if not k.startswith("_")}
    out = {"parameters": [k for k in keys if k not in fixed], "all_action_fields": keys,
           "validation": "Engine validates the submitted combination; no parameters are chosen here."}
    if fn and inspect.getdoc(fn):
        out["handler_help"] = inspect.getdoc(fn)
    if kind in ("reset_discard", "reset_done"):
        out.update(parameters=[], all_action_fields=sorted(fixed),
                   eligible_cards=campaign.reset_discard_candidates(gs, side),
                   notes=["Discard any subset of your Held Events and deployed Capabilities, one card at a time.",
                          "reset_done keeps every remaining card; Seljuk finishes before Roman.",
                          "Mandatory cleanup and Themata retention already happened and do not repeat.",
                          "A Special-Vassal card also removes its contingent; losing the last Force Disbands its Lord."])
    elif kind == "grow":
        out.update(remaining=current_pending(gs)["remaining"],
                   enemy_marker_side=other(side),
                   eligible_locales=[move["locale"] for move in campaign.grow_moves(gs)],
                   notes=["Remove one enemy Ravaged marker per action, Seljuk first, then Roman.",
                          "The fixed quota leaves half the original markers, rounded up.",
                          "Repair, Wastage and Reset wait until both owners finish."])
    elif kind == "capability_discard":
        out.update(remaining=campaign.capability_excess(gs, side),
                   eligible_cards=list(gs.side_decks(side).capabilities_in_play),
                   notes=["Select one board-edge Capability, repeating until at the Mustered-Lord limit.",
                          "This Lord Capabilities and Held Events do not count or qualify.",
                          "Seljuk completes its choices before Roman; Planning waits for both."])
    elif kind == "build_plan":
        out.update(required={"cards": "Ordered array of Lord ids, no_command, or treachery"},
                   constraints=campaign.plan_constraints(gs, side),
                   on_map_lords=list(move["_available_lords"]),
                   lieutenant_options=deepcopy(move.get("_lieutenant_options", [])),
                   notes=["No automatic Plan construction. Supply every card in play order.",
                          "Off-map/Lower-Lord Command cards are legal but reveal as Pass (4.2.3).",
                          "Optional lieutenants must be eligible, disjoint pairs (4.1.3)."])
    elif kind in ("resolve_event", "play_hold_event"):
        resolvers = events._RESOLVERS if kind == "resolve_event" else events._HOLD_RESOLVERS
        fn = resolvers.get(move["card"])
        out.update(required={"args": "Object; choose arguments using the full card mechanics"},
                   argument_names=parameter_names(fn, "args") if fn else [],
                   card_lookup=move["card"],
                   notes=["Supply args explicitly ({} for no-choice/no-target effects).",
                          "lookup_card includes the complete curated clarification, not just the short data text."])
        if kind == "resolve_event" and move["card"] == "R16":
            targets = events.anglo_saxon_targets(gs)
            out.update(argument_names=["lord"], eligible_lords=targets,
                       required_count=int(bool(targets)))
            out["notes"].append("Choose one listed Roman Lord to receive a Varangian Guard. "
                                "Supply {} if the list is empty.")
        elif kind == "resolve_event" and move["card"] in ("R1", "R10"):
            if move["card"] in gs.meta.asterisks_used:
                targets = events.muster_penalty_targets(gs)
                out.update(argument_names=["lord"], eligible_lords=targets,
                           required_count=int(bool(targets)))
                out["notes"].append("Choose a listed Seljuk Lord to lose 1 Lordship this Muster. "
                                    "Lords able to Muster take priority. Supply {} if the list is empty.")
            else:
                out.update(argument_names=[])
        elif kind == "resolve_event" and move["card"] in ("R5", "S12", "S23"):
            out.update(eligible_markers=events.calendar_event_targets(gs, move["card"]),
                       directions=["left", "right"])
            out["notes"].append("Choose a Lord and one of its listed marker types. "
                                "Supply {} if there is no eligible marker.")
        elif kind == "resolve_event" and move["card"] == "R19":
            targets = events.resilient_agriculture_targets(gs)
            out.update(eligible_locales=targets, required_count=min(2, len(targets)))
            out["notes"].append("Supply args.locales with exactly the required number of "
                                "distinct eligible Locale IDs. Supply {} if none are eligible.")
        elif kind == "resolve_event" and move["card"] == "R20":
            out.update(argument_names=["locale"], eligible_locales=events.armenian_resistance_targets(gs))
            out["notes"].append("Choose a Locale, or supply {} if none are eligible. "
                                "If a Seljuk Lord is present, the Seljuk player chooses Siege or Bypass.")
        elif kind == "resolve_event" and move["card"] == "S5":
            if "S5" in gs.meta.asterisks_used:
                out.update(argument_names=["lord"],
                           eligible_lords=[lid for lid, lord in gs.lords.items()
                                           if lord.side == "seljuk"])
                out["notes"].append("Choose a Seljuk Lord to gain +1 Lordship this Muster.")
            else:
                targets, required = events.siege_of_bari_targets(gs)
                out.update(argument_names=["markers"], required_count=required,
                           eligible_markers=[
                               {"thema": thema, "marker_index": index,
                                "unit": marker.unit, "symbols": marker.symbols}
                               for (thema, index), marker in targets.items()
                           ])
                out["notes"].append("Supply args.markers with exactly the required count of distinct "
                                    "{thema, marker_index} pairs. Unit and symbols identify each counter.")
        elif kind == "resolve_event" and move["card"] == "S8":
            targets = events.merchant_financing_targets(gs)
            out.update(argument_names=["lord", "to", "amount"], eligible_lords=list(targets),
                       max_amount_by_lord_and_destination=targets)
            out["notes"].append("Choose one Lord and a destination Asset (coin or carts). "
                                "Use amount 0 or {} to decline. Any received Asset above eight is lost.")
        elif kind == "resolve_event" and move["card"] == "R13":
            out.update(argument_names=["marker_index"],
                       eligible_markers=[
                           {"marker_index": index, "thema": marker.home_thema,
                            "unit": marker.unit, "symbols": marker.symbols}
                           for index, marker in enumerate(gs.meta.themata_removed)
                       ])
            out["notes"].append("Choose one removed counter by args.marker_index. "
                                "Supply {} if the removed pile is empty.")
        elif kind == "resolve_event" and move["card"] == "S15":
            targets = events.thematic_desert_targets(gs)
            out.update(argument_names=list(events.THEMATIC_DESERT_ARGS),
                       eligible_markers=targets, required_count=int(bool(targets)))
            out["notes"].append("Copy one eligible marker reference into args. "
                                "Use {} when there are no eligible markers or only one.")
        if move["card"] == "S24":
            out["notes"] += ["Select S24 without order to declare play and inspect privately, then choose keep/swap. Once inspected, no cancellation is permitted."]
    elif kind == "pay":
        out.update(max_amount=move["_max"], parameters=["amount"] if move["_max"] > 1 else [],
                   notes=["For bulk Pay, submit this action with the desired amount and current version. "
                          "Each unit must advance the Lord's or an affected Vassal's Service."])
    elif kind == "besiege_bypass" and gs.meta.phase == "levy":
        out.update(parameters=[], all_action_fields=sorted(fixed),
                   notes=["R20 places the selected marker at this Stronghold. Levy then resumes."])
    elif kind == "assign_themata_defenders":
        loc = current_pending(gs)["locale"]
        home = sd.locale(loc)["thema"]
        out.update(required={"markers": "Array of selected reserve indices; [] explicitly declines"},
                   max_markers=campaign._stronghold_size(gs, loc), locale=loc, thema=home,
                   available=[{"index": i, **m.model_dump()} for i, m in enumerate(gs.themata[home])])
    elif kind == "respond_approach":
        out["parameters"] = [key for key in out["parameters"]
                             if key not in ("sally_join", "avoid_spoils_decisions")]
        pending = current_pending(gs)
        loc = pending["locale"]
        defenders = pending["defenders"]
        pairs = gs.lieutenant_pairs(defenders)
        paired = {lid for pair in pairs for lid in pair}
        inside = sum(l.mustered and l.cylinder == loc and l.besieged and l.side == side
                     for l in gs.lords.values())
        choices = {}
        for lid in defenders:
            options = [{"action": "stand"}]
            try:
                campaign._validate_withdraw(gs, gs.lords[lid], loc)
            except IllegalAction:
                pass
            else:
                slots_needed = 2 if lid in paired else 1
                if campaign._stronghold_size(gs, loc) - inside >= slots_needed:
                    options.append({"action": "withdraw"})
            for dest in gmap.neighbors(loc):
                try:
                    campaign._validate_avoid(gs, gs.lords[lid], loc, dest, side, pending.get("from"))
                except IllegalAction:
                    continue
                options.append({"action": "avoid", "to": dest})
            choices[lid] = options
        out.update(required={"choices": "Object mapping each defender id to an explicit choice"},
                   choices=choices, max_total_withdrawals=max(0, campaign._stronghold_size(gs, loc)-inside),
                   notes=["Withdrawal capacity is shared, not a separate allowance per Lord.",
                          "Lords Avoiding to the same destination share Carts. Optionally use avoid_keep_provender to specify how much food each keeps on its own mat. Defaults use own Carts first. Loot and excess Provender become Spoils.",
                          "The opponent controls Local Scouts, Avoid Spoils, Relief Sally, and its own combat inputs."])
        if pairs:
            out["lieutenant_pairs"] = pairs
            out["notes"].append("Each Lieutenant pair must choose the same response and Avoid destination.")
    elif kind == "cmd_march":
        out["notes"] = ["Optional group uses _co_marchers / _co_marcher_max; the engine recomputes group cost.",
                        "Discard variants remain distinct menu rows; no variant is silently selected.",
                        "Group Carts can change cost. For combinations not represented by a default row, submit a flat action with version=; the engine validates it."]
    elif kind == "cmd_sortie":
        out["notes"] = ["Optional group selects the Commander's allies from _co_marchers.",
                        "A Lieutenant brings his Lower Lord automatically.",
                        "Sortie spends one action and hands off to the enemy's Approach response.",
                        "Supply any combat inputs with respond_approach."]
    if kind in ("respond_approach", "cmd_storm", "cmd_sally"):
        out["combat"] = {
            "battle_events": "Each side supplies its own cards. Use {card, lord} for S3/S6/R24 "
                             "and {card, targets} for R21/S21.",
            "rounds": "steeled_rounds / javelins_rounds: {your_lord: round}; existing default is 1.",
            "decisions": "battle_decisions / storm_decisions: your typed FIFO arrays, e.g. [[concede, true]], scoped to your decisions.",
            "retreat": "Use [retreat, removed] for voluntary removal when losing. For a conceding group Retreat, use [retreat_keep_provender, COUNT] at each contested mat in resolution order.",
            "spoils": "Winning owner chooses spoils_recipient (Lord ID), then spoils_amount (positive marker count); repeat to split Assets. Defaults fill the first eligible mat then allies; each Asset type is capped at 8 per Lord.",
            "resolution": "Engine combat is atomic. Preserve scripted choices; unscripted choices use its existing fallback.",
            "opponent_input": "An explicit input/decline handoff occurs before dice. No opponent hand is disclosed.",
            **HIT_DECISION_HELP,
            **siege_formation_help(gs, move, side),
            **combat_event_help(gs, move, side, move.get("_combat_inputs", {}).get("your_held_events", [])),
        }
        if kind == "respond_approach":
            out["combat"].update(FIELD_DECISION_HELP)
    out["references"] = ["guide", "rules", "decisions", "errata"]
    return out
