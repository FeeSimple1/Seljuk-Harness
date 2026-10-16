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
    if kind in ("respond_approach", "cmd_storm", "cmd_sally", "cmd_sortie"):
        att = (gs.lords[current_pending(gs)["attackers"][0]].side
               if kind == "respond_approach" else gs.lords[move["lord"]].side)
        own_role = "attacker" if side == att else "defender"
        allowed = {"R21", "S21"} if kind == "cmd_storm" else battle._BATTLE_HOLDS
        own = sorted(set(gs.side_decks(side).held_events) & allowed)
        for key in ("_battle_holds_available", "_storm_events_available", "_r4_sultans_horse_available"):
            out.pop(key, None)
        out["_combat_inputs"] = {"your_role": own_role, "your_held_events": own,
                                 "opponent": "Private input collected before resolution, including a decline."}
        out["_desc"] = {
            "cmd_storm": "Storm the Stronghold (4.5.2)",
            "cmd_sally": "Sally against the Besiegers (4.5.3)",
            "cmd_sortie": "Sortie against the Bypassing Enemy (4.3.6)",
            "respond_approach": "Each defending Lord chooses Avoid, Withdraw, or Stand (4.3.4)",
        }[kind]
        if side == "roman" and kind == "cmd_storm":
            out["_your_sultans_horse_held"] = "R4" in gs.roman.held_events
    if kind in ("resolve_loyalty", "discard_imperial_coffers") and gs.meta.options.get("hidden_mats"):
        out["_max_coins_against"] = "Opponent supplies privately"
        out["_desc"] = "Loyalty Check (1.4.1): your payment, then the opponent's counterpayment."
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
    if kind == "build_plan":
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
        if move["card"] == "S24":
            out["notes"] += ["Select S24 without order to declare play and inspect privately, then choose keep/swap. Once inspected, no cancellation is permitted."]
    elif kind == "assign_themata_defenders":
        loc = current_pending(gs)["locale"]
        home = sd.locale(loc)["thema"]
        out.update(required={"markers": "Array of selected reserve indices; [] explicitly declines"},
                   max_markers=battle._value(loc), locale=loc, thema=home,
                   available=[{"index": i, **m.model_dump()} for i, m in enumerate(gs.themata[home])])
    elif kind == "respond_approach":
        pending = current_pending(gs)
        loc = pending["locale"]
        defenders = pending["defenders"]
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
                if campaign._stronghold_size(gs, loc) > inside:
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
                          "Avoid discards Loot/excess Provender. The opponent can supply Local Scouts and combat inputs."])
    elif kind == "cmd_march":
        out["notes"] = ["Optional group uses _co_marchers / _co_marcher_max; the engine recomputes group cost.",
                        "Discard variants remain distinct menu rows; no variant is silently selected.",
                        "Group Carts can change cost. For combinations not represented by a default row, submit a flat action with version=; the engine validates it."]
    if kind in ("respond_approach", "cmd_storm", "cmd_sally", "cmd_sortie"):
        out["combat"] = {
            "battle_events": "Each side explicitly supplies its own held card ids (S6/R24: {card, lord}).",
            "rounds": "steeled_rounds / javelins_rounds: {your_lord: round}; existing default is 1.",
            "decisions": "battle_decisions / storm_decisions: your typed FIFO arrays, e.g. [[concede, true]], scoped to your decisions.",
            "resolution": "Engine combat is atomic. Preserve scripted choices; unscripted choices use its existing fallback.",
            "opponent_input": "An explicit input/decline handoff occurs before dice. No opponent hand is disclosed.",
        }
    out["references"] = ["guide", "rules", "decisions", "errata"]
    return out
