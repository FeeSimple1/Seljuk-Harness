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
        _set_game_over(gs, "roman"); return
    if not any(l.mustered and l.side == "roman" for l in gs.lords.values()):
        _set_game_over(gs, "seljuk"); return
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
    # 5.2: a side with no Mustered Lords during Campaign loses immediately.
    if not any(l.mustered and l.side == "seljuk" for l in gs.lords.values()):
        _set_game_over(gs, "roman"); return
    if not any(l.mustered and l.side == "roman" for l in gs.lords.values()):
        _set_game_over(gs, "seljuk"); return
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


# --- End Campaign (4.7) and Winter (4.7.6) ----------------------------------

def _set_game_over(gs: GameState, winner: str) -> None:
    gs.meta.phase = "game_over"
    gs.meta.subphase = "game_over"
    gs.meta.notes["winner"] = winner


def _end_campaign(gs: GameState) -> None:
    gs.meta.subphase = "campaign.end"
    box = gs.meta.calendar_box
    _grow(gs)       # 4.7.2 (Spring only)
    _repair(gs)     # 4.7.3
    _wastage(gs)    # 4.7.4
    _reset(gs)      # 4.7.5 (non-advance parts)
    gs.meta.vp = scenarios.score(gs)
    if box in (3, 6, 9):                # 4.7.6 Winter on the first three Autumns
        winner = _winter(gs)
        gs.meta.vp = scenarios.score(gs)
        if winner:
            _set_game_over(gs, winner)
            return
    if box >= gs.meta.final_box:        # 4.7.1 Game End
        _set_game_over(gs, scenarios.end_of_scenario_winner(gs))
        return
    # advance to next Turn's Levy (4.7.5 final bullet)
    gs.meta.calendar_box = box + 1
    gs.meta.phase = "levy"
    gs.meta.subphase = None
    gs.meta.plan_submitted = {}
    gs.meta.active_card = None
    gs.meta.active_lord = None


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


def _wastage(gs: GameState) -> None:
    """4.7.4: each Lord with more than one of any Asset type, or more than one
    This-Lord Capability, discards one such item (Seljuk then Roman)."""
    for side in SIDES:
        for l in gs.lords.values():
            if l.side != side or not l.mustered:
                continue
            assets = {"carts": l.assets.carts, "provender": l.assets.provender,
                      "coin": l.assets.coin, "loot": l.assets.loot}
            top = max(assets, key=lambda k: assets[k])
            if assets[top] > 1:
                setattr(l.assets, top, assets[top] - 1)
            elif len(l.capabilities) > 1:
                card = l.capabilities.pop()
                gs.side_decks(side).draw_deck.append(card)


def _reset(gs: GameState) -> None:
    """4.7.5 (non-advance parts): return unpaid Themata, unstack Lieutenants,
    discard This-Campaign Events. (Auto-returns Themata; pay-to-retain is a
    player choice surfaced in a later phase.)"""
    for l in gs.lords.values():
        for marker in l.themata_on_mat:
            home = marker.home_thema
            if home and home in gs.themata:
                marker.home_thema = None
                gs.themata[home].append(marker)
        l.themata_on_mat = []
        l.lieutenant_of = None
        l.lower_lord = None
    for side in SIDES:
        gs.side_decks(side).this_campaign_events = []
    gs.meta.notes.pop("moustache_campaign", None)
    gs.meta.notes.pop("peace_offering_season", None)


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
            seats += ["to_mosul_and_baghdad", "amid"]
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
        lord.assets.loot = 0  # Unladen
        lord.assets.carts = -(-lord.assets.carts // 2)  # halve, round up
        lord.assets.provender = min(lord.assets.provender, lord.assets.carts)
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
        # March (4.3): one option per connected Way (cost computed by handler).
        if not lord.besieged:
            for edge in gmap.ways_from(loc_id):
                out.append({"type": "cmd_march", "lord": lid, "to": edge["to"], "way_type": edge["type"],
                            "_desc": f"March to {sd.locale(edge['to'])['name']} via {edge['type']} (4.3)"})
        # Forage (4.5.4): available unless the Locale is Ravaged.
        if st.ravaged_side is None and not lord.besieged:
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
                out.append({"type": "cmd_ravage", "lord": lid, "actions": 2, "_desc": "Ravage (Seljuk, 2 actions, auto) (4.5.5)"})
                if gs.meta.actions_remaining >= 1:
                    out.append({"type": "cmd_ravage", "lord": lid, "actions": 1, "_desc": "Ravage (Seljuk, 1 action; Roman may defend with Themata) (4.5.5)"})
        # Supply (4.4): a Route to an un-Ruined Seat within Cart budget.
        if not lord.besieged:
            cost = _min_supply_cost(gs, lord)
            if cost is not None and cost <= _available_carts(gs, lord):
                out.append({"type": "cmd_supply", "lord": lid, "_desc": "Supply Provender via a Route (4.4)"})
        # Siege/Storm (4.5.1-.2): a Besieging Lord may advance the Siege or Storm.
        if _besieging(gs, lord):
            out.append({"type": "cmd_siege", "lord": lid, "_desc": "Siege: roll Surrender / add Siegeworks (4.5.1)"})
            out.append({"type": "cmd_storm", "lord": lid, "_desc": "Storm the Stronghold (4.5.2)"})
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
    loc_id = lord.cylinder
    st = gs.locales[loc_id]
    if actions.current_allegiance(gs, loc_id) == lord.side:
        raise IllegalAction("not_enemy", "Ravage targets an Enemy Locale (4.5.5)")
    if st.ravaged_side is not None:
        raise IllegalAction("already_ravaged", "Locale is already Ravaged (4.5.5)")
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


def _min_supply_cost(gs: GameState, lord: LordState) -> int | None:
    """Cheapest Cart cost (Road 1, Pass 2 per Way) of a Route from the Lord to
    any of his own un-Ruined Seats, avoiding blocked Locales. None if no route."""
    seats = [s for s in sd.lord(lord.id).get("seats", []) if not gs.locales[s].ruins]
    if lord.id == "artuk_beg" and capabilities.lord_has(gs, "artuk_beg", "Artukid Legacy"):
        seats += [s for s in ("to_mosul_and_baghdad", "amid") if not gs.locales[s].ruins]
    if not seats:
        return None
    origin = lord.cylinder
    if origin in seats:
        return 0
    import heapq
    best = {origin: 0}
    pq = [(0, origin)]
    while pq:
        cost, loc = heapq.heappop(pq)
        if loc in seats:
            return cost
        if cost > best.get(loc, 1 << 30):
            continue
        for edge in gmap.ways_from(loc):
            nxt = edge["to"]
            if _blocks_supply(gs, nxt, lord.side, origin):
                continue
            step = 2 if edge["type"] == "pass" else 1
            nc = cost + step
            if nc < best.get(nxt, 1 << 30):
                best[nxt] = nc
                heapq.heappush(pq, (nc, nxt))
    return min((best[s] for s in seats if s in best), default=None)


def h_cmd_supply(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if lord.besieged:
        raise IllegalAction("besieged", "a Besieged Lord may not Supply (4.4)")
    cost = _min_supply_cost(gs, lord)
    if cost is None:
        raise IllegalAction("no_supply_route", "no Route to an un-Ruined Seat (4.4.1)")
    if cost > _available_carts(gs, lord):
        raise IllegalAction("insufficient_carts", f"need {cost} Carts for the Route (4.4.1)")
    lord.assets.provender = min(lord.assets.provender + 1, 8)
    spend_actions(gs, 1)
    return {"ok": True, "action": "cmd_supply", "lord": lord.id, "route_cost": cost, "provender": lord.assets.provender}


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
        if not actions.is_commander(gs, lord.id):
            raise IllegalAction("not_commander_group", "only a Commander may lead a Group March (4.3.1)")
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
    way = _way_between(lord.cylinder, to, action.get("way_type"))
    if way is None:
        raise IllegalAction("no_way", f"no Way from {lord.cylinder} to {to}")
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
    for g in group:
        g.cylinder = to
        g.moved_fought = True
    lord.flags["first_march_used"] = True
    gs.meta.actions_remaining -= cost
    res = {"ok": True, "action": "cmd_march", "lord": lord.id, "to": to,
           "way": way["type"], "cost": cost, "group": [g.id for g in group]}
    arrival = _resolve_arrival(gs, group, to)
    res.update(arrival)
    if not arrival.get("pending") and gs.meta.actions_remaining <= 0:
        _after_card(gs)
    return res


def _resolve_arrival(gs: GameState, group: list[LordState], to: str) -> dict[str, Any]:
    """After a March: Approach (enemy Lords present) or Besiege/Bypass (enemy
    Stronghold, no enemy Lords outside) — both as pending sub-decisions."""
    side = group[0].side
    enemy_lords = _enemy_lord_ids_at(gs, to, side)
    if gs.locales[to].bypass:
        enemy_lords = []  # already Bypassing this Locale
    if enemy_lords:
        gs.meta.pending.append({
            "type": "approach_response", "locale": to, "attackers": [g.id for g in group],
            "defenders": enemy_lords, "_owed_by": _enemy(side),
        })
        return {"pending": "approach_response", "defenders": enemy_lords}
    info = sd.locale(to)
    enemy_sh = info.get("is_stronghold") and not gs.locales[to].ruins \
        and actions.current_allegiance(gs, to) == _enemy(side)
    if enemy_sh and not gs.locales[to].bypass and gs.locales[to].siege_markers == 0:
        gs.meta.pending.append({
            "type": "besiege_or_bypass", "locale": to, "lords": [g.id for g in group], "_owed_by": side,
        })
        return {"pending": "besiege_or_bypass"}
    return {}


def h_respond_approach(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    """4.3.4: each Inactive (defending) Lord chooses Avoid Battle, Withdraw, or
    Stand. ``choices`` maps lord_id -> {"action": "avoid"|"withdraw"|"stand",
    "to": <locale for avoid>}. Standers (if any) trigger a Battle (resolved in
    the Battle engine)."""
    pend = next((p for p in gs.meta.pending if p["type"] == "approach_response"), None)
    if pend is None:
        raise IllegalAction("no_pending", "no Approach to respond to")
    to = pend["locale"]
    choices = action.get("choices", {})
    side = gs.lords[pend["defenders"][0]].side
    standers, avoided, withdrew = [], [], []
    attacker_origin = gs.lords[pend["attackers"][0]].cylinder  # they are now at `to`
    for did in pend["defenders"]:
        ch = choices.get(did, {"action": "stand"})
        kind = ch.get("action", "stand")
        lord = gs.lords[did]
        if kind == "avoid":
            dest = ch.get("to")
            _validate_avoid(gs, lord, to, dest, side)
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
        res = battle.begin_battle(gs, pend["attackers"], standers, to,
                                  scripted=action.get("battle_decisions"),
                                  events=action.get("battle_events"))
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


def _validate_avoid(gs: GameState, lord: LordState, battle_loc: str, dest: str, side: str) -> None:
    if dest not in gs.locales or not gmap.is_adjacent(battle_loc, dest):
        raise IllegalAction("bad_avoid", "Avoid Battle moves to an adjacent Locale (4.3.4)")
    if _enemy_lord_ids_at(gs, dest, side):
        raise IllegalAction("avoid_into_enemy", "may not Avoid into a Locale with an Unbesieged Enemy Lord (4.3.4)")
    if group_laden(gs, [lord]):
        raise IllegalAction("avoid_laden", "Lords may only Avoid Battle Unladen (4.3.4)")


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
        for l in gs.lords.values():
            if l.mustered and l.cylinder == loc_id:
                l.moved_fought = True
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
            result["conquer"] = battle.conquer(gs, loc_id, lord.side)
            gs.meta.vp = scenarios.score(gs)
    if not seized:
        besiegers = sum(1 for l in gs.lords.values()
                        if l.mustered and l.cylinder == loc_id and l.side == lord.side and not l.besieged)
        if besiegers >= size and gs.locales[loc_id].siege_markers < 4:
            gs.locales[loc_id].siege_markers += 1
            result["siegeworks_added"] = True
    for l in gs.lords.values():  # mark all Lords at the Locale Moved/Fought
        if l.mustered and l.cylinder == loc_id:
            l.moved_fought = True
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


def h_cmd_storm(gs: GameState, action: dict[str, Any], roller: DiceRoller) -> dict[str, Any]:
    lord = _require(action.get("lord"), gs)
    if not _besieging(gs, lord):
        raise IllegalAction("not_besieging", "only a Besieging Lord may Storm (4.5.2)")
    if gs.locales[lord.cylinder].siege_markers <= 0:
        raise IllegalAction("no_siege", "no Siege markers to Storm with")
    from . import battle
    attackers = _besieging_lords_at(gs, lord.cylinder, lord.side)
    ctx = battle.DecisionContext(action.get("storm_decisions"))
    res = battle.resolve_storm(gs, attackers, lord.cylinder, ctx, roller)
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
