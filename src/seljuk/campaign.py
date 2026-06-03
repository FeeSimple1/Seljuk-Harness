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
from . import actions
from . import capabilities
from .rng import DiceRoller
from .state import Assets, GameState, IllegalAction, LordState

SIDES = ["seljuk", "roman"]


def season_index(box: int) -> int:
    return (box - 1) % 3  # 0 Spring, 1 Summer, 2 Autumn


def is_autumn(box: int) -> bool:
    return season_index(box) == 2


def plan_size(gs: GameState, side: str | None = None) -> int:
    """Required Plan stack size this turn (4.1), honoring a scenario's first-turn
    override and any Treachery additions (Treachery card / forced No Command)."""
    override = gs.meta.notes.get("first_turn_plan_size")
    if override and not gs.meta.notes.get("first_plan_done"):
        base = int(override)
    else:
        base = [7, 8, 7][season_index(gs.meta.calendar_box)]
        if gs.meta.notes.get("weather_plan9") and season_index(gs.meta.calendar_box) == 1:
            base = 9  # R17/S17 Unpredictable Weather (Summer)
    if side:
        if gs.meta.notes.get("treachery_side") == side:
            base += 1  # the Treachery card
        if gs.meta.notes.get("treachery_no_command_side") == side:
            base += 1  # forced extra No Command
    return base


# --- predicates shared with actions.py via import there ---------------------

def on_map(lord: LordState) -> bool:
    return lord.mustered and lord.cylinder not in ("calendar", "offboard", "removed")


# --- machine ----------------------------------------------------------------

def start_campaign(gs: GameState) -> None:
    gs.meta.phase = "campaign"
    for _l in gs.lords.values():
        _l.flags.pop("prov_bureau_used_campaign", None)
    _capability_discard(gs)
    # 5.2: a side with no Mustered Lords during Campaign loses immediately.
    if not any(l.mustered and l.side == "seljuk" for l in gs.lords.values()):
        _set_game_over(gs, "roman", "5.2: seljuk has no Mustered Lords during Campaign"); return
    if not any(l.mustered and l.side == "roman" for l in gs.lords.values()):
        _set_game_over(gs, "seljuk", "5.2: roman has no Mustered Lords during Campaign"); return
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
    need = plan_size(gs, side)
    if len(cards) != need:
        raise IllegalAction("bad_plan_size", f"{side} Plan must have {need} cards this turn (4.1)")
    counts: dict[str, int] = {}
    for c in cards:
        counts[c] = counts.get(c, 0) + 1
    nc_cap = 5 + (1 if gs.meta.notes.get("treachery_no_command_side") == side else 0)
    if gs.meta.notes.get("treachery_side") == side and counts.get("treachery", 0) != 1:
        raise IllegalAction("treachery_required", f"{side} must include exactly one Treachery card (1.4)")
    if gs.meta.notes.get("weather_no_command_side") == side and counts.get("no_command", 0) < 1:
        raise IllegalAction("weather_no_command", f"{side} must include 1 No Command this turn (Unpredictable Weather)")
    for c, n in counts.items():
        if c == "treachery":
            if gs.meta.notes.get("treachery_side") != side:
                raise IllegalAction("no_treachery", f"{side} has no Treachery card to play")
            continue
        if c == "no_command":
            if n > nc_cap:
                raise IllegalAction("too_many_no_command", f"at most {nc_cap} No Command cards (1.9.2)")
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
        gs.meta.notes.pop("treachery_side", None)
        gs.meta.notes.pop("treachery_no_command_side", None)
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
        if card == "treachery":
            targets = ["robert_crepin", "roussel_de_bailleul"] if side == "seljuk" else ["arisighi"]
            gs.meta.pending.append({"type": "loyalty_check", "side": side, "targets": targets, "_owed_by": side})
            return
        if _is_pass_card(gs, card):
            # No Command, off-map Lord, or a Lower Lord's card -> nothing (4.2.3)
            _after_card(gs)
            return
        lord = gs.lords[card]
        gs.meta.active_lord = card
        _r = DiceRoller(seed=gs.meta.seed)
        if gs.meta.rng_state is not None:
            _st = gs.meta.rng_state
            _r.set_state((_st[0], tuple(_st[1]), _st[2]))
        gs.meta.actions_remaining = capabilities.command_rating(gs, card, _r)
        _s = _r.get_state(); gs.meta.rng_state = [_s[0], list(_s[1]), _s[2]]
        lord.flags.pop("first_march_used", None)
        lord.flags.pop("mules_used_this_card", None)
        lord.flags.pop("unstoppable_used_this_card", None)
        lord.flags.pop("peace_paid_this_card", None)
        gs.meta.notes.pop("marwanid_supply_lock", None)
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


def _load_fpd_roller(gs: GameState) -> DiceRoller:
    roller = DiceRoller(seed=gs.meta.seed)
    if gs.meta.rng_state is not None:
        st = gs.meta.rng_state
        roller.set_state((st[0], tuple(st[1]), st[2]))
    return roller


def _store_fpd_roller(gs: GameState, roller: DiceRoller) -> None:
    st = roller.get_state()
    gs.meta.rng_state = [st[0], list(st[1]), st[2]]


def _after_card(gs: GameState) -> None:
    if gs.meta.phase == "winter":
        _winter_end_activation(gs)
        return
    roller = _load_fpd_roller(gs)
    _fpd_feed(gs)                       # 4.6.1 Feed (Seljuk then Roman)
    _store_fpd_roller(gs, roller)
    # The Command card is over once Feed/Pay/Disband begins.
    card_player = gs.meta.active_player
    gs.meta.active_card = None
    gs.meta.active_lord = None
    gs.meta.actions_remaining = 0
    # 5.2: a side may already have no Mustered Lords (e.g. all lost in the Battle
    # that ended this card) -> game ends immediately, before any Pay/Disband.
    if _campaign_5_2_over(gs):
        return
    # 4.6.2: any Seljuk then Roman Lords may receive Pay BEFORE Disband. Pause for
    # it when a Pay is available, else go straight to Disband.
    gs.meta.notes["fpd_card_player"] = card_player
    gs.meta.notes["fpd_passed"] = {}
    gs.meta.subphase = "campaign.fpd_pay"
    if _fpd_advance(gs):
        return                          # pause: the active side may Pay (4.6.2)
    _after_card_finish(gs)


def _permanently_disbanded(gs: GameState, lid: str) -> bool:
    l = gs.lords.get(lid)
    return bool(l and l.cylinder == "removed" and not l.flags.get("setup_removed"))


def _campaign_5_2_over(gs: GameState) -> bool:
    """5.2 immediate victory: a permanently Disbanded Alp Arslan -> Romans win
    (in every scenario; a 'removed' Lord was necessarily in play, satisfying the
    Specter 'until he comes into play' caveat). Manzikert: a permanently
    Disbanded Romanos IV -> Seljuks win. Then the no-Mustered-Lords loss (5.2)."""
    if _permanently_disbanded(gs, "alp_arslan"):
        _set_game_over(gs, "roman", "5.2: Alp Arslan permanently Disbanded")
        return True
    if gs.meta.scenario == "manzikert" and _permanently_disbanded(gs, "romanos_diogenes"):
        _set_game_over(gs, "seljuk", "5.2: Romanos IV permanently Disbanded (Manzikert)")
        return True
    if not any(l.mustered and l.side == "seljuk" for l in gs.lords.values()):
        _set_game_over(gs, "roman", "5.2: seljuk has no Mustered Lords during Campaign")
        return True
    if not any(l.mustered and l.side == "roman" for l in gs.lords.values()):
        _set_game_over(gs, "seljuk", "5.2: roman has no Mustered Lords during Campaign")
        return True
    return False


def _fpd_advance(gs: GameState) -> bool:
    """Give the FPD Pay turn to the next side (Seljuk then Roman) that has not
    finished and still has a legal Pay (4.6.2). Returns False when both are done."""
    passed = gs.meta.notes.get("fpd_passed", {})
    for side in SIDES:
        if passed.get(side):
            continue
        gs.meta.active_player = side
        if actions.enumerate_pay(gs):
            return True
    return False


def h_fpd_done(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """4.6.2: the active side finishes its Pay; when both sides are done, Disband
    and continue to the next Command card."""
    if gs.meta.subphase != "campaign.fpd_pay":
        raise IllegalAction("wrong_step", "not in the Feed/Pay/Disband Pay step (4.6.2)")
    done_side = gs.meta.active_player
    gs.meta.notes.setdefault("fpd_passed", {})[done_side] = True
    if not _fpd_advance(gs):
        _after_card_finish(gs)
    return {"ok": True, "action": "fpd_done", "side": done_side}


def _after_card_finish(gs: GameState) -> None:
    roller = _load_fpd_roller(gs)
    _fpd_disband(gs, roller)            # 4.6.2 Disband + 4.6.3 remove Moved/Fought
    _store_fpd_roller(gs, roller)
    card_player = gs.meta.notes.pop("fpd_card_player", gs.meta.active_player)
    gs.meta.notes.pop("fpd_passed", None)
    gs.meta.subphase = "campaign.command"
    # 5.2: Disband may have removed a side's last Mustered Lord.
    if _campaign_5_2_over(gs):
        return
    gs.meta.active_player = _other(card_player)
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


def _fpd_feed(gs: GameState) -> dict:
    """4.6.1 Feed: each Lord who Moved/Fought Feeds (Seljuk then Roman)."""
    result = {"feed": [], "disband": []}
    for side in SIDES:
        _feed_side(gs, side, result)
    return result


def _fpd_disband(gs: GameState, roller: DiceRoller) -> dict:
    """4.6.2 Disband (after Pay) + 4.6.3 remove Moved/Fought markers."""
    result = {"disband": []}
    for side in SIDES:
        result["disband"].extend(actions.resolve_disband(gs, side))
    # SMOKE-005 (4.3.5/4.4.1): a Besieged/Bypassed Stronghold whose besiegers all
    # Disbanded becomes free of Enemy Lords -> drop its Siege/Bypass markers.
    for _loc in gs.locales:
        _refresh_invest(gs, _loc)
    for l in gs.lords.values():
        l.moved_fought = False
    gs.meta.vp = scenarios.score(gs)
    return result


def feed_pay_disband(gs: GameState, roller: DiceRoller) -> dict:
    """Non-interactive Feed + Disband (4.6) for direct/test use. During play the
    interactive Pay (4.6.2) between Feed and Disband is surfaced by _after_card."""
    result = _fpd_feed(gs)
    result["disband"] = _fpd_disband(gs, roller)["disband"]
    return result


def _unit_count(lord: LordState) -> int:
    return sum(lord.forces.values())


def _feed_side(gs: GameState, side: str, result: dict) -> None:
    # Each Lord Feeds his own Forces first (4.6.1); Sharing among co-located
    # Lords then covers shortfalls.
    movers = [l for l in gs.lords.values() if l.side == side and on_map(l) and l.moved_fought]
    # B.3.1: ALL Lords Feed their own Forces from their own mats FIRST; only then
    # do co-located Lords Share to cover remaining shortfalls. Doing this in one
    # interleaved pass would let an early mover drain a later (not-yet-fed)
    # mover's Provender and penalise the wrong Lord.
    fed = []  # [lord, need, paid]
    for lord in movers:
        need = _feed_requirement(_unit_count(lord))
        fed.append([lord, need, _consume_food(lord, need)])
    # Share to cover shortfalls, smallest remaining shortfall FIRST -- this
    # maximises the number of fully-fed Lords (minimising Unfed Service shifts,
    # B.3.1), instead of letting one big-need Lord drain the shared Provender.
    for entry in sorted((e for e in fed if e[2] < e[1]), key=lambda e: e[1] - e[2]):
        lord, need, paid = entry
        entry[2] = paid + _share_food(gs, lord, side, need - paid)
    for lord, need, paid in fed:
        if paid < need:
            # Unfed: shift Service Marker left one box (4.6.1)
            if lord.service_box is not None:
                lord.service_box = max(0, lord.service_box - 1)
                from .state import shift_vassal_service
                shift_vassal_service(gs, lord, -1)  # 6.2
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


# --- End Campaign (4.7) and Winter (4.7.6) ----------------------------------

def _set_game_over(gs: GameState, winner: str, reason: str = "") -> None:
    gs.meta.phase = "game_over"
    gs.meta.subphase = "game_over"
    gs.meta.notes["winner"] = winner
    gs.meta.notes["win_reason"] = reason


def _end_campaign(gs: GameState) -> None:
    gs.meta.subphase = "campaign.end"
    box = gs.meta.calendar_box
    _grow(gs)       # 4.7.2 (Spring only)
    _repair(gs)     # 4.7.3
    _wastage(gs)    # 4.7.4
    _reset(gs)      # 4.7.5 (non-advance parts)
    gs.meta.vp = scenarios.score(gs)
    if box in (3, 6, 9):                # 4.7.6 Winter on the first three Autumns
        # Winter Campaign / Winter March (R9/S18): a pre-Bounty activation
        # window. Pause if either side Holds the card; else resolve Winter now.
        holders = [s for s, c in (("roman", "R9"), ("seljuk", "S18"))
                   if c in gs.side_decks(s).held_events]
        if holders:
            gs.meta.phase = "winter"
            gs.meta.subphase = "winter.activation"
            gs.meta.active_player = holders[0]
            gs.meta.active_lord = None
            gs.meta.notes["winter_holders"] = holders
            return
        _finalize_winter(gs)
        return
    _advance_or_end(gs)


def _finalize_winter(gs: GameState) -> None:
    winner = _winter(gs)
    gs.meta.vp = scenarios.score(gs)
    if winner:
        _set_game_over(gs, winner, "5.2/4.7.6: Seljuk Aleppo Independence auto-victory")
        return
    _advance_or_end(gs)


def _advance_or_end(gs: GameState) -> None:
    box = gs.meta.calendar_box
    if box >= gs.meta.final_box:        # 4.7.1 Game End
        w = scenarios.end_of_scenario_winner(gs)
        _set_game_over(gs, w, "5.3: " + ("most VP at end of final Turn" if w != "draw" else "VP tied at end of final Turn"))
        return
    gs.meta.calendar_box = box + 1      # advance to next Turn's Levy (4.7.5)
    gs.meta.phase = "levy"
    gs.meta.subphase = None
    gs.meta.plan_submitted = {}
    gs.meta.active_card = None
    gs.meta.active_lord = None
    gs.meta.notes.pop("winter_holders", None)


def _winter_end_activation(gs: GameState) -> None:
    """Called when a Winter-activated Lord's card ends (instead of the campaign
    _after_card). Move to the next Holder, or finalize Winter."""
    gs.meta.active_lord = None
    gs.meta.active_card = None
    gs.meta.actions_remaining = 0
    holders = gs.meta.notes.get("winter_holders", [])
    if holders:
        gs.meta.active_player = holders[0]   # next Holder may activate or proceed
    else:
        _finalize_winter(gs)


def h_winter_activate(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """R9/S18: play the Held card to activate one Lord in Winter (one Command card)."""
    if gs.meta.subphase != "winter.activation":
        raise IllegalAction("wrong_step", "Winter activation only in the Winter window (R9/S18)")
    side = gs.meta.active_player
    card = "R9" if side == "roman" else "S18"
    if card not in gs.side_decks(side).held_events:
        raise IllegalAction("not_held", f"{side} does not hold {card}")
    lord = gs.lords.get(action.get("lord"))
    if lord is None or lord.side != side or not lord.mustered:
        raise IllegalAction("bad_lord", "activate one of your Mustered Lords (R9/S18)")
    gs.side_decks(side).held_events.remove(card)
    gs.side_decks(side).draw_deck.append(card)
    gs.meta.notes["winter_holders"] = [h for h in gs.meta.notes.get("winter_holders", []) if h != side]
    gs.meta.active_lord = lord.id
    gs.meta.active_card = lord.id
    gs.meta.actions_remaining = capabilities.command_rating(gs, lord.id, roller)
    lord.flags.pop("first_march_used", None)
    return {"ok": True, "action": "winter_activate", "lord": lord.id, "actions": gs.meta.actions_remaining}


def h_winter_proceed(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """Decline a Winter activation; move to the next Holder or resolve Winter."""
    if gs.meta.subphase != "winter.activation":
        raise IllegalAction("wrong_step", "not in the Winter activation window")
    side = gs.meta.active_player
    gs.meta.notes["winter_holders"] = [h for h in gs.meta.notes.get("winter_holders", []) if h != side]
    holders = gs.meta.notes["winter_holders"]
    if holders:
        gs.meta.active_player = holders[0]
        return {"ok": True, "action": "winter_proceed", "next_holder": holders[0]}
    _finalize_winter(gs)
    return {"ok": True, "action": "winter_proceed", "winter_resolved": True}


def _grow(gs: GameState) -> None:
    """4.7.2: at the end of each Spring turn, each side reduces the ENEMY's
    Ravaged markers to half (rounded up) — i.e. removes floor(N/2)."""
    if season_index(gs.meta.calendar_box) != 0:
        return
    for victim in ("roman", "seljuk"):  # Seljuk reduces Roman's, Roman reduces Seljuk's
        marked = [lid for lid, l in gs.locales.items() if l.ravaged_side == victim]
        remove = len(marked) // 2
        for lid in marked[:remove]:
            gs.locales[lid].ravaged_side = None


def _repair(gs: GameState) -> None:
    """4.7.3: remove one Siege marker from each Stronghold with 3 or 4."""
    for l in gs.locales.values():
        if l.siege_markers >= 3:
            l.siege_markers -= 1


def _do_one_wastage(gs: GameState, l: LordState) -> bool:
    """Discard one excess Asset (or a This-Lord Capability) from a Lord (4.7.4).
    Returns False if the Lord did not qualify (<=1 of each, <=1 Capability)."""
    assets = {"carts": l.assets.carts, "provender": l.assets.provender,
              "coin": l.assets.coin, "loot": l.assets.loot}
    top = max(assets, key=lambda k: assets[k])
    if assets[top] > 1:
        setattr(l.assets, top, assets[top] - 1)
        return True
    if len(l.capabilities) > 1:
        gs.side_decks(l.side).draw_deck.append(l.capabilities.pop())
        return True
    return False


def _wastage(gs: GameState) -> None:
    """4.7.4: each Lord with more than one of any Asset type, or more than one
    This-Lord Capability, discards one such item (Seljuk then Roman). R22/S22
    raiders then force one adjacent enemy Lord to undergo Wastage a second time."""
    for side in SIDES:
        for l in gs.lords.values():
            if l.side == side and l.mustered:
                _do_one_wastage(gs, l)
    # R22 Cavalry Supply Line Raiders / S22 Turkmen Skirmishers: each such Lord
    # forces ONE adjacent enemy Lord to Waste again (owner's choice -> nearest by
    # map order). Targets are gathered first, then re-Wasted.
    targets: list[LordState] = []
    for l in gs.lords.values():
        if not (l.mustered and l.cylinder in gs.locales):
            continue
        if not (capabilities.lord_has(gs, l.id, "Cavalry Supply Line Raiders")
                or capabilities.lord_has(gs, l.id, "Turkmen Skirmishers")):
            continue
        for adj in gmap.neighbors(l.cylinder):
            enemy = next((o for o in gs.lords.values()
                          if o.mustered and o.cylinder == adj and o.side != l.side), None)
            if enemy is not None:
                targets.append(enemy)
                break
    for enemy in targets:
        _do_one_wastage(gs, enemy)


def _reset(gs: GameState) -> None:
    """4.7.5 (non-advance parts): return unpaid Themata, unstack Lieutenants,
    discard This-Campaign Events. (Auto-returns Themata; pay-to-retain is a
    player choice surfaced in a later phase.)"""
    # R4 Pressed Levy Service: the Romans may keep 1 Unpaid Thema's Levied
    # Themata. Auto-choice: retain the Thema with the most Levied markers.
    keep_thema = None
    if capabilities.side_has(gs, "roman", "Pressed Levy Service"):
        from collections import Counter
        counts: Counter = Counter()
        for l in gs.lords.values():
            if l.side == "roman":
                for m in l.themata_on_mat:
                    if m.home_thema:
                        counts[m.home_thema] += 1
        if counts:
            keep_thema = counts.most_common(1)[0][0]
    for l in gs.lords.values():
        kept = []
        for marker in l.themata_on_mat:
            home = marker.home_thema
            if keep_thema is not None and l.side == "roman" and home == keep_thema:
                kept.append(marker)  # Pressed Levy: retain this Thema's Levied markers
                continue
            if home and home in gs.themata:
                marker.home_thema = None
                gs.themata[home].append(marker)
        l.themata_on_mat = kept
        l.lieutenant_of = None
        l.lower_lord = None
    for side in SIDES:
        gs.side_decks(side).this_campaign_events = []
    gs.meta.notes.pop("moustache_campaign", None)
    gs.meta.notes.pop("peace_offering_season", None)
    gs.meta.notes.pop("gifts_coins", None)
    gs.meta.notes.pop("gifts_taken", None)
    for _wk in ("weather_pass_block", "weather_plan9", "weather_no_command_side"):
        gs.meta.notes.pop(_wk, None)


def _winter(gs: GameState) -> str | None:
    """4.7.6: Aleppo auto-victory, Bounty, Seljuk Unity, Winter Quarters,
    Aleppo Diplomacy. Returns a winning side if the Aleppo auto-victory fires."""
    # Aleppo Independence auto-victory (5.2)
    if gs.meta.aleppo_independence_played and gs.locales["aleppo"].conquered_side == "seljuk":
        return "seljuk"
    _bounty(gs)
    _seljuk_unity(gs)
    _winter_quarters(gs)
    _aleppo_diplomacy(gs)
    gs.meta.notes.pop("marwanid_seats", None)  # 3.5.1.1: deactivate at end of Winter Phase
    return None


def _bounty_traversable(gs: GameState, locale_id: str) -> bool:
    """A Locale a Seljuk Bounty path may pass through (4.7.6, errata: Enemy
    Lords block)."""
    if _enemy_lords_at(gs, locale_id, "seljuk") > 0:
        return False
    st = gs.locales[locale_id]
    info = sd.locale(locale_id)
    if st.ruins or info["type"] in ("wilderness", "unfortified_settlement", "holding_box"):
        return True
    if info.get("is_stronghold"):
        friendly = actions.current_allegiance(gs, locale_id) == "seljuk"
        if friendly:
            return True
        # Enemy Stronghold: only if Bypassed or Besieged
        return st.bypass or st.siege_markers > 0
    return True


def _bounty(gs: GameState) -> None:
    for lid, lord in gs.lords.items():
        if lord.side != "seljuk" or not on_map(lord) or lord.assets.loot <= 0:
            continue
        seats = list(sd.lord(lid).get("seats", []))
        if lid == "artuk_beg" and capabilities.lord_has(gs, "artuk_beg", "Artukid Legacy"):
            seats += ["amid", "mayyafariqin"]  # S10: Mayyafariqin AND Amid (base Seat already included)
        seats += [s for s in gs.meta.notes.get("marwanid_seats", []) if s not in seats]  # Marwanid Alliance (S8) activated Seats
        # BFS over bounty-traversable Locales from the Lord to one of his Seats.
        from collections import deque
        seen = {lord.cylinder}
        dq = deque([lord.cylinder])
        reached = lord.cylinder in seats
        while dq and not reached:
            cur = dq.popleft()
            for edge in gmap.ways_from(cur):
                nxt = edge["to"]
                if nxt in seen:
                    continue
                if nxt in seats:
                    reached = True
                    break
                if _bounty_traversable(gs, nxt):
                    seen.add(nxt)
                    dq.append(nxt)
        if not reached:
            continue
        carts = lord.assets.carts + sum(
            o.assets.carts for o in gs.lords.values()
            if o is not lord and o.side == "seljuk" and o.cylinder == lord.cylinder and on_map(o))
        cap = carts + (1 if capabilities.lord_has(gs, lid, "Prisoners") else 0)  # S24
        scored = min(lord.assets.loot, cap)
        lord.assets.loot -= scored
        # B.5.3: positive Bounty VPs first remove Roman Conquered 1 VP markers
        # placed in the Constantinople Holding Box by a prior Seljuk Unity shortfall.
        if gs.holding_boxes.constantinople_roman_vp_markers > 0 and scored > 0:
            cancel = min(scored, gs.holding_boxes.constantinople_roman_vp_markers)
            gs.holding_boxes.constantinople_roman_vp_markers -= cancel
            scored -= cancel
        gs.holding_boxes.mosul_baghdad_loot += scored


def _seljuk_unity(gs: GameState) -> None:
    target = gs.meta.seljuk_unity_targets.get(str(gs.meta.calendar_box))
    if not target:
        return
    count = sum(1 for l in gs.locales.values()
                if (l.ruins and (l.ruins_color or "seljuk") == "seljuk")
                or l.conquered_side == "seljuk" or l.ravaged_side == "seljuk")
    if count >= target:
        return
    deficit = target - count
    take = min(deficit, gs.holding_boxes.mosul_baghdad_loot)
    gs.holding_boxes.mosul_baghdad_loot -= take
    gs.holding_boxes.constantinople_roman_vp_markers += (deficit - take)


def _winter_quarters(gs: GameState) -> None:
    """4.7.6: return Lords to their Seats Unladen; Seat-if-Conquered -> allied
    Holding Box; halve Carts (round up). (Capabilities that let a Lord stay are
    Phase 4.)"""
    for lid, lord in gs.lords.items():
        if not on_map(lord):
            continue
        if (capabilities.lord_has(gs, lid, "Fealty to the Basileus")
                or capabilities.lord_has(gs, lid, "Nizam al-Mulk Administrates the Sultanate")):
            continue  # may choose not to return to Seat in Winter (R15 / S15)
        seats = sd.lord(lid).get("seats", [])
        dest = None
        for s in seats:
            if gs.locales[s].conquered_side not in (None, lord.side):
                continue
            dest = s
            break
        if dest is None:
            dest = "to_mosul_and_baghdad" if lord.side == "seljuk" else "to_constantinople"
        lord.cylinder = dest
        lord.assets.loot = 0  # Unladen: discard Loot
        # Unladen also requires Provender <= Carts; this is checked against the
        # Lord's CURRENT Carts and only THEN are Carts halved (B.5.4 order).
        lord.assets.provender = min(lord.assets.provender, lord.assets.carts)
        lord.assets.carts = -(-lord.assets.carts // 2)  # halve, round up
        lord.besieged = False
        lord.bypassed = False


def _aleppo_diplomacy(gs: GameState) -> None:
    if not gs.meta.independent_aleppo_on_map:
        return
    roller = DiceRoller(seed=gs.meta.seed)
    if gs.meta.rng_state is not None:
        s = gs.meta.rng_state
        roller.set_state((s[0], tuple(s[1]), s[2]))
    roll = roller.d6()
    st = roller.get_state()
    gs.meta.rng_state = [st[0], list(st[1]), st[2]]
    if roll <= 2:
        gs.meta.independent_aleppo_on_map = False


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
    if gs.meta.subphase not in ("campaign.command", "winter.activation") or gs.meta.active_lord is None:
        raise IllegalAction("wrong_step", "Pass ends the active Lord's card (4.5.8)")
    lord = gs.meta.active_lord
    end_activation(gs)
    return {"ok": True, "action": "cmd_pass", "lord": lord, "now": gs.meta.subphase}


def h_end_activation(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    if gs.meta.subphase not in ("campaign.command", "winter.activation") or gs.meta.active_lord is None:
        raise IllegalAction("wrong_step", "no active Lord to end")
    lord = gs.meta.active_lord
    end_activation(gs)
    return {"ok": True, "action": "end_activation", "lord": lord, "now": gs.meta.subphase}


def legal_moves_campaign(gs: GameState) -> list[dict[str, Any]]:
    if gs.meta.subphase == "winter.activation":
        if gs.meta.active_lord is not None:
            return command_menu(gs) + [{"type": "end_activation", "_desc": "End the Winter activation"}]
        side = gs.meta.active_player
        card = "R9" if side == "roman" else "S18"
        out = [{"type": "winter_proceed", "_desc": "Decline the Winter activation (R9/S18)"}]
        if card in gs.side_decks(side).held_events:
            out = [{"type": "winter_activate", "lord": lid,
                    "_desc": f"Winter Campaign/March: activate {lid} (R9/S18)"}
                   for lid, l in gs.lords.items() if l.mustered and l.side == side] + out
        return out
    br = next((p for p in gs.meta.pending if p["type"] == "basil_response"), None)
    if br is not None:
        return [{"type": "basil_response", "play": True, "_desc": "Play Basil: Surrender -> Bypass (R7)"},
                {"type": "basil_response", "play": False, "_desc": "Decline: Stronghold is Conquered"}]
    lc = next((p for p in gs.meta.pending if p["type"] == "loyalty_check"), None)
    if lc is not None:
        return [{"type": "resolve_loyalty", "target": tgt, "_desc": f"Loyalty Check vs {tgt} (1.4)"}
                for tgt in lc["targets"]]
    at = next((p for p in gs.meta.pending if p["type"] == "assign_themata_defenders"), None)
    if at is not None:
        thema = sd.locale(at["locale"])["thema"]
        box = gs.themata.get(thema, [])
        return [{"type": "assign_themata_defenders", "_locale": at["locale"], "_thema": thema,
                 "_available": [{"index": i, "unit": m.unit} for i, m in enumerate(box)],
                 "_desc": "Assign up to Size available Themata to defend the Stronghold (4.3.5)"}]
    ap = next((p for p in gs.meta.pending if p["type"] == "approach_response"), None)
    if ap is not None:
        return [{"type": "respond_approach", "_defenders": ap["defenders"], "_locale": ap["locale"],
                 "_desc": "Each defending Lord: Avoid Battle / Withdraw / Stand (4.3.4)"}]
    bb = next((p for p in gs.meta.pending if p["type"] == "besiege_or_bypass"), None)
    if bb is not None:
        return [{"type": "besiege_bypass", "choice": "besiege", "_desc": "Besiege the Stronghold (4.3.5)"},
                {"type": "besiege_bypass", "choice": "bypass", "_desc": "Bypass the Stronghold (4.3.5)"}]
    pend = next((p for p in gs.meta.pending if p["type"] == "ravage_defence"), None)
    if pend is not None:
        moves = [{"type": "resolve_ravage_defence", "defend_with": None,
                  "_desc": "Decline to defend the Ravage with a Themata (4.5.5)"}]
        for opt in pend["options"]:
            moves.append({"type": "resolve_ravage_defence", "defend_with": opt["index"],
                          "_desc": f"Defend with {opt['unit']} Themata (4.5.5)"})
        return moves
    step = gs.meta.subphase
    if step == "campaign.plan":
        side = gs.meta.active_player
        if gs.meta.plan_submitted.get(side):
            return []
        avail = [lid for lid in sd.command_decks()[side]["lords_with_cards"]
                 if lid in gs.lords and gs.lords[lid].mustered and gs.lords[lid].side == side]
        need = plan_size(gs, side)  # include any Treachery card owed by this side (4.1)
        treachery_required = gs.meta.notes.get("treachery_side") == side
        return [{"type": "build_plan", "side": side, "_plan_size": need,
                 "_available_lords": avail, "_no_command": "no_command",
                 "_treachery_required": treachery_required, "_treachery": "treachery",
                 "_no_command_required": gs.meta.notes.get("weather_no_command_side") == side,
                 "_desc": f"Build the {side} Campaign Plan: {need} ordered cards (4.1)"
                          + (" incl. one Treachery card" if treachery_required else "")}]
    if step == "campaign.fpd_pay":
        moves = actions.enumerate_pay(gs)  # 4.6.2: Pay as per Levy (3.2)
        moves.append({"type": "fpd_done", "_desc": "Finish Pay for this side, then Disband (4.6.2)"})
        return moves
    if step == "campaign.command" and gs.meta.active_lord is not None:
        moves = command_menu(gs)  # defined in the commands module (increment 2)
        moves.append({"type": "cmd_pass", "_desc": "Pass: the active Lord does nothing (4.5.8)"})
        moves.append({"type": "end_activation", "_desc": "End this Lord's card"})
        return moves
    return []


def command_menu(gs: GameState) -> list[dict[str, Any]]:
    """Non-combat Command options for the active Lord (March/combat in 3b/3c).
    Defensive: a data hiccup suppresses an option rather than crashing (lessons)."""
    out: list[dict[str, Any]] = []
    if gs.meta.active_lord is None or gs.meta.actions_remaining <= 0:
        return out
    lord = gs.lords[gs.meta.active_lord]
    loc_id = lord.cylinder
    lid = lord.id
    try:
        st = gs.locales[loc_id]
        info = sd.locale(loc_id)
        # March (4.3): one option per connected Way the active Lord can actually
        # take now (mirror h_cmd_march: not over-laden, affordable, legal dest).
        if not lord.besieged:
            mgroup = _marching_group(gs, lord, [])
            if not _over_laden(gs, mgroup):
                first_march = not lord.flags.get("first_march_used")
                for edge in gmap.ways_from(loc_id):
                    to = edge["to"]
                    dest_info = sd.locale(to)
                    if dest_info["type"] == "holding_box" and dest_info["allegiance"] != lord.side:
                        continue  # no Lord may enter an Enemy Holding Box (1.3.1)
                    if edge["type"] == "pass" and _passes_blocked(gs):
                        continue  # Unpredictable Weather: no Pass March
                    way = _way_between(loc_id, to, edge["type"])
                    if way is None:
                        continue
                    cost = march_cost(gs, mgroup, way, first_march)
                    if cost != "whole_card":  # whole-card Ways always use the rest of the card
                        if (way["type"] == "pass" and len(mgroup) == 1 and not lord.lower_lord
                                and not lord.lieutenant_of and capabilities.lord_has(gs, lord.id, "Mules")
                                and not lord.flags.get("mules_used_this_card")):
                            cost = min(cost, 1)  # Mules: first Pass March = 1 (no state mutation here)
                        if cost > gs.meta.actions_remaining:
                            continue
                    out.append({"type": "cmd_march", "lord": lid, "to": to, "way_type": edge["type"],
                                "_desc": f"March to {sd.locale(to)['name']} via {edge['type']} (4.3)"})
        # Forage (4.5.4): available unless Ravaged, or Besieged by >= Size (a Lord
        # Besieged by fewer, or at a friendly Gardens Town/City, may still Forage).
        if st.ravaged_side is None:
            _g = info.get("gardens") and info["type"] in ("town", "city") and actions.is_friendly_locale(gs, loc_id, lord.side)
            _sz = {"fort": 1, "town": 2, "city": 3}.get(info["type"], 0)
            _heavy = info.get("is_stronghold") and not st.ruins and _enemy_lords_at(gs, loc_id, lord.side) >= _sz and _sz > 0
            if not _heavy or _g:
                out.append({"type": "cmd_forage", "lord": lid, "_desc": "Forage for Provender (4.5.4)"})
        # Tax (4.5.6): own Seat, or Roman Commander Friendly Empire Stronghold.
        if not lord.besieged:
            at_seat = loc_id in sd.lord(lid).get("seats", [])
            empire_tax = (actions.is_commander(gs, lid) and lord.side == "roman"
                          and info.get("is_stronghold") and info["allegiance"] == "roman"
                          and actions.is_friendly_locale(gs, loc_id, "roman")
                          and st.ravaged_side is None)
            if at_seat or empire_tax:
                out.append({"type": "cmd_tax", "lord": lid, "_desc": "Tax for a Coin — uses the whole card (4.5.6)"})
        # Ravage (4.5.5): Enemy, not yet Ravaged, not Besieged.
        if not lord.besieged and st.ravaged_side is None and actions.current_allegiance(gs, loc_id) == _enemy(lord.side):
            if lord.side == "roman":
                out.append({"type": "cmd_ravage", "lord": lid, "_desc": "Ravage (Roman, 1 action, auto) (4.5.5)"})
            else:
                if gs.meta.actions_remaining >= 2:
                    out.append({"type": "cmd_ravage", "lord": lid, "actions": 2, "_desc": "Ravage (Seljuk, 2 actions, auto) (4.5.5)"})
                if gs.meta.actions_remaining >= 1:
                    out.append({"type": "cmd_ravage", "lord": lid, "actions": 1, "_desc": "Ravage (Seljuk, 1 action; Roman may defend with Themata) (4.5.5)"})
        # S3 Steppe Raiders: Ravage an adjacent enemy Locale with no enemy Lord.
        if (not lord.besieged and lord.forces.get("turkic_horse", 0) > 0
                and capabilities.lord_has(gs, lid, "Steppe Raiders")):
            for _adj in gmap.neighbors(loc_id):
                ast = gs.locales[_adj]
                if (ast.ravaged_side is None and actions.current_allegiance(gs, _adj) == _enemy(lord.side)
                        and not any(o.mustered and o.cylinder == _adj and o.side != lord.side for o in gs.lords.values())):
                    if lord.side == "roman":
                        out.append({"type": "cmd_ravage", "lord": lid, "target": _adj,
                                    "_desc": f"Steppe Raid (Ravage adjacent {_adj}) (S3)"})
                    elif gs.meta.actions_remaining >= 1:
                        out.append({"type": "cmd_ravage", "lord": lid, "target": _adj, "actions": 2,
                                    "_desc": f"Steppe Raid (Ravage adjacent {_adj}) (S3)"})
        # Supply (4.4): a Route to an un-Ruined Seat within Cart budget.
        if not lord.besieged:
            cost = _min_supply_cost(gs, lord)
            if cost is not None and cost <= _available_carts(gs, lord) and lord.assets.provender < 8:
                out.append({"type": "cmd_supply", "lord": lid, "_desc": "Supply Provender via a Route (4.4)"})
        # Siege/Storm (4.5.1-.2): a Besieging Lord may advance the Siege or Storm.
        if lord.bypassed and st.bypass:  # 4.3.6 ENCAMP
            out.append({"type": "cmd_encamp", "lord": lid, "_desc": "Encamp: convert Bypass to Siege (4.3.6)"})
        if (not lord.bypassed and st.bypass and actions.current_allegiance(gs, loc_id) == lord.side
                and any(o.mustered and o.cylinder == loc_id and o.side == _enemy(lord.side) and o.bypassed
                        for o in gs.lords.values())):  # 4.3.6 SORTIE
            out.append({"type": "cmd_sortie", "lord": lid, "_desc": "Sortie: Approach the Bypassing Enemy (4.3.6)"})
        if _besieging(gs, lord) and _peace_can_pay(gs, lord):
            out.append({"type": "cmd_siege", "lord": lid, "_desc": "Siege: roll Surrender / add Siegeworks (4.5.1)"})
            out.append({"type": "cmd_storm", "lord": lid, "_desc": "Storm the Stronghold (4.5.2)"})
        if (gs.meta.notes.get("gifts_coins", 0) > 0 and not lord.besieged
                and gs.meta.notes.get("gifts_taken", {}).get(lord.side, 0) < 2):
            out.append({"type": "cmd_take_gift_coin", "lord": lid, "_desc": "Take 1 Coin from Gifts Exchanged (S13)"})
        # Sally (4.5.3): a Besieged Lord may Attack the Besiegers.
        if lord.besieged:
            out.append({"type": "cmd_sally", "lord": lid, "_desc": "Sally against the Besiegers (4.5.3)"})
        # Recruit (4.5.7): Roman Commander in a Thema with available Themata.
        if lord.side == "roman" and actions.is_commander(gs, lid) and not lord.besieged:
            thema = info.get("thema")
            if thema and gs.themata.get(thema):
                out.append({"type": "cmd_recruit", "lord": lid, "_desc": "Recruit a Themata into Forces (4.5.7)"})
    except (KeyError, AttributeError):  # pragma: no cover - suppress over offer
        return out
    return out


# === Non-combat Commands (Phase 3a) =========================================
# March and the combat Commands (Siege/Storm/Sally) are Phases 3b/3c.

def _active_lord(gs: GameState) -> LordState:
    if gs.meta.subphase != "campaign.command" or gs.meta.active_lord is None:
        raise IllegalAction("no_active_lord", "no Lord is currently activated")
    return gs.lords[gs.meta.active_lord]


def _require(lord_id: str, gs: GameState) -> LordState:
    if gs.meta.active_lord != lord_id:
        raise IllegalAction("not_active_lord", f"{lord_id} is not the activated Lord")
    return gs.lords[lord_id]


def _enemy(side: str) -> str:
    return "roman" if side == "seljuk" else "seljuk"


def _enemy_lords_at(gs: GameState, locale_id: str, side: str) -> int:
    return sum(1 for l in gs.lords.values()
               if l.mustered and l.cylinder == locale_id and l.side == _enemy(side))


# --- Tax (4.5.6) ------------------------------------------------------------

def h_cmd_tax(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if lord.besieged:
        raise IllegalAction("besieged", "a Besieged Lord may not Tax (4.5.6)")
    loc_id = lord.cylinder
    if loc_id in gs.meta.notes.get("marwanid_seats", []):
        raise IllegalAction("marwanid_no_tax", "Lords may not Tax an activated Marwanid Locale (3.5.1.1)")
    info = sd.lord(lord.id)
    at_own_seat = loc_id in info.get("seats", [])
    commander_empire_tax = False
    if not at_own_seat:
        # Roman Commander may Tax any Friendly Stronghold in the Roman Empire (not his Seat).
        if actions.is_commander(gs, lord.id) and lord.side == "roman":
            loc = sd.locale(loc_id)
            if loc.get("is_stronghold") and loc["allegiance"] == "roman" \
                    and actions.is_friendly_locale(gs, loc_id, "roman"):
                if gs.locales[loc_id].ravaged_side is not None:
                    raise IllegalAction("already_ravaged", "Roman Commander may not Tax a Ravaged Stronghold (4.5.6)")
                commander_empire_tax = True
        if not commander_empire_tax:
            raise IllegalAction("not_taxable", "Tax requires the Lord's own Seat, or Roman Commander Tax in the Empire (4.5.6)")
    lord.assets.coin = min(lord.assets.coin + 1, 8)
    placed_ravage = False
    if commander_empire_tax:
        prov = (capabilities.lord_has(gs, lord.id, "Provincial Bureaucracy")
                and not lord.flags.get("prov_bureau_used_campaign"))
        if prov:
            lord.flags["prov_bureau_used_campaign"] = True  # R9: first Empire Tax this Campaign, no Ravaged
        else:
            gs.locales[loc_id].ravaged_side = "seljuk"  # Roman Commander Tax places a Seljuk Ravaged marker
            placed_ravage = True
            gs.meta.vp = scenarios.score(gs)
    gs.meta.actions_remaining = 0  # Tax uses the entire card (4.5.6)
    _after_card(gs)
    return {"ok": True, "action": "cmd_tax", "lord": lord.id, "coin": lord.assets.coin, "placed_ravaged": placed_ravage}


# --- Forage (4.5.4) ---------------------------------------------------------

def h_cmd_forage(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    loc_id = lord.cylinder
    st = gs.locales[loc_id]
    if st.ravaged_side is not None:
        raise IllegalAction("ravaged", "Ravage blocks Forage (4.5.4)")
    info = sd.locale(loc_id)
    friendly = actions.is_friendly_locale(gs, loc_id, lord.side)
    is_sh = info.get("is_stronghold") and not st.ruins
    gardens = info.get("gardens") and info["type"] in ("town", "city")
    # Besieged by >= Size enemy Lords blocks Forage (4.5.4), except Gardens.
    size = {"fort": 1, "town": 2, "city": 3}.get(info["type"], 0)
    heavily_besieged = is_sh and _enemy_lords_at(gs, loc_id, lord.side) >= size and size > 0
    if heavily_besieged and not (friendly and gardens):
        raise IllegalAction("forage_besieged", "a Lord Besieged by >= the Stronghold's Size may not Forage (4.5.4)")
    auto = False
    if friendly and gardens:
        auto = True  # Gardens: auto even if Besieged (4.5.4)
    elif friendly and is_sh and not heavily_besieged and not lord.besieged:
        auto = True
    if auto:
        added = True
        roll = None
    else:
        roll = roller.d6()
        thresh = 3
        if lord.id == "alp_arslan" and gs.meta.notes.get("moustache_campaign"):
            thresh = 1  # S9 Alp Arslan's Moustache: -2 to Forage (penalty) this Campaign
        added = roll <= thresh
    if added:
        lord.assets.provender = min(lord.assets.provender + 1, 8)
    spend_actions(gs, 1)
    return {"ok": True, "action": "cmd_forage", "lord": lord.id, "auto": auto, "roll": roll,
            "provender_added": added, "provender": lord.assets.provender}


# --- Ravage (4.5.5) ---------------------------------------------------------

_THEMATA_PROT = {"tagmata": (1, 3), "infantry": (1, 3), "militia": (1, 1), "turkic_horse": (1, 3)}


def _ravage_succeeds_effects(gs: GameState, lord: LordState, loc_id: str) -> None:
    gs.locales[loc_id].ravaged_side = lord.side  # opposite of the Locale's (enemy) Allegiance
    lord.assets.provender = min(lord.assets.provender + 1, 8)
    info = sd.locale(loc_id)
    if info.get("is_stronghold") and not gs.locales[loc_id].ruins:
        lord.assets.loot = min(lord.assets.loot + 1, 8)
    gs.meta.vp = scenarios.score(gs)


def h_cmd_ravage(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if lord.besieged:
        raise IllegalAction("besieged", "a Besieged Lord may not Ravage (4.5.5)")
    loc_id = action.get("target", lord.cylinder)
    if loc_id not in gs.locales:
        raise IllegalAction("bad_locale", "unknown Ravage target")
    if loc_id != lord.cylinder:
        # S3 Steppe Raiders: Ravage an ADJACENT Locale (incl. across a Pass) with
        # no enemy Lord, if this Lord has the Capability and Turkic Horse.
        if not (capabilities.lord_has(gs, lord.id, "Steppe Raiders") and lord.forces.get("turkic_horse", 0) > 0):
            raise IllegalAction("not_steppe_raider", "only a Steppe Raider with Turkic Horse may Ravage an adjacent Locale (S3)")
        if not gmap.is_adjacent(lord.cylinder, loc_id):
            raise IllegalAction("not_adjacent", "Steppe Raiders Ravage targets an adjacent Locale (S3)")
        if any(_l.mustered and _l.cylinder == loc_id and _l.side != lord.side for _l in gs.lords.values()):
            raise IllegalAction("enemy_lord_present", "cannot Steppe-Raid a Locale containing an enemy Lord (S3)")
    st = gs.locales[loc_id]
    if actions.current_allegiance(gs, loc_id) == lord.side:
        raise IllegalAction("not_enemy", "Ravage targets an Enemy Locale (4.5.5)")
    if st.ravaged_side is not None:
        raise IllegalAction("already_ravaged", "Locale is already Ravaged (4.5.5)")
    lord.moved_fought = True  # the Ravaging Lord acted
    for _l in gs.lords.values():  # 4.5.5: mark all Lords of both sides at the Locale Moved/Fought
        if _l.mustered and _l.cylinder == loc_id:
            _l.moved_fought = True
    if lord.side == "roman":
        _ravage_succeeds_effects(gs, lord, loc_id)
        spend_actions(gs, 1)
        return {"ok": True, "action": "cmd_ravage", "lord": lord.id, "success": True, "cost": 1}
    # Seljuk: 1 or 2 actions
    n = int(action.get("actions", 2))
    if n not in (1, 2):
        raise IllegalAction("bad_actions", "Seljuk Ravage uses 1 or 2 Command actions (4.5.5)")
    if n > gs.meta.actions_remaining:
        raise IllegalAction("insufficient_actions", "not enough Command actions for this Ravage")
    in_empire = sd.locale(loc_id)["allegiance"] == "roman"
    thema = sd.locale(loc_id)["thema"]
    can_defend = (n == 1 and in_empire and thema and bool(gs.themata.get(thema)))
    if not can_defend:
        _ravage_succeeds_effects(gs, lord, loc_id)
        spend_actions(gs, n)
        return {"ok": True, "action": "cmd_ravage", "lord": lord.id, "success": True, "cost": n}
    # 1-action Seljuk Ravage in the Roman Empire: Roman MAY defend with a Themata.
    gs.meta.actions_remaining -= n  # the action is spent now; resolution is owed by Roman
    gs.meta.pending.append({
        "type": "ravage_defence", "locale": loc_id, "thema": thema, "ravager": lord.id,
        "options": [{"index": i, "unit": m.unit} for i, m in enumerate(gs.themata[thema])],
    })
    return {"ok": True, "action": "cmd_ravage", "lord": lord.id, "pending": "ravage_defence",
            "thema": thema, "_owed_by": "roman"}


def h_resolve_ravage_defence(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    pend = next((p for p in gs.meta.pending if p["type"] == "ravage_defence"), None)
    if pend is None:
        raise IllegalAction("no_pending", "no Ravage to defend")
    loc_id = pend["locale"]
    thema = pend["thema"]
    lord = gs.lords[pend["ravager"]]
    defend_index = action.get("defend_with")  # None = Roman declines
    if defend_index is None:
        _ravage_succeeds_effects(gs, lord, loc_id)
        result = {"defended": False, "success": True}
    else:
        box = gs.themata[thema]
        if defend_index < 0 or defend_index >= len(box):
            raise IllegalAction("bad_themata", "no such defending Themata")
        marker = box[defend_index]
        lo, hi = _THEMATA_PROT.get(marker.unit, (1, 1))
        roll = roller.d6()
        protected = lo <= roll <= hi
        if protected:
            result = {"defended": True, "roll": roll, "unit": marker.unit, "success": False}  # Ravage fails
        else:
            box.pop(defend_index)  # Themata eliminated from play
            _ravage_succeeds_effects(gs, lord, loc_id)
            result = {"defended": True, "roll": roll, "unit": marker.unit, "themata_lost": True, "success": True}
    gs.meta.pending.remove(pend)
    if gs.meta.actions_remaining <= 0:
        _after_card(gs)
    return {"ok": True, "action": "resolve_ravage_defence", **result}


# --- Supply (4.4) -----------------------------------------------------------

def _available_carts(gs: GameState, lord: LordState) -> int:
    carts = lord.assets.carts
    for other in gs.lords.values():  # Sharing co-located Carts (1.5.2)
        if other is not lord and other.side == lord.side and other.cylinder == lord.cylinder and on_map(other):
            carts += other.assets.carts
    return carts


def _blocks_supply(gs: GameState, locale_id: str, side: str, origin: str) -> bool:
    """A Supply Route may not pass through a Locale with an Enemy Lord or Enemy
    Stronghold unless it is Besieged or Bypassed (4.4.1). The origin Locale is
    exempt (the Lord is there)."""
    if locale_id == origin:
        return False
    st = gs.locales[locale_id]
    if st.siege_markers > 0 or st.bypass:
        return False
    if _enemy_lords_at(gs, locale_id, side) > 0:
        return True
    loc = sd.locale(locale_id)
    if loc.get("is_stronghold") and actions.current_allegiance(gs, locale_id) == _enemy(side) and not st.ruins:
        return True
    return False


_MARWANID_LOCALES = ("amid", "mayyafariqin")


def _supply_seats(gs: GameState, lord: LordState) -> list[str]:
    """Every un-Ruined Stronghold Seat this Lord may use as a Supply Source,
    respecting the one-Marwanid-Seat-per-Command-card lock (3.5.1.1)."""
    seats = [s for s in sd.lord(lord.id).get("seats", []) if not gs.locales[s].ruins]
    if lord.id == "artuk_beg" and capabilities.lord_has(gs, "artuk_beg", "Artukid Legacy"):
        for s in _MARWANID_LOCALES:                                          # S10
            if not gs.locales[s].ruins and s not in seats:
                seats.append(s)
    if lord.side == "seljuk":
        lock = gs.meta.notes.get("marwanid_supply_lock")
        for s in gs.meta.notes.get("marwanid_seats", []):
            if gs.locales[s].ruins or s in seats:
                continue
            if lock is not None and s in _MARWANID_LOCALES and s != lock:
                continue  # another Marwanid Seat is already this card's Supply Source
            seats.append(s)
    return seats


def _supply_route_costs(gs: GameState, lord: LordState) -> dict[str, int]:
    """Cheapest Cart cost (Road 1, Pass 2) from the Lord to EACH of his available
    Seats (4.4.1). A Seat he occupies costs 0."""
    seats = _supply_seats(gs, lord)
    if not seats:
        return {}
    import heapq
    origin = lord.cylinder
    best = {origin: 0}
    pq = [(0, origin)]
    while pq:
        cost, loc = heapq.heappop(pq)
        if cost > best.get(loc, 1 << 30):
            continue
        for edge in gmap.ways_from(loc):
            nxt = edge["to"]
            if edge["type"] == "pass" and _passes_blocked(gs):
                continue  # Unpredictable Weather: no Pass Supply
            if _blocks_supply(gs, nxt, lord.side, origin):
                continue
            step = 2 if edge["type"] == "pass" else 1
            nc = cost + step
            if nc < best.get(nxt, 1 << 30):
                best[nxt] = nc
                heapq.heappush(pq, (nc, nxt))
    return {s: best[s] for s in seats if s in best}


def _supply_plan(gs: GameState, lord: LordState) -> tuple[int, list[str], int]:
    """Maximum-Provender Supply plan for one Command action (4.4.2 + the 4.4.1
    Important box): draw one Provender per Stronghold Seat used, each Seat funded
    by its OWN Carts along its Route ("each Cart is committed to a single Way per
    action" -- Carts are NOT shared across Routes). Pick the most Seats fundable
    within the Lord's Cart budget and his 8-Provender room; at most one Marwanid
    Seat per card (3.5.1.1). Returns (provender_gain, seats_used, total_cart_cost).
    """
    costs = _supply_route_costs(gs, lord)
    if not costs:
        return 0, [], 0
    budget = _available_carts(gs, lord)
    room = max(0, 8 - lord.assets.provender)
    marwanid = gs.meta.notes.get("marwanid_supply_lock")
    used: list[str] = []
    total = 0
    for seat, c in sorted(costs.items(), key=lambda kv: kv[1]):  # cheapest first
        if len(used) >= room or c > budget:
            break  # ascending cost: nothing cheaper remains affordable
        if seat in _MARWANID_LOCALES and marwanid not in (None, seat):
            continue  # one Marwanid Seat per card already chosen
        used.append(seat)
        budget -= c
        total += c
        if seat in _MARWANID_LOCALES:
            marwanid = seat
    return len(used), used, total


def _min_supply_route(gs: GameState, lord: LordState) -> tuple[int | None, str | None]:
    """Cheapest Cart-cost Route (Road 1, Pass 2) from the Lord to any of his
    un-Ruined Seats, with the chosen Seat. 3.5.1.1: only one Marwanid Seat may be
    a Supply Source per Command card -- if one is already locked this card, the
    other Marwanid Seat is unavailable."""
    seats = [s for s in sd.lord(lord.id).get("seats", []) if not gs.locales[s].ruins]
    if lord.id == "artuk_beg" and capabilities.lord_has(gs, "artuk_beg", "Artukid Legacy"):
        seats += [s for s in _MARWANID_LOCALES if not gs.locales[s].ruins]  # S10
    if lord.side == "seljuk":
        lock = gs.meta.notes.get("marwanid_supply_lock")
        for s in gs.meta.notes.get("marwanid_seats", []):
            if gs.locales[s].ruins or s in seats:
                continue
            if lock is not None and s in _MARWANID_LOCALES and s != lock:
                continue  # another Marwanid Seat is already this card's Supply Source
            seats.append(s)
    if not seats:
        return None, None
    origin = lord.cylinder
    if origin in seats:
        return 0, origin
    import heapq
    best = {origin: 0}
    pq = [(0, origin)]
    while pq:
        cost, loc = heapq.heappop(pq)
        if loc in seats:
            return cost, loc
        if cost > best.get(loc, 1 << 30):
            continue
        for edge in gmap.ways_from(loc):
            nxt = edge["to"]
            if edge["type"] == "pass" and _passes_blocked(gs):
                continue  # Unpredictable Weather: no Pass Supply
            if _blocks_supply(gs, nxt, lord.side, origin):
                continue
            step = 2 if edge["type"] == "pass" else 1
            nc = cost + step
            if nc < best.get(nxt, 1 << 30):
                best[nxt] = nc
                heapq.heappush(pq, (nc, nxt))
    reachable = [(best[s], s) for s in seats if s in best]
    if not reachable:
        return None, None
    reachable.sort()
    return reachable[0]


def _min_supply_cost(gs: GameState, lord: LordState) -> int | None:
    return _min_supply_route(gs, lord)[0]


def h_cmd_supply(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if lord.besieged:
        raise IllegalAction("besieged", "a Besieged Lord may not Supply (4.4)")
    gain, seats, total = _supply_plan(gs, lord)
    if not seats:
        if not _supply_route_costs(gs, lord):
            raise IllegalAction("no_supply_route", "no Route to an un-Ruined Seat (4.4.1)")
        if lord.assets.provender >= 8:
            raise IllegalAction("provender_full", "already at the 8-Provender cap (1.7.3)")
        raise IllegalAction("insufficient_carts", "no Cart budget for any Route (4.4.1)")
    lord.assets.provender = min(8, lord.assets.provender + gain)
    for s in seats:
        if s in _MARWANID_LOCALES:
            gs.meta.notes["marwanid_supply_lock"] = s  # 3.5.1.1: one Marwanid Source per card
    spend_actions(gs, 1)
    return {"ok": True, "action": "cmd_supply", "lord": lord.id, "route_cost": total,
            "seats": seats, "seat": seats[0], "provender_gained": gain,
            "provender": lord.assets.provender}


# --- Recruit (4.5.7) --------------------------------------------------------

def h_cmd_recruit(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if lord.side != "roman" or not actions.is_commander(gs, lord.id):
        raise IllegalAction("not_roman_commander", "only the Roman Commander may Recruit (4.5.7)")
    if lord.besieged:
        raise IllegalAction("besieged", "a Besieged Lord may not Recruit (4.5.7)")
    thema = sd.locale(lord.cylinder)["thema"]
    if not thema or not gs.themata.get(thema):
        raise IllegalAction("no_themata_here", "no available Themata in this Lord's Thema (4.5.7)")
    idx = int(action.get("marker_index", 0))
    box = gs.themata[thema]
    if idx < 0 or idx >= len(box):
        raise IllegalAction("bad_themata_index", "no such Themata marker")
    marker = box.pop(idx)
    marker.home_thema = thema
    lord.themata_on_mat.append(marker)
    spend_actions(gs, 1)
    return {"ok": True, "action": "cmd_recruit", "lord": lord.id, "thema": thema,
            "marker": {"unit": marker.unit, "symbols": marker.symbols}}


# === March (4.3) and Approach (4.3.4) / Besiege-Bypass (4.3.5) ===============

def _enemy_lord_ids_at(gs: GameState, locale_id: str, side: str) -> list[str]:
    return [lid for lid, l in gs.lords.items()
            if l.mustered and l.cylinder == locale_id and l.side == _enemy(side) and not l.besieged]


def _all_turkic(lords: list[LordState]) -> bool:
    for l in lords:
        if not l.forces:
            return False
        if any(u != "turkic_horse" and n > 0 for u, n in l.forces.items()):
            return False
    return True


def group_laden(gs: GameState, lords: list[LordState]) -> bool:
    """4.3.2: a group is Laden if it carries any Loot, or more Provender than
    Carts (shared across the group)."""
    loot = sum(l.assets.loot for l in lords)
    prov = sum(l.assets.provender for l in lords)
    carts = sum(l.assets.carts for l in lords)
    return loot > 0 or prov > carts


def _over_laden(gs: GameState, lords: list[LordState]) -> bool:
    prov = sum(l.assets.provender for l in lords)
    carts = sum(l.assets.carts for l in lords)
    return prov > 2 * carts  # 4.3.2: more than two Provender per Cart cannot move


def _passes_blocked(gs: GameState) -> bool:
    """R17/S17 Unpredictable Weather: Passes blocked for Supply/March/Avoid/Retreat."""
    return bool(gs.meta.notes.get("weather_pass_block"))


def _way_between(origin: str, to: str, way_type: str | None):
    cands = gmap.ways_between(origin, to)
    if not cands:
        return None
    if way_type:
        for w in cands:
            if w["type"] == way_type:
                return w
        return None
    return cands[0]


def march_cost(gs: GameState, lords: list[LordState], way: dict, first_march: bool) -> int | str:
    """Action cost of a March (4.3.3). Returns 'whole_card' for Holding-Box Ways."""
    if way["whole_command_card"]:
        return "whole_card"
    laden = group_laden(gs, lords)
    cost = 2 if laden else 1
    if first_march and _all_turkic(lords):
        cost = max(0, cost - 1)  # Turkic-Horse first March of the card (-1)
    if way["type"] == "pass":
        cost += 1
    return cost


def _marching_group(gs: GameState, lord: LordState, co_marchers: list[str]) -> list[LordState]:
    """The set of Lords that move together (4.3.1 Group March + 4.1.3 stack)."""
    group = [lord]
    # A Lieutenant brings his Lower Lord; a Lower Lord cannot be the active card.
    if lord.lower_lord and lord.lower_lord in gs.lords:
        group.append(gs.lords[lord.lower_lord])
    if co_marchers:
        # S7 Trusted Commander: a non-Commander Lord may March with 1 (only) other
        # Seljuk Lord (for March only; no Commander status).
        trusted = capabilities.lord_has(gs, lord.id, "Trusted Commander")
        if not actions.is_commander(gs, lord.id) and not trusted:
            raise IllegalAction("not_commander_group", "only a Commander may lead a Group March (4.3.1)")
        if trusted and not actions.is_commander(gs, lord.id) and len(co_marchers) > 1:
            raise IllegalAction("trusted_commander_one_only",
                                "Trusted Commander may March with 1 (only) other Seljuk Lord (S7)")
        for cid in co_marchers:
            other = gs.lords.get(cid)
            if other is None or other.side != lord.side or not on_map(other) or other.cylinder != lord.cylinder:
                raise IllegalAction("bad_co_marcher", f"{cid} cannot Group-March with {lord.id}")
            if other.besieged:
                raise IllegalAction("besieged", f"{cid} is Besieged")
            group.append(other)
            if other.lower_lord and other.lower_lord in gs.lords:
                group.append(gs.lords[other.lower_lord])
    return group


def h_cmd_march(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if lord.besieged:
        raise IllegalAction("besieged", "a Besieged Lord may only Sally/Pass/Forage (4.2.1)")
    to = action.get("to")
    if to not in gs.locales:
        raise IllegalAction("bad_destination", "unknown destination Locale")
    if _enemy_lord_ids_at(gs, to, lord.side) and not gs.locales[to].bypass:
        _peace_gate(gs, lord)  # S13: an Approach this Season requires 1 Coin
    way = _way_between(lord.cylinder, to, action.get("way_type"))
    if way is None:
        raise IllegalAction("no_way", f"no Way from {lord.cylinder} to {to}")
    if way["type"] == "pass" and _passes_blocked(gs):
        raise IllegalAction("passes_blocked", "Passes cannot be used to March (Unpredictable Weather)")
    group = _marching_group(gs, lord, action.get("group", []))
    if _over_laden(gs, group):
        raise IllegalAction("over_laden", "group carries more than two Provender per Cart (discard to March, 4.3.2)")
    # Holding-Box rule: only the owning side may enter its own Box; no enemy box.
    dest_info = sd.locale(to)
    if dest_info["type"] == "holding_box" and dest_info["allegiance"] != lord.side:
        raise IllegalAction("enemy_holding_box", "no Lord may enter an Enemy Holding Box (1.3.1)")
    first_march = not lord.flags.get("first_march_used")
    cost = march_cost(gs, group, way, first_march)
    if cost == "whole_card":
        cost = gs.meta.actions_remaining
    elif (way["type"] == "pass" and len(group) == 1 and not lord.lower_lord and not lord.lieutenant_of
          and capabilities.lord_has(gs, lord.id, "Mules") and not lord.flags.get("mules_used_this_card")):
        cost = min(cost, 1)  # Mules (R24/S25): first Pass March = 1 Command even if Laden
        lord.flags["mules_used_this_card"] = True
    if cost > gs.meta.actions_remaining:
        raise IllegalAction("insufficient_actions", f"March costs {cost}, only {gs.meta.actions_remaining} left")
    # Move the group.
    march_from = lord.cylinder  # SMOKE-006: approach breadcrumb (origin Locale)
    origins = {g.cylinder for g in group}
    for g in group:
        g.cylinder = to
        g.moved_fought = True
        g.bypassed = False  # SMOKE-005: leaving a Locale ends any Bypass there
    # Year of Treacherous Ambition objective: latch when a Seljuk Lord reaches
    # Ikonion / Western Anatolia (scored at end; see scenarios._scenario_special_vp).
    if gs.meta.scenario == "year_of_treacherous_ambition" and lord.side == "seljuk":
        if to == "ikonion":
            gs.meta.notes["reached_ikonion"] = True
        elif to == "western_anatolia":
            gs.meta.notes["reached_western_anatolia"] = True
    for origin in origins:
        if origin != to:
            _refresh_invest(gs, origin)  # clear stale Siege/Bypass if besiegers left
    lord.flags["first_march_used"] = True
    gs.meta.actions_remaining -= cost
    res = {"ok": True, "action": "cmd_march", "lord": lord.id, "to": to,
           "way": way["type"], "cost": cost, "group": [g.id for g in group]}
    arrival = _resolve_arrival(gs, group, to, from_locale=march_from, unstoppable=action.get("unstoppable", False))
    res.update(arrival)
    if not arrival.get("pending") and gs.meta.actions_remaining <= 0:
        _after_card(gs)
    return res


def _refresh_invest(gs: GameState, locale: str) -> None:
    """SMOKE-005 (4.3.5 / 4.4.1): "Whenever a Besieged or Bypassed Stronghold
    becomes free of Enemy Lords in the Locale, remove all Siege and Bypass
    markers there, then return all Themata Service Markers to their Thema box."
    Without this the Bypass marker goes stale after the bypassing Lords leave,
    and _resolve_arrival keeps suppressing the Approach (4.3.4) of a later
    un-bypassed enemy Lord (and blocks re-Besiege)."""
    st = gs.locales[locale]
    if st.siege_markers == 0 and not st.bypass:
        return
    if not sd.locale(locale).get("is_stronghold"):
        return
    alleg = actions.current_allegiance(gs, locale)
    # "Enemy Lords" = Lords of the side opposing the Stronghold (its besiegers /
    # bypassers), which are always outside; a withdrawn defender is same-side.
    if any(l.mustered and l.cylinder == locale and l.side != alleg for l in gs.lords.values()):
        return
    st.siege_markers = 0
    st.bypass = False
    # The Stronghold is no longer invested: any Lord who Withdrew inside is now
    # free (SMOKE-007 / Inferno advisory #2 Door B: a stale `besieged` flag would
    # otherwise persist and corrupt Sally/March/Feed legality forever).
    for l in gs.lords.values():
        if l.mustered and l.cylinder == locale and l.besieged:
            l.besieged = False
    for marker in st.themata_defending:
        home = marker.home_thema
        if home and home in gs.themata:
            marker.home_thema = None
            gs.themata[home].append(marker)
    st.themata_defending = []


def _resolve_arrival(gs: GameState, group: list[LordState], to: str,
                     from_locale: str | None = None, unstoppable: bool = False) -> dict[str, Any]:
    """After a March: Approach (enemy Lords present) or Besiege/Bypass (enemy
    Stronghold, no enemy Lords outside) — both as pending sub-decisions."""
    side = group[0].side
    enemy_lords = _enemy_lord_ids_at(gs, to, side)
    if gs.locales[to].bypass:
        enemy_lords = []  # already Bypassing this Locale
    if enemy_lords:
        gs.meta.pending.append({
            "type": "approach_response", "locale": to, "attackers": [g.id for g in group],
            "defenders": enemy_lords, "_owed_by": _enemy(side), "from": from_locale,
        })
        return {"pending": "approach_response", "defenders": enemy_lords}
    enemy_sh = _is_stronghold(gs, to) and actions.current_allegiance(gs, to) == _enemy(side)
    if enemy_sh and not gs.locales[to].bypass and gs.locales[to].siege_markers == 0:
        lead = group[0]
        # S18 Unstoppable Turkmen: Bypass without stopping (no Besiege/Bypass
        # decision) -- place the Bypass marker and continue, once per Command.
        if (unstoppable and capabilities.lord_has(gs, lead.id, "Unstoppable Turkmen")
                and not lead.flags.get("unstoppable_used_this_card")):
            gs.locales[to].bypass = True
            for g in group:
                g.bypassed = True
            lead.flags["unstoppable_used_this_card"] = True
            return {"bypassed_without_stopping": to}
        gs.meta.pending.append({
            "type": "besiege_or_bypass", "locale": to, "lords": [g.id for g in group], "_owed_by": side,
        })
        return {"pending": "besiege_or_bypass"}
    return {}


def _award_avoid_spoils(gs: GameState, attacker_ids: list[str], loot: int, prov: int) -> None:
    """4.3.4/4.8.3: the Approaching Lords receive and divide Assets a Lord
    discarded to Avoid Battle (round-robin, 8-cap)."""
    atts = [gs.lords[a] for a in attacker_ids if a in gs.lords and gs.lords[a].mustered]
    if not atts:
        return
    i = 0
    for _ in range(loot):
        atts[i % len(atts)].assets.loot = min(8, atts[i % len(atts)].assets.loot + 1); i += 1
    for _ in range(prov):
        atts[i % len(atts)].assets.provender = min(8, atts[i % len(atts)].assets.provender + 1); i += 1


def h_respond_approach(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """4.3.4: each Inactive (defending) Lord chooses Avoid Battle, Withdraw, or
    Stand. ``choices`` maps lord_id -> {"action": "avoid"|"withdraw"|"stand",
    "to": <locale for avoid>}. Standers (if any) trigger a Battle (resolved in
    the Battle engine)."""
    pend = next((p for p in gs.meta.pending if p["type"] == "approach_response"), None)
    if pend is None:
        raise IllegalAction("no_pending", "no Approach to respond to")
    to = pend["locale"]
    choices = dict(action.get("choices", {}))
    side = gs.lords[pend["defenders"][0]].side
    att_side = gs.lords[pend["attackers"][0]].side
    ls = action.get("local_scouts")
    if ls and "R18" in gs.side_decks(att_side).held_events and ls.get("lord") in choices:
        # R18 Local Scouts: the playing side forces one Avoiding Lord to Battle/Withdraw.
        if choices[ls["lord"]].get("action") == "avoid":
            choices[ls["lord"]] = {"action": ls.get("action", "stand")}
            gs.side_decks(att_side).held_events.remove("R18")
            gs.side_decks(att_side).draw_deck.append("R18")
    standers, avoided, withdrew = [], [], []
    approach_origin = pend.get("from")  # SMOKE-006: Locale the Attackers Approached from
    # 4.3.4: Withdraw is limited to the Stronghold's Size (incl. Lords already inside).
    inside = sum(1 for l in gs.lords.values()
                 if l.mustered and l.cylinder == to and l.besieged and l.side == side)
    n_withdraw = sum(1 for did in pend["defenders"]
                     if choices.get(did, {}).get("action") == "withdraw")
    if inside + n_withdraw > _stronghold_size(gs, to):
        raise IllegalAction("stronghold_full",
                            f"Stronghold Size {_stronghold_size(gs, to)} cannot hold {inside + n_withdraw} Lords (4.3.4)")
    for did in pend["defenders"]:
        ch = choices.get(did, {"action": "stand"})
        kind = ch.get("action", "stand")
        lord = gs.lords[did]
        if kind == "avoid":
            dest = ch.get("to")
            _validate_avoid(gs, lord, to, dest, side, approach_origin)
            # 4.3.4: discard Loot and excess Provender to become Unladen; the
            # Approaching Enemy Lords receive and divide the discarded Assets.
            disc_loot = lord.assets.loot
            disc_prov = max(0, lord.assets.provender - lord.assets.carts)
            lord.assets.loot = 0
            lord.assets.provender = min(lord.assets.provender, lord.assets.carts)
            _award_avoid_spoils(gs, pend["attackers"], disc_loot, disc_prov)
            lord.cylinder = dest
            lord.moved_fought = True
            avoided.append(did)
        elif kind == "withdraw":
            _validate_withdraw(gs, lord, to)
            lord.besieged = True  # inside the Stronghold at `to`
            withdrew.append(did)
        else:
            standers.append(did)
    gs.meta.pending.remove(pend)
    if standers:
        from . import battle
        attackers = list(pend["attackers"])
        att_side = gs.lords[attackers[0]].side
        # Relief Sally (4.8.1): friendly Besieged Lords at this Locale join the
        # relief Attack for no extra Command actions. (Rearguard rows and the
        # Siegeworks-vs-Sallying-only nuance are a documented approximation.)
        sallying = [lid for lid, l in gs.lords.items()
                    if l.mustered and l.cylinder == to and l.side == att_side and l.besieged]
        attackers += sallying
        res = battle.begin_battle(gs, attackers, standers, to,
                                  scripted=action.get("battle_decisions"),
                                  events=action.get("battle_events"),
                                  sallying=set(sallying),
                                  siegeworks=gs.locales[to].siege_markers if sallying else 0,
                                  approach_origin=approach_origin)
        if sallying:
            res["relief_sally"] = list(sallying)
            for lid in sallying:                       # Sallying Lords withdraw back inside
                if lid in gs.lords and gs.lords[lid].mustered:
                    gs.lords[lid].besieged = True
                    gs.lords[lid].cylinder = to
            if res.get("winner") == "defender" and gs.locales[to].siege_markers > 0:
                gs.locales[to].siege_markers = 1       # reduce Siege markers to one (4.8.1)
        # A Battle ends the active Lord's card (4.8.6): skip remaining actions.
        if gs.meta.phase == "campaign":
            gs.meta.actions_remaining = 0
            _after_card(gs)
        return {"ok": True, "action": "respond_approach", "battle": res}
    # No defenders left to fight -> the attacker may now Besiege/Bypass if a
    # Stronghold remains, else the card continues.
    arrival = _resolve_arrival(gs, [gs.lords[a] for a in pend["attackers"]], to)
    if not arrival.get("pending") and gs.meta.actions_remaining <= 0:
        _after_card(gs)
    return {"ok": True, "action": "respond_approach", "avoided": avoided,
            "withdrew": withdrew, "standers": standers, **arrival}


def _validate_avoid(gs: GameState, lord: LordState, battle_loc: str, dest: str, side: str,
                    approach_origin: str | None = None) -> None:
    if dest not in gs.locales or not gmap.is_adjacent(battle_loc, dest):
        raise IllegalAction("bad_avoid", "Avoid Battle moves to an adjacent Locale (4.3.4)")
    if approach_origin is not None and dest == approach_origin:
        raise IllegalAction("avoid_across_approach", "may not Avoid across the Way the Enemy Approached on (4.3.4)")
    if _passes_blocked(gs) and all(w["type"] == "pass" for w in gmap.ways_between(battle_loc, dest)):
        raise IllegalAction("passes_blocked", "Passes cannot be used to Avoid Battle (Unpredictable Weather)")
    if _enemy_lord_ids_at(gs, dest, side):
        raise IllegalAction("avoid_into_enemy", "may not Avoid into a Locale with an Unbesieged Enemy Lord (4.3.4)")


def _validate_withdraw(gs: GameState, lord: LordState, battle_loc: str) -> None:
    info = sd.locale(battle_loc)
    if not info.get("is_stronghold") or gs.locales[battle_loc].ruins:
        raise IllegalAction("no_stronghold", "Withdraw requires a Friendly Stronghold here (4.3.4)")
    if actions.current_allegiance(gs, battle_loc) != lord.side:
        raise IllegalAction("not_friendly_stronghold", "Withdraw requires a Friendly Stronghold (4.3.4)")
    if battle_loc == "aleppo":
        raise IllegalAction("no_withdraw_aleppo", "no Lord may Withdraw inside Aleppo (1.3.1)")


def h_besiege_bypass(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    pend = next((p for p in gs.meta.pending if p["type"] == "besiege_or_bypass"), None)
    if pend is None:
        raise IllegalAction("no_pending", "no Besiege/Bypass to resolve")
    to = pend["locale"]
    side = gs.lords[pend["lords"][0]].side
    choice = action.get("choice")
    gs.meta.pending.remove(pend)
    if choice == "besiege":
        lords_here = [l for l in gs.lords.values() if l.mustered and l.cylinder == to]
        if (action.get("surprise") and side == "seljuk" and "S1" in gs.seljuk.held_events
                and sd.locale(to)["type"] in ("fort", "town") and len(lords_here) == 1):
            # S1 Surprise: place 2 Siege markers (not 1), then immediately Storm.
            gs.locales[to].siege_markers = 2
            gs.seljuk.held_events.remove("S1"); gs.seljuk.draw_deck.append("S1")
            from . import battle
            res = battle.resolve_storm(gs, [pend["lords"][0]], to,
                                       battle.DecisionContext(action.get("storm_decisions")), roller)
            gs.meta.actions_remaining = 0
            _after_card(gs)
            return {"ok": True, "action": "besiege_surprise", "locale": to, "storm": res}
        gs.locales[to].siege_markers = max(1, gs.locales[to].siege_markers)  # place first Siege marker (4.3.5)
        gs.meta.actions_remaining = 0  # Besieging ends the card
        if _needs_themata_assignment(gs, to, side):
            gs.meta.pending.append({"type": "assign_themata_defenders", "locale": to, "_owed_by": "roman"})
            return {"ok": True, "action": "besiege", "locale": to, "pending": "assign_themata_defenders"}
        _after_card(gs)
        return {"ok": True, "action": "besiege", "locale": to}
    elif choice == "bypass":
        gs.locales[to].bypass = True
        for lid in pend["lords"]:
            gs.lords[lid].bypassed = True
        if gs.meta.actions_remaining <= 0:
            _after_card(gs)
        return {"ok": True, "action": "bypass", "locale": to}
    raise IllegalAction("bad_choice", "choose 'besiege' or 'bypass' (4.3.5)")


# === Siege (4.5.1) and Themata-defender assignment (4.3.5) ==================

def _stronghold_size(gs: GameState, loc: str) -> int:
    """Stronghold Size / Lord capacity: fort=1, town=2, city=3 (R1 Fort = 1)."""
    info = sd.locale(loc)
    if info.get("is_stronghold") and not gs.locales[loc].ruins:
        return {"fort": 1, "town": 2, "city": 3}.get(info["type"], 0)
    return 1 if gs.locales[loc].fort_marker else 0


def _is_stronghold(gs: GameState, loc: str) -> bool:
    """A Locale defended as a Stronghold: its printed Stronghold (un-Ruined) OR a
    Fort marker from R1 Imperial Fortress Construction."""
    info = sd.locale(loc)
    st = gs.locales[loc]
    return bool((info.get("is_stronghold") and not st.ruins) or st.fort_marker)


def h_cmd_fort(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """R1 Imperial Fortress Construction: a Command action -- place a Fort marker
    on an unfortified Locale (including Ruined) in the Roman Empire (max 2)."""
    lord = _require(action.get("lord"), gs)
    if lord.side != "roman" or not capabilities.lord_has(gs, lord.id, "Imperial Fortress Construction"):
        raise IllegalAction("no_fort_capability", "only a Lord with Imperial Fortress Construction may build a Fort (R1)")
    target = action.get("target")
    if target not in gs.locales:
        raise IllegalAction("bad_locale", "unknown Fort target")
    if sum(1 for l in gs.locales.values() if l.fort_marker) >= 2:
        raise IllegalAction("no_fort_markers", "both Fort markers are already on the map (R1)")
    info = sd.locale(target)
    st = gs.locales[target]
    if info["allegiance"] != "roman":
        raise IllegalAction("not_roman_empire", "a Fort is built in the Roman Empire (R1)")
    if (info.get("is_stronghold") and not st.ruins) or st.fort_marker:
        raise IllegalAction("already_fortified", "Locale is already fortified (R1)")
    st.fort_marker = True
    if st.ruins and (st.ruins_color or "seljuk") == "seljuk":
        st.ruins = False
        st.ruins_color = None  # a Seljuk Ruins marker is removed when a Fort is placed
    gs.meta.vp = scenarios.score(gs)
    spend_actions(gs, 1)
    return {"ok": True, "action": "cmd_fort", "locale": target}


def h_cmd_take_gift_coin(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """S13 Gifts Exchanged: during a Lord's Command, take 1 Coin from the card
    onto an Unbesieged Lord (each side at most 2 of the 4 Coins). Free action."""
    lord = _require(action.get("lord"), gs)
    if gs.meta.notes.get("gifts_coins", 0) <= 0:
        raise IllegalAction("no_gift_coins", "no Coins left on Gifts Exchanged (S13)")
    if lord.besieged:
        raise IllegalAction("besieged", "the Gifts Coin goes on an Unbesieged Lord (S13)")
    taken = gs.meta.notes.setdefault("gifts_taken", {"seljuk": 0, "roman": 0})
    if taken.get(lord.side, 0) >= 2:
        raise IllegalAction("gift_limit", "each side may take at most 2 Coins (S13)")
    lord.assets.coin = min(8, lord.assets.coin + 1)
    gs.meta.notes["gifts_coins"] -= 1
    taken[lord.side] = taken.get(lord.side, 0) + 1
    return {"ok": True, "action": "cmd_take_gift_coin", "lord": lord.id,
            "gifts_coins": gs.meta.notes["gifts_coins"]}


def _peace_gate(gs: GameState, lord: LordState) -> None:
    """S13 Peace Offering: this Season a Lord may not Approach/Storm/Siege unless
    he pays 1 Coin that Command card (from himself, or Alp Arslan if Unbesieged)."""
    if not gs.meta.notes.get("peace_offering_season") or lord.flags.get("peace_paid_this_card"):
        return
    aa = gs.lords.get("alp_arslan")
    if lord.assets.coin > 0:
        lord.assets.coin -= 1
    elif aa is not None and on_map(aa) and not aa.besieged and aa.assets.coin > 0:
        aa.assets.coin -= 1
    else:
        raise IllegalAction("peace_offering_coin", "must pay 1 Coin to Approach/Storm/Siege this Season (S13)")
    lord.flags["peace_paid_this_card"] = True


def _peace_can_pay(gs: GameState, lord: LordState) -> bool:
    if not gs.meta.notes.get("peace_offering_season") or lord.flags.get("peace_paid_this_card"):
        return True
    aa = gs.lords.get("alp_arslan")
    return lord.assets.coin > 0 or (aa is not None and on_map(aa) and not aa.besieged and aa.assets.coin > 0)


def _besieging(gs: GameState, lord: LordState) -> bool:
    return on_map(lord) and not lord.besieged and gs.locales[lord.cylinder].siege_markers > 0


def _besieged_enemy_inside(gs: GameState, locale: str, side: str) -> bool:
    return any(l.mustered and l.cylinder == locale and l.side == _enemy(side) and l.besieged
               for l in gs.lords.values())


def h_cmd_siege(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """4.5.1: a Besieging Lord uses the entire card to roll for Surrender and/or
    add a Siege marker (Siegeworks)."""
    lord = _require(action.get("lord"), gs)
    if not _besieging(gs, lord):
        raise IllegalAction("not_besieging", "only a Besieging Lord may Siege (4.5.1)")
    _peace_gate(gs, lord)  # S13 Peace Offering coin-gate
    loc_id = lord.cylinder
    from . import battle
    info = sd.locale(loc_id)
    size = battle._value(loc_id)
    siege = gs.locales[loc_id].siege_markers
    result = {"ok": True, "action": "cmd_siege", "lord": lord.id, "locale": loc_id}
    seized = False
    # Honors of War (R25): a Held Roman Event auto-Surrenders a Fort (no Spoils).
    if (action.get("honors_of_war") and "R25" in gs.roman.held_events
            and sd.locale(loc_id)["type"] == "fort" and lord.side == "roman"
            and not _besieged_enemy_inside(gs, loc_id, lord.side)):
        from . import battle
        result["honors_of_war"] = True
        result["conquer"] = battle.conquer(gs, loc_id, "roman")
        gs.roman.held_events.remove("R25"); gs.roman.draw_deck.append("R25")
        gs.meta.vp = scenarios.score(gs)
        lord.moved_fought = True  # 4.5.1: only the besieging Lord
        gs.meta.actions_remaining = 0
        _after_card(gs)
        return result
    if not _besieged_enemy_inside(gs, loc_id, lord.side) and action.get("roll_surrender", True):
        dice_n = sd.stronghold_profile(loc_id)["surrender_dice"]
        threshold = min(siege, 4) + (1 if gs.locales[loc_id].ravaged_side is not None else 0)
        rolls = roller.roll(dice_n)
        if capabilities.lord_has(gs, lord.id, "Brutal Reputation"):  # S21: reroll 1 Surrender die
            for i, r in enumerate(rolls):
                if r > threshold:
                    rolls[i] = roller.d6()
                    break
        seized = all(r <= threshold for r in rolls)
        result.update({"surrender_roll": rolls, "threshold": threshold, "seized": seized})
        if seized:
            # Basil Alousianos (R7*): the Roman may convert a Surrender (threshold
            # exactly 3, not 4) of a Roman Stronghold into a Bypass instead of a
            # Conquest. Pause for the Roman response.
            if (info["allegiance"] == "roman" and lord.side == "seljuk" and threshold == 3
                    and "R7" not in gs.meta.asterisks_used and "R7" in gs.roman.held_events):
                lord.moved_fought = True  # 4.5.1: only the besieging Lord
                gs.meta.actions_remaining = 0
                gs.meta.pending.append({"type": "basil_response", "locale": loc_id,
                                        "by_side": lord.side, "_owed_by": "roman"})
                result["pending"] = "basil_response"
                return result
            result["conquer"] = battle.conquer(gs, loc_id, lord.side)
            gs.meta.vp = scenarios.score(gs)
    if not seized:
        besiegers = sum(1 for l in gs.lords.values()
                        if l.mustered and l.cylinder == loc_id and l.side == lord.side and not l.besieged)
        if besiegers >= size and gs.locales[loc_id].siege_markers < 4:
            gs.locales[loc_id].siege_markers += 1
            result["siegeworks_added"] = True
    lord.moved_fought = True  # 4.5.1: only the besieging (Encamping) Lord, "not any other Lords there"
    gs.meta.actions_remaining = 0  # Siege uses the entire card (4.5.1)
    _after_card(gs)
    return result


def _needs_themata_assignment(gs: GameState, locale: str, besieging_side: str) -> bool:
    info = sd.locale(locale)
    if besieging_side != "seljuk" or info["allegiance"] != "roman":
        return False
    thema = info.get("thema")
    return bool(thema and gs.themata.get(thema)) and not gs.locales[locale].themata_defending


def h_assign_themata_defenders(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """4.3.5: when a Roman Stronghold is first Besieged, the Roman player may
    assign up to Size available Themata from its Thema as defenders."""
    pend = next((p for p in gs.meta.pending if p["type"] == "assign_themata_defenders"), None)
    if pend is None:
        raise IllegalAction("no_pending", "no Themata defenders to assign")
    loc_id = pend["locale"]
    from . import battle
    size = battle._value(loc_id)
    thema = sd.locale(loc_id)["thema"]
    box = gs.themata[thema]
    idxs = sorted(set(action.get("markers", [])), reverse=True)
    if len(idxs) > size:
        raise IllegalAction("too_many_themata", f"at most {size} Themata may defend (4.3.5)")
    chosen = []
    for i in idxs:
        if i < 0 or i >= len(box):
            raise IllegalAction("bad_themata_index", "no such Themata marker")
    for i in idxs:
        marker = box.pop(i)
        marker.home_thema = thema
        gs.locales[loc_id].themata_defending.append(marker)
        chosen.append(marker.unit)
    gs.meta.pending.remove(pend)
    if gs.meta.actions_remaining <= 0:
        _after_card(gs)
    return {"ok": True, "action": "assign_themata_defenders", "locale": loc_id, "assigned": chosen}


# === Storm (4.5.2 / 4.9.1) and Sally (4.5.3 / 4.9.2) commands ===============

def _besieging_lords_at(gs: GameState, locale: str, side: str) -> list[str]:
    active = gs.meta.active_lord
    others = [lid for lid, l in gs.lords.items()
              if l.mustered and l.cylinder == locale and l.side == side and not l.besieged and lid != active]
    return ([active] if active else []) + others


def h_cmd_encamp(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """4.3.6 ENCAMP: a Bypassing Lord uses one March action (regardless of Laden)
    to replace the Bypass marker with one Siege marker, then ends the card."""
    lord = _require(action.get("lord"), gs)
    loc = lord.cylinder
    if not (lord.bypassed and gs.locales[loc].bypass):
        raise IllegalAction("not_bypassing", "only a Bypassing Lord may Encamp (4.3.6)")
    if gs.meta.actions_remaining < 1:
        raise IllegalAction("insufficient_actions", "Encamp uses one March action (4.3.6)")
    gs.locales[loc].bypass = False
    gs.locales[loc].siege_markers = max(1, gs.locales[loc].siege_markers)
    for l in gs.lords.values():
        if l.mustered and l.cylinder == loc and l.side == lord.side and l.bypassed:
            l.bypassed = False
    lord.moved_fought = True
    gs.meta.actions_remaining = 0  # Encamp ends the card (4.3.6)
    if _needs_themata_assignment(gs, loc, lord.side):
        gs.meta.pending.append({"type": "assign_themata_defenders", "locale": loc, "_owed_by": "roman"})
        return {"ok": True, "action": "cmd_encamp", "locale": loc, "pending": "assign_themata_defenders"}
    _after_card(gs)
    return {"ok": True, "action": "cmd_encamp", "locale": loc}


def h_cmd_sortie(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """4.3.6 SORTIE: a Lord (group) inside a Bypassed Friendly Stronghold uses one
    March action to Approach the Bypassing Enemy. On loss they Withdraw/Retreat
    keeping the Bypass marker (the marker persists while the bypasser remains)."""
    lord = _require(action.get("lord"), gs)
    loc = lord.cylinder
    if not gs.locales[loc].bypass or actions.current_allegiance(gs, loc) != lord.side:
        raise IllegalAction("not_bypassed_friendly", "Sortie requires a Bypassed Friendly Stronghold (4.3.6)")
    if lord.bypassed:
        raise IllegalAction("bypasser_cannot_sortie", "the Bypassing side cannot Sortie (4.3.6)")
    enemy = [lid for lid, l in gs.lords.items()
             if l.mustered and l.cylinder == loc and l.side == _enemy(lord.side) and l.bypassed]
    if not enemy:
        raise IllegalAction("no_bypasser", "no Bypassing Enemy to Sortie against (4.3.6)")
    from . import battle
    sortie = [lord.id] + [lid for lid, l in gs.lords.items()
                          if lid != lord.id and l.mustered and l.cylinder == loc and l.side == lord.side]
    res = battle.begin_battle(gs, sortie, enemy, loc,
                              scripted=action.get("battle_decisions"),
                              events=action.get("battle_events"))
    gs.meta.actions_remaining = 0
    _after_card(gs)  # _refresh_invest clears the Bypass marker only if the bypasser is gone
    return {"ok": True, "action": "cmd_sortie", "locale": loc, "battle": res}


def h_cmd_storm(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if not _besieging(gs, lord):
        raise IllegalAction("not_besieging", "only a Besieging Lord may Storm (4.5.2)")
    if gs.locales[lord.cylinder].siege_markers <= 0:
        raise IllegalAction("no_siege", "no Siege markers to Storm with")
    from . import battle
    attackers = _besieging_lords_at(gs, lord.cylinder, lord.side)
    ctx = battle.DecisionContext(action.get("storm_decisions"))
    # R4 Sultan's Horse Is Killed: the Roman defender may play it during a Storm
    # by Alp Arslan at a Locale with >1 Siege marker to reduce the Rounds by 1.
    rounds_reduction = 0
    if (action.get("play_sultans_horse") and "R4" in gs.roman.held_events
            and "alp_arslan" in attackers and gs.locales[lord.cylinder].siege_markers > 1):
        gs.roman.held_events.remove("R4"); gs.roman.draw_deck.append("R4")
        rounds_reduction = 1
    res = battle.resolve_storm(gs, attackers, lord.cylinder, ctx, roller, rounds_reduction=rounds_reduction)
    gs.meta.actions_remaining = 0  # Storm ends the card (4.5.2)
    _after_card(gs)
    return {"ok": True, "action": "cmd_storm", "storm": res}


def h_cmd_sally(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if not lord.besieged:
        raise IllegalAction("not_besieged", "only a Besieged Lord may Sally (4.5.3)")
    from . import battle
    locale = lord.cylinder
    besiegers = [lid for lid, l in gs.lords.items()
                 if l.mustered and l.cylinder == locale and l.side == _enemy(lord.side) and not l.besieged]
    sallying = [lid for lid, l in gs.lords.items()
                if l.mustered and l.cylinder == locale and l.side == lord.side and l.besieged]
    # Active sallying Lord first.
    sallying = [lord.id] + [s for s in sallying if s != lord.id]
    ctx = battle.DecisionContext(action.get("battle_decisions"))
    res = battle.resolve_sally(gs, sallying, besiegers, locale, ctx, roller)
    gs.meta.actions_remaining = 0  # Sally ends the card (4.8.6)
    _after_card(gs)
    return {"ok": True, "action": "cmd_sally", "sally": res}


# === Loyalty Checks from Treachery (1.4) and Imperial Coffers (R14) =========

def h_resolve_loyalty(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """Resolve a Loyalty Check triggered by a revealed Treachery card (1.4.1)."""
    pend = next((p for p in gs.meta.pending if p["type"] == "loyalty_check"), None)
    if pend is None:
        raise IllegalAction("no_pending", "no Loyalty Check to resolve")
    target = action.get("target")
    if target not in pend["targets"]:
        raise IllegalAction("bad_target", f"choose one of {pend['targets']}")
    res = actions.resolve_loyalty_check(gs, target, pend["side"], roller,
                                        coins_for=int(action.get("coins_for", 0)),
                                        coins_against=int(action.get("coins_against", 0)))
    gs.meta.pending.remove(pend)
    gs.meta.actions_remaining = 0  # the Treachery card carries no Command actions
    _after_card(gs)
    return {"ok": True, "action": "resolve_loyalty", "loyalty": res}


def h_discard_imperial_coffers(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """R14 Imperial Coffers: discard during Arts of War to make a Loyalty Check
    against a Seljuk-allied Robert/Roussel adjacent to a Roman Lord (1.4.1)."""
    if "R14" not in gs.roman.capabilities_in_play:
        raise IllegalAction("no_imperial_coffers", "Imperial Coffers is not in play")
    target = action.get("target")
    tl = gs.lords.get(target)
    if target not in ("robert_crepin", "roussel_de_bailleul") or tl is None or tl.side != "seljuk" or not tl.mustered:
        raise IllegalAction("bad_target", "target must be a Mustered Seljuk-allied Robert/Roussel")
    if not any(l.side == "roman" and l.mustered and gmap.is_adjacent(l.cylinder, tl.cylinder)
               for l in gs.lords.values()):
        raise IllegalAction("no_adjacent_roman", "no Roman Lord adjacent to the target (R14)")
    gs.roman.capabilities_in_play.remove("R14")
    gs.roman.draw_deck.append("R14")
    res = actions.resolve_loyalty_check(gs, target, "roman", roller,
                                        coins_for=int(action.get("coins_for", 0)),
                                        coins_against=int(action.get("coins_against", 0)))
    return {"ok": True, "action": "discard_imperial_coffers", "loyalty": res}


def h_basil_response(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """Resolve a Basil Alousianos (R7) reaction to a Roman Stronghold Surrender."""
    pend = next((p for p in gs.meta.pending if p["type"] == "basil_response"), None)
    if pend is None:
        raise IllegalAction("no_pending", "no Basil reaction owed")
    loc_id = pend["locale"]
    from . import battle
    if action.get("play"):  # R7: replace all Siege with Bypass, place no Conquered (once per game)
        gs.locales[loc_id].siege_markers = 0
        gs.locales[loc_id].bypass = True
        gs.roman.held_events.remove("R7"); gs.roman.draw_deck.append("R7")
        gs.meta.asterisks_used.append("R7")
        out = {"basil": "bypass"}
    else:  # decline -> the Stronghold is Conquered as normal
        out = {"basil": "declined", "conquer": battle.conquer(gs, loc_id, pend["by_side"])}
    gs.meta.pending.remove(pend)
    gs.meta.vp = scenarios.score(gs)
    _after_card(gs)
    return {"ok": True, "action": "basil_response", **out}
