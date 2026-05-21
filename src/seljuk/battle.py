"""Battle resolution (Phase 3b; Storm/Sally share much of this in 3c).

Implements the 4.8 Battle: Array (up to 3 Front positions + Reserve), Rounds
(Concede -> Reposition -> Strike), the six Strike steps in initiative order
(Missile then Melee; Defending then Attacking; Horse before Foot), Flanking,
Hits (sum of Strike values, rounded up), Protection by Hit type
(Armor / Evade / Unarmored), Rout, Concede + Pursuit halving, and the Ending
(Retreat / Withdraw / Removal, Losses, Spoils, Service, Aftermath).

Player choice points flow through a DecisionContext: a scripted list (FIFO, for
tests), else a deterministic fallback (first option) so the engine is a usable
black box (BRIEF.md, "Engine / Operator Split"). The full decision trace is
returned so a Battle replays from a state file + recorded decisions.

Per-card Arts of War effects (Cavalry Charge, Bardoukia, Lamellar, etc.) are
Phase 4 and are not applied here.
"""
from __future__ import annotations

from typing import Any, Optional

from . import scenarios, static_data as sd
from .rng import DiceRoller
from .state import GameState, LordState

SLOTS = ["left", "center", "right"]

# Base Strike values (no Capabilities). Missile: Infantry needs JAVELINS (0
# here); Norman/Varangian have no Missiles. Foot Melee: Varangian Strikes in
# Round 1 only.
_MISSILE = {"tagmata": 0.5, "scholai_hetaireia": 1.0, "ghulam_cavalry": 0.5,
            "turkic_horse": 1.0, "militia": 0.5}
_HORSE_MELEE = {"tagmata": 1.0, "norman_knights": 2.0, "scholai_hetaireia": 1.0,
                "ghulam_cavalry": 1.0, "turkic_horse": 0.5}
_FOOT_MELEE = {"varangian_guard": 3.0, "infantry": 1.0, "militia": 0.5}

_ARMORED = {"tagmata": (1, 3), "norman_knights": (1, 4), "scholai_hetaireia": (1, 4),
            "ghulam_cavalry": (1, 4), "varangian_guard": (1, 4), "infantry": (1, 3)}


def _category(unit: str) -> str:
    return sd.forces()["units"][unit]["category"]


def protection_range(unit: str, hit_type: str) -> tuple[int, int]:
    """Protection roll range that NEGATES a Hit (4.8.2). hit_type: 'missile' or
    'melee'. Only Turkic Horse differs by Hit type (Unarmored vs Evade)."""
    if unit == "turkic_horse":
        return (1, 1) if hit_type == "missile" else (1, 3)  # Unarmored vs Evade (Battle)
    if unit == "militia":
        return (1, 1)  # Unarmored
    return _ARMORED[unit]


def _strike_table(step: str, round_no: int) -> dict[str, float]:
    if step == "missile":
        return _MISSILE
    if step == "horse_melee":
        return _HORSE_MELEE
    # foot_melee: Varangian only in Round 1 (Player Aid / errata)
    tbl = dict(_FOOT_MELEE)
    if round_no > 1:
        tbl["varangian_guard"] = 0.0
    return tbl


class DecisionContext:
    """Resolves Battle choice points (scripted FIFO, else first-option fallback)."""

    def __init__(self, scripted: Optional[list] = None) -> None:
        self.scripted = list(scripted or [])
        self.trace: list[dict] = []

    def decide(self, dtype: str, options: list, info: dict | None = None):
        """Resolve a choice. Scripted entries may be typed ``(dtype, choice)``
        (consumed only at a matching decision) or bare values (consumed in
        order). With nothing applicable scripted, fall back to the first
        option."""
        if not options:
            return None
        choice = None
        if self.scripted:
            head = self.scripted[0]
            if isinstance(head, tuple) and len(head) == 2 and isinstance(head[0], str):
                if head[0] == dtype:
                    self.scripted.pop(0)
                    choice = head[1]
                # else: a typed entry for a different decision -> fall back here
            else:
                self.scripted.pop(0)
                choice = head
        if choice is None:
            choice = options[0]
        self.trace.append({"type": dtype, "choice": choice, "options": options})
        return choice


class _Side:
    def __init__(self, gs: GameState, lord_ids: list[str], role: str) -> None:
        self.gs = gs
        self.role = role  # "attacker" | "defender"
        self.front: dict[str, Optional[str]] = {"left": None, "center": None, "right": None}
        self.reserve: list[str] = list(lord_ids)

    def front_lords(self) -> list[str]:
        return [self.front[s] for s in SLOTS if self.front[s]]

    def all_lords(self) -> list[str]:
        return self.front_lords() + list(self.reserve)


def _unrouted_units(lord: LordState) -> dict[str, int]:
    return {u: n for u, n in lord.forces.items() if n > 0}


def _is_routed(lord: LordState) -> bool:
    return sum(lord.forces.values()) == 0


def begin_battle(gs: GameState, attackers: list[str], defenders: list[str], locale: str,
                 scripted: Optional[list] = None) -> dict[str, Any]:
    """Entry point from the Approach 'Stand' path (4.3.4 -> 4.8)."""
    ctx = DecisionContext(scripted)
    roller = _roller(gs)
    result = resolve_battle(gs, attackers, defenders, locale, ctx, roller)
    _save_roller(gs, roller)
    # remove the pending battle marker if present
    gs.meta.pending = [p for p in gs.meta.pending if p.get("type") != "battle"]
    return result


def _roller(gs: GameState) -> DiceRoller:
    r = DiceRoller(seed=gs.meta.seed)
    if gs.meta.rng_state is not None:
        st = gs.meta.rng_state
        r.set_state((st[0], tuple(st[1]), st[2]))
    return r


def _save_roller(gs: GameState, r: DiceRoller) -> None:
    st = r.get_state()
    gs.meta.rng_state = [st[0], list(st[1]), st[2]]


def resolve_battle(gs: GameState, attacker_ids: list[str], defender_ids: list[str],
                   locale: str, ctx: DecisionContext, roller: DiceRoller) -> dict[str, Any]:
    active = gs.meta.active_lord if gs.meta.active_lord in attacker_ids else attacker_ids[0]
    att = _Side(gs, [a for a in attacker_ids if a != active], "attacker")
    deff = _Side(gs, list(defender_ids), "defender")

    # --- Array (4.8.1): Active attacker at Front center; others fill L/R. ---
    att.front["center"] = active
    _fill_front(att, ctx, "initial_placement_attacker")
    # Defender opposite each Front attacker: center first, then L, R.
    _fill_defender(att, deff, ctx)

    rounds = []
    pursuit = {"attacker": False, "defender": False}
    conceder = None
    round_no = 0
    MAX = 30
    while round_no < MAX:
        round_no += 1
        # Concede? (Rounds after the first; Attacker then Defender)
        if round_no > 1:
            for role, side in (("attacker", att), ("defender", deff)):
                if conceder is None and _offer_concede(gs, side, ctx, role):
                    conceder = role
                    pursuit[role] = True
            # Reposition
            _reposition(gs, att, deff, ctx)

        _strike_phase(gs, att, deff, pursuit, round_no, ctx, roller, rounds)

        att_alive = any(not _is_routed(gs.lords[l]) for l in att.all_lords())
        def_alive = any(not _is_routed(gs.lords[l]) for l in deff.all_lords())
        if conceder is not None or not att_alive or not def_alive:
            break
        # remove routed lords from the array before next round
        _purge_routed(att)
        _purge_routed(deff)

    # --- Determine loser (4.8.3) ---
    att_alive = any(not _is_routed(gs.lords[l]) for l in att.all_lords())
    def_alive = any(not _is_routed(gs.lords[l]) for l in deff.all_lords())
    if conceder == "attacker" or not att_alive:
        loser, winner = "attacker", "defender"
    elif conceder == "defender" or not def_alive:
        loser, winner = "defender", "attacker"
    else:
        loser, winner = "defender", "attacker"  # shouldn't happen; safe default

    ending = _end_battle(gs, attacker_ids, defender_ids, loser, conceder, locale, ctx, roller)
    gs.meta.vp = scenarios.score(gs)
    return {"ok": True, "action": "battle", "locale": locale, "winner": winner, "loser": loser,
            "conceder": conceder, "rounds": round_no, "strikes": rounds, "ending": ending,
            "decisions": ctx.trace}


def _fill_front(side: _Side, ctx: DecisionContext, dtype: str) -> None:
    for slot in ("left", "right"):
        if not side.reserve:
            break
        choice = ctx.decide(dtype, list(side.reserve), {"slot": slot})
        side.front[slot] = choice
        side.reserve.remove(choice)


def _fill_defender(att: _Side, deff: _Side, ctx: DecisionContext) -> None:
    order = [s for s in ("center", "left", "right") if att.front[s]]
    for slot in order:
        if not deff.reserve:
            break
        choice = ctx.decide("initial_placement_defender", list(deff.reserve), {"slot": slot})
        deff.front[slot] = choice
        deff.reserve.remove(choice)


def _offer_concede(gs: GameState, side: _Side, ctx: DecisionContext, role: str) -> bool:
    choice = ctx.decide("concede", [False, True], {"role": role})
    return bool(choice)


def _purge_routed(side: _Side) -> None:
    for slot in SLOTS:
        lid = side.front[slot]
        if lid and _is_routed(side.gs.lords[lid]):
            side.front[slot] = None
    side.reserve = [l for l in side.reserve if not _is_routed(side.gs.lords[l])]


def _reposition(gs: GameState, att: _Side, deff: _Side, ctx: DecisionContext) -> None:
    _purge_routed(att)
    _purge_routed(deff)
    # Advance Lords: Attacker then Defender slide Reserve into empty Front slots.
    for side, dtype in ((att, "reserve_advance"), (deff, "reserve_advance")):
        for slot in SLOTS:
            if side.front[slot] is None and side.reserve:
                opts = list(side.reserve)
                choice = ctx.decide(dtype, opts, {"slot": slot, "role": side.role})
                side.front[slot] = choice
                side.reserve.remove(choice)
    # Center fill: a Left/Right Front Lord must slide to an empty Center.
    for side in (att, deff):
        if side.front["center"] is None:
            wing = [side.front[s] for s in ("left", "right") if side.front[s]]
            if wing:
                choice = ctx.decide("center_fill", wing, {"role": side.role})
                for s in ("left", "right"):
                    if side.front[s] == choice:
                        side.front[s] = None
                side.front["center"] = choice


def _target_of(striker_slot: str, enemy: _Side, ctx: DecisionContext) -> Optional[str]:
    """The enemy Lord a Front striker hits: directly opposite, else Flank the
    closest enemy in the row (Center may choose Left/Right)."""
    if enemy.front[striker_slot]:
        return enemy.front[striker_slot]
    si = SLOTS.index(striker_slot)
    present = [(abs(SLOTS.index(s) - si), s) for s in SLOTS if enemy.front[s]]
    if not present:
        return None
    present.sort()
    closest = [s for d, s in present if d == present[0][0]]
    if len(closest) == 1:
        return enemy.front[closest[0]]
    choice = ctx.decide("flanker_target", [enemy.front[s] for s in closest], {"striker_slot": striker_slot})
    return choice


def _strike_phase(gs: GameState, att: _Side, deff: _Side, pursuit: dict, round_no: int,
                  ctx: DecisionContext, roller: DiceRoller, log: list) -> None:
    steps = [
        ("missile", deff, att, "defender"), ("missile", att, deff, "attacker"),
        ("horse_melee", deff, att, "defender"), ("horse_melee", att, deff, "attacker"),
        ("foot_melee", deff, att, "defender"), ("foot_melee", att, deff, "attacker"),
    ]
    for step, striking, target_side, role in steps:
        _resolve_step(gs, step, striking, target_side, role, pursuit, round_no, ctx, roller, log)


def _resolve_step(gs, step, striking: _Side, target_side: _Side, role, pursuit, round_no,
                  ctx: DecisionContext, roller: DiceRoller, log: list) -> None:
    table = _strike_table(step, round_no)
    cat = "horse" if step == "horse_melee" else ("foot" if step == "foot_melee" else None)
    hit_type = "missile" if step == "missile" else "melee"
    # Group strikers by the enemy Lord they hit.
    by_target: dict[str, float] = {}
    for slot in SLOTS:
        lid = striking.front[slot]
        if not lid or _is_routed(gs.lords[lid]):
            continue
        target = _target_of(slot, target_side, ctx)
        if not target:
            continue
        hits = 0.0
        for unit, n in _unrouted_units(gs.lords[lid]).items():
            if cat and _category(unit) != cat:
                continue
            hits += table.get(unit, 0.0) * n
        by_target[target] = by_target.get(target, 0.0) + hits
    for target, raw in by_target.items():
        if raw <= 0:
            continue
        if pursuit.get(role):  # Conceding side halves its Hits (Pursuit, 4.8.2)
            raw = raw / 2.0
        hits = int(raw + 0.999)  # round up
        applied = _apply_hits(gs, target, hits, hit_type, ctx, roller)
        log.append({"round": round_no, "step": step, "by": role, "target": target,
                    "hits": hits, "routed_units": applied})


def _apply_hits(gs: GameState, target_id: str, hits: int, hit_type: str,
                ctx: DecisionContext, roller: DiceRoller) -> list[str]:
    lord = gs.lords[target_id]
    routed_units: list[str] = []
    for _ in range(hits):
        avail = [u for u, n in lord.forces.items() if n > 0]
        if not avail:
            break
        unit = ctx.decide("hit_absorption", avail, {"lord": target_id, "hit_type": hit_type})
        lo, hi = protection_range(unit, hit_type)
        roll = roller.d6()
        if not (lo <= roll <= hi):
            lord.forces[unit] -= 1
            lord.routed[unit] = lord.routed.get(unit, 0) + 1
            routed_units.append(unit)
    return routed_units


# --- Ending the Battle (4.8.3-4.8.6) ----------------------------------------

def _end_battle(gs: GameState, att_ids: list[str], def_ids: list[str], loser: str,
                conceder: Optional[str], locale: str, ctx: DecisionContext,
                roller: DiceRoller) -> dict[str, Any]:
    losing_ids = att_ids if loser == "attacker" else def_ids
    loser_role = loser
    conceded = (conceder == loser)
    events = {"retreat": [], "losses": [], "service": [], "removed": [],
              "spoils_to": "defender" if loser == "attacker" else "attacker"}

    for lid in losing_ids:
        lord = gs.lords[lid]
        fate = _lord_fate(gs, lord, loser_role, locale, conceded, ctx)
        events["retreat"].append({"lord": lid, "fate": fate})
        if fate == "retreat" and lord.service_box is not None:  # Service shift (4.8.3)
            roll = roller.d6()
            shift = 1 if roll <= 3 else 2
            lord.service_box = max(0, lord.service_box - shift)
            events["service"].append({"lord": lid, "roll": roll, "shift": shift})

    # Losses (4.8.4): roll for each Routed unit (both sides).
    for lid in att_ids + def_ids:
        lord = gs.lords[lid]
        fate = next((e["fate"] for e in events["retreat"] if e["lord"] == lid), None)
        harsh = (lid in losing_ids and loser_role == "attacker" and fate == "retreat" and not conceded)
        _resolve_losses(gs, lord, harsh, roller, events)

    # Spoils (4.8.3) + removal of Lords with no Forces (4.8.5).
    _spoils_and_removal(gs, att_ids, def_ids, loser, events, conceder)

    for lid in att_ids + def_ids:  # Aftermath (4.8.6)
        if lid in gs.lords:
            gs.lords[lid].moved_fought = True
    return events


def _lord_fate(gs: GameState, lord: LordState, loser_role: str, locale: str,
               conceded: bool, ctx: DecisionContext) -> str:
    """Retreat / Withdraw / Removal for a losing Lord (4.8.3)."""
    # Withdraw into a Friendly Stronghold here (Defender only, not Aleppo).
    from . import campaign
    can_withdraw = (loser_role == "defender"
                    and sd.locale(locale).get("is_stronghold") and not gs.locales[locale].ruins
                    and campaign.actions.current_allegiance(gs, locale) == lord.side
                    and locale != "aleppo")
    # Retreat targets: adjacent Locales free of enemy Lords / unbesieged-unbypassed enemy Strongholds.
    from . import map as gmap
    enemy = "roman" if lord.side == "seljuk" else "seljuk"
    retreat_opts = []
    for edge in gmap.ways_from(locale):
        dst = edge["to"]
        if any(o.mustered and o.cylinder == dst and o.side == enemy for o in gs.lords.values()):
            continue
        retreat_opts.append(dst)
    options = []
    if can_withdraw:
        options.append("withdraw")
    options.extend([("retreat", d) for d in retreat_opts])
    if not options:
        choice = "removed"
    else:
        choice = ctx.decide("retreat", options, {"lord": lord.id})
    if choice == "withdraw":
        lord.besieged = True
        lord.cylinder = locale
        return "withdraw"
    if isinstance(choice, tuple) and choice[0] == "retreat":
        lord.cylinder = choice[1]
        lord.besieged = False
        return "retreat"
    return "removed"


def _resolve_losses(gs: GameState, lord: LordState, harsh: bool, roller: DiceRoller, events: dict) -> None:
    recovered: dict[str, int] = {}
    lost: dict[str, int] = {}
    for unit, n in list(lord.routed.items()):
        for _ in range(n):
            roll = roller.d6()
            if harsh:
                ok = roll == 1
            else:
                lo, hi = _natural_protection(unit)
                ok = lo <= roll <= hi
            if ok:
                lord.forces[unit] = lord.forces.get(unit, 0) + 1
                recovered[unit] = recovered.get(unit, 0) + 1
            else:
                lost[unit] = lost.get(unit, 0) + 1
        lord.routed[unit] = 0
    lord.routed = {u: n for u, n in lord.routed.items() if n > 0}
    if recovered or lost:
        events["losses"].append({"lord": lord.id, "recovered": recovered, "lost": lost, "harsh": harsh})


def _natural_protection(unit: str) -> tuple[int, int]:
    """Inherent Protection for post-Battle Losses (4.8.4), unmodified by cards."""
    if unit == "militia":
        return (1, 1)
    if unit == "turkic_horse":
        return (1, 3)  # Evade range used as inherent (no Missiles context post-Battle)
    return _ARMORED[unit]


def _spoils_and_removal(gs: GameState, att_ids: list[str], def_ids: list[str], loser: str,
                        events: dict, conceder: Optional[str]) -> None:
    from . import actions
    losing_ids = att_ids if loser == "attacker" else def_ids
    winner_ids = def_ids if loser == "attacker" else att_ids
    winners = [l for l in winner_ids if not _is_routed(gs.lords[l])]
    conceded = (conceder == loser)
    pool = {"coin": 0, "loot": 0, "provender": 0, "carts": 0}
    # Spoils transfer by fate (4.8.3).
    for lid in losing_ids:
        lord = gs.lords[lid]
        fate = next((e["fate"] for e in events["retreat"] if e["lord"] == lid), "removed")
        if fate == "withdraw":
            continue  # keep all Assets
        if fate == "retreat" and conceded:
            pool["loot"] += lord.assets.loot
            lord.assets.loot = 0
            excess = max(0, lord.assets.provender - lord.assets.carts)
            pool["provender"] += excess
            lord.assets.provender -= excess
        else:  # removed, or retreated WITHOUT conceding -> all Assets
            for k in ("coin", "loot", "provender", "carts"):
                pool[k] += getattr(lord.assets, k)
                setattr(lord.assets, k, 0)
    # Distribute Spoils to the first surviving winning Lord (a player choice;
    # deterministic here).
    if winners and any(pool.values()):
        w = gs.lords[winners[0]]
        for k in ("coin", "loot", "provender", "carts"):
            setattr(w.assets, k, min(8, getattr(w.assets, k) + pool[k]))
    # Removal by combat (4.8.5): any Lord (either side) with no Forces after
    # Losses, or a losing Lord who could not Retreat/Withdraw, is removed.
    for lid in att_ids + def_ids:
        lord = gs.lords.get(lid)
        if lord is None or not lord.mustered:
            continue
        fate = next((e["fate"] for e in events["retreat"] if e["lord"] == lid), None)
        if _is_routed(lord) or fate == "removed":
            _remove_by_combat(gs, lord)
            events["removed"].append(lid)


def _remove_by_combat(gs: GameState, lord: LordState) -> None:
    """4.8.5: a Lord removed in combat Disbands as if Beyond Service (3.3.1)."""
    from . import actions
    actions._disband_beyond(gs, lord)
