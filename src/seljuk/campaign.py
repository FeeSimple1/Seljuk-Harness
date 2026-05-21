"""Campaign-phase machine and the non-combat Commands (Phase 3a).

Flow (4.0): Capability Discard -> Plan (4.1) -> alternating Command Activations
(4.2) each followed by Feed-Pay-Disband (4.6) -> End Campaign (4.7) and, on the
first three Autumn turns, Winter (4.7.6).

Phase 3a implements the non-combat Command menu (Pass, Tax, Forage, Ravage,
Supply, Recruit). March and the combat Commands (Siege/Storm/Sally) arrive in
Phases 3b/3c; until then the enumerator simply does not offer them.
"""
from __future__ import annotations

from typing import Any

from . import scenarios, static_data as sd, map as gmap
from .rng import DiceRoller
from .state import Assets, GameState, IllegalAction, LordState

SIDES = ["seljuk", "roman"]


def season_index(box: int) -> int:
    return (box - 1) % 3  # 0 Spring, 1 Summer, 2 Autumn


def is_autumn(box: int) -> bool:
    return season_index(box) == 2


def plan_size(gs: GameState) -> int:
    """Required Plan stack size this turn (4.1), honoring a scenario's
    first-turn override (e.g. Year of Treacherous Ambition 6, Manzikert 4)."""
    override = gs.meta.notes.get("first_turn_plan_size")
    if override and not gs.meta.notes.get("first_plan_done"):
        return int(override)
    return [7, 8, 7][season_index(gs.meta.calendar_box)]


# --- predicates shared with actions.py via import there ---------------------

def on_map(lord: LordState) -> bool:
    return lord.mustered and lord.cylinder not in ("calendar", "offboard", "removed")


# --- machine ----------------------------------------------------------------

def start_campaign(gs: GameState) -> None:
    gs.meta.phase = "campaign"
    _capability_discard(gs)
    gs.meta.subphase = "campaign.plan"
    gs.meta.plan_submitted = {}
    gs.meta.active_player = "seljuk"


def _capability_discard(gs: GameState) -> None:
    """4.0: each side discards side-wide Capabilities exceeding its number of
    Mustered Lords (This-Lord Capabilities don't count). Seljuk first."""
    for side in SIDES:
        n_lords = sum(1 for l in gs.lords.values() if l.mustered and l.side == side)
        decks = gs.side_decks(side)
        excess = len(decks.capabilities_in_play) - n_lords
        # Deterministic auto-discard from the end (a player choice in principle;
        # surfaced for the consumer in later phases). Returns cards to the deck.
        while excess > 0 and decks.capabilities_in_play:
            card = decks.capabilities_in_play.pop()
            decks.draw_deck.append(card)
            excess -= 1


def build_plan(gs: GameState, side: str, cards: list[str], lieutenants: list[dict] | None = None) -> dict:
    """4.1: build a side's ordered, face-down Plan stack of Command cards.

    ``cards`` is an ordered list of Lord ids (whose Command card is played) and
    "no_command" entries; its length must equal the required Plan size. Action
    cards are limited to 4 per Lord; No Command to 5 (1.9.2)."""
    if gs.meta.subphase != "campaign.plan":
        raise IllegalAction("wrong_step", "Plan is built in the Campaign Plan step (4.1)")
    if gs.meta.plan_submitted.get(side):
        raise IllegalAction("already_planned", f"{side} already built its Plan")
    need = plan_size(gs)
    if len(cards) != need:
        raise IllegalAction("bad_plan_size", f"{side} Plan must have {need} cards this turn (4.1)")
    counts: dict[str, int] = {}
    for c in cards:
        counts[c] = counts.get(c, 0) + 1
    for c, n in counts.items():
        if c == "no_command":
            if n > 5:
                raise IllegalAction("too_many_no_command", "at most 5 No Command cards (1.9.2)")
            continue
        if c not in gs.lords:
            raise IllegalAction("bad_plan_card", f"no such Lord {c}")
        if c not in sd.command_decks()[side]["lords_with_cards"]:
            raise IllegalAction("lord_not_on_side", f"{c} has no Command cards in the {side} deck")
        if n > 4:
            raise IllegalAction("too_many_lord_cards", f"at most 4 Command cards for {c} (1.9.2)")
    decks = gs.side_decks(side)
    decks.command_plan = list(cards)
    decks.plan_pointer = 0
    # Lieutenants (4.1.3)
    for stack in (lieutenants or []):
        _designate_lieutenant(gs, side, stack["lieutenant"], stack["lower_lord"])
    gs.meta.plan_submitted[side] = True
    if all(gs.meta.plan_submitted.get(s) for s in SIDES):
        gs.meta.notes["first_plan_done"] = True
        _begin_command(gs)
    return {"ok": True, "side": side, "plan": list(cards)}


def _designate_lieutenant(gs: GameState, side: str, lieut: str, lower: str) -> None:
    li, lo = gs.lords.get(lieut), gs.lords.get(lower)
    if li is None or lo is None:
        raise IllegalAction("bad_lord", "lieutenant/lower lord not found")
    if li.side != side or lo.side != side:
        raise IllegalAction("lieutenant_side", "Lieutenant and Lower Lord must be on the planning side")
    if not (on_map(li) and on_map(lo) and li.cylinder == lo.cylinder):
        raise IllegalAction("lieutenant_locale", "Lieutenant and Lower Lord must be at the same Locale (4.1.3)")
    if sd.lord(lieut).get("commander") or sd.lord(lower).get("commander"):
        raise IllegalAction("commander_lieutenant", "a Commander may not be Lieutenant or Lower Lord (4.1.3)")
    if li.lieutenant_of or lo.lower_lord or lo.lieutenant_of or li.lower_lord:
        raise IllegalAction("already_stacked", "a Lord may have only one Lower Lord, and a Lower Lord may not lead (4.1.3)")
    li.lower_lord = lower
    lo.lieutenant_of = lieut


def _begin_command(gs: GameState) -> None:
    gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"  # Seljuk reveals first (4.2)
    _reveal_next(gs)


def _plan_exhausted(gs: GameState, side: str) -> bool:
    d = gs.side_decks(side)
    return d.plan_pointer >= len(d.command_plan)


def _reveal_next(gs: GameState) -> None:
    """Reveal the active side's next Command card, skipping sides whose Plan is
    exhausted. Auto-resolves No Command / off-map / Lower-Lord cards (4.2.3)."""
    for _ in range(len(SIDES) + 1):
        if _plan_exhausted(gs, "seljuk") and _plan_exhausted(gs, "roman"):
            _end_campaign(gs)
            return
        side = gs.meta.active_player
        if _plan_exhausted(gs, side):
            gs.meta.active_player = _other(side)
            continue
        d = gs.side_decks(side)
        card = d.command_plan[d.plan_pointer]
        d.plan_pointer += 1
        gs.meta.active_card = card
        if _is_pass_card(gs, card):
            # No Command, off-map Lord, or a Lower Lord's card -> nothing (4.2.3)
            _after_card(gs)
            return
        lord = gs.lords[card]
        gs.meta.active_lord = card
        gs.meta.actions_remaining = sd.lord(card)["ratings"]["command"]
        return


def _is_pass_card(gs: GameState, card: str) -> bool:
    if card == "no_command":
        return True
    lord = gs.lords.get(card)
    if lord is None or not on_map(lord):
        return True
    if lord.lieutenant_of:  # revealing a Lower Lord's card = Pass (4.1.3)
        return True
    return False


def _other(side: str) -> str:
    return "roman" if side == "seljuk" else "seljuk"


def end_activation(gs: GameState) -> None:
    """Finish the active Lord's card -> Feed-Pay-Disband -> next side's card."""
    _after_card(gs)


def _after_card(gs: GameState) -> None:
    roller = DiceRoller(seed=gs.meta.seed)
    if gs.meta.rng_state is not None:
        st = gs.meta.rng_state
        roller.set_state((st[0], tuple(st[1]), st[2]))
    feed_pay_disband(gs, roller)
    s = roller.get_state()
    gs.meta.rng_state = [s[0], list(s[1]), s[2]]
    gs.meta.active_card = None
    gs.meta.active_lord = None
    gs.meta.actions_remaining = 0
    gs.meta.active_player = _other(gs.meta.active_player)
    _reveal_next(gs)


def spend_actions(gs: GameState, n: int) -> None:
    gs.meta.actions_remaining -= n
    if gs.meta.actions_remaining <= 0:
        _after_card(gs)


# --- Feed - Pay - Disband (4.6) ---------------------------------------------

def _feed_requirement(units: int) -> int:
    if units <= 0:
        return 0
    if units <= 8:
        return 1
    if units <= 12:
        return 2
    if units <= 16:
        return 3
    return 4


def feed_pay_disband(gs: GameState, roller: DiceRoller) -> dict:
    """4.6: Lords who Moved/Fought Feed; then Disband per Service (Pay between
    is a player option handled via the Pay action set, omitted here)."""
    result = {"feed": [], "disband": []}
    for side in SIDES:  # Seljuk then Roman (4.6.1)
        _feed_side(gs, side, result)
    from . import actions
    for side in SIDES:
        result["disband"].extend(actions.resolve_disband(gs, side))
    # Remove Moved/Fought markers (4.6.3)
    for l in gs.lords.values():
        l.moved_fought = False
    gs.meta.vp = scenarios.score(gs)
    return result


def _unit_count(lord: LordState) -> int:
    return sum(lord.forces.values())


def _feed_side(gs: GameState, side: str, result: dict) -> None:
    # Each Lord Feeds his own Forces first (4.6.1); Sharing among co-located
    # Lords then covers shortfalls.
    movers = [l for l in gs.lords.values() if l.side == side and on_map(l) and l.moved_fought]
    for lord in movers:
        need = _feed_requirement(_unit_count(lord))
        paid = _consume_food(lord, need)
        if paid < need:
            paid += _share_food(gs, lord, side, need - paid)
        if paid < need:
            # Unfed: shift Service Marker left one box (4.6.1)
            if lord.service_box is not None:
                lord.service_box = max(0, lord.service_box - 1)
            result["feed"].append({"lord": lord.id, "needed": need, "fed": paid, "unfed": True})
        else:
            result["feed"].append({"lord": lord.id, "needed": need, "fed": paid, "unfed": False})


def _consume_food(lord: LordState, need: int) -> int:
    paid = 0
    for asset in ("provender", "loot"):  # Loot Feeds anywhere (4.6.1)
        while paid < need and getattr(lord.assets, asset) > 0:
            setattr(lord.assets, asset, getattr(lord.assets, asset) - 1)
            paid += 1
    return paid


def _share_food(gs: GameState, hungry: LordState, side: str, need: int) -> int:
    """Co-located friendly Lords must Share Provender/Loot to cover a shortfall
    (4.6.1); a side may not withhold."""
    paid = 0
    for other in gs.lords.values():
        if other is hungry or other.side != side or other.cylinder != hungry.cylinder or not on_map(other):
            continue
        for asset in ("provender", "loot"):
            while paid < need and getattr(other.assets, asset) > 0:
                setattr(other.assets, asset, getattr(other.assets, asset) - 1)
                paid += 1
    return paid


# --- End Campaign (4.7) — minimal in increment 1; full steps in increment 3 -

def _end_campaign(gs: GameState) -> None:
    gs.meta.subphase = "campaign.complete"


# --- action handlers + enumerator (campaign) --------------------------------

def h_build_plan(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    side = action.get("side", gs.meta.active_player)
    if side != gs.meta.active_player:
        raise IllegalAction("not_active_side", f"{side} is not the active planning side")
    res = build_plan(gs, side, list(action.get("cards", [])), action.get("lieutenants"))
    if gs.meta.subphase == "campaign.plan" and not gs.meta.plan_submitted.get(_other(side)):
        gs.meta.active_player = _other(side)
    return res


def h_cmd_pass(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    if gs.meta.subphase != "campaign.command" or gs.meta.active_lord is None:
        raise IllegalAction("wrong_step", "Pass ends the active Lord's card (4.5.8)")
    lord = gs.meta.active_lord
    end_activation(gs)
    return {"ok": True, "action": "cmd_pass", "lord": lord, "now": gs.meta.subphase}


def h_end_activation(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    if gs.meta.subphase != "campaign.command" or gs.meta.active_lord is None:
        raise IllegalAction("wrong_step", "no active Lord to end")
    lord = gs.meta.active_lord
    end_activation(gs)
    return {"ok": True, "action": "end_activation", "lord": lord, "now": gs.meta.subphase}


def legal_moves_campaign(gs: GameState) -> list[dict[str, Any]]:
    step = gs.meta.subphase
    if step == "campaign.plan":
        side = gs.meta.active_player
        if gs.meta.plan_submitted.get(side):
            return []
        avail = [lid for lid in sd.command_decks()[side]["lords_with_cards"]
                 if lid in gs.lords and gs.lords[lid].mustered and gs.lords[lid].side == side]
        return [{"type": "build_plan", "side": side, "_plan_size": plan_size(gs),
                 "_available_lords": avail, "_no_command": "no_command",
                 "_desc": f"Build the {side} Campaign Plan: {plan_size(gs)} ordered cards (4.1)"}]
    if step == "campaign.command" and gs.meta.active_lord is not None:
        moves = command_menu(gs)  # defined in the commands module (increment 2)
        moves.append({"type": "cmd_pass", "_desc": "Pass: the active Lord does nothing (4.5.8)"})
        moves.append({"type": "end_activation", "_desc": "End this Lord's card"})
        return moves
    return []


def command_menu(gs: GameState) -> list[dict[str, Any]]:
    """Non-combat Command options for the active Lord. Extended in increment 2;
    returns [] until the simple-Command handlers land."""
    return []
