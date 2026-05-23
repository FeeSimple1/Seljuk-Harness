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
from . import capabilities
from .rng import DiceRoller
from .state import GameState, LordState

SLOTS = ["left", "center", "right"]

# Base Strike values (no Capabilities). Missile: Infantry needs JAVELINS (0
# here); Norman/Varangian have no Missiles. Foot Melee: Varangian Strikes in
# Round 1 only.
_MISSILE = {"tagmata": 0.5, "scholai_hetaireia": 1.0, "ghulam_cavalry": 0.5,
            "turkic_horse": 1.0, "militia": 0.5}
_HORSE_MELEE = {"tagmata": 1.0, "norman_knights": 2.0, "scholai_hetaireia": 1.0,
                "ghulam_cavalry": 1.0}  # Turkic Horse base Melee 0 (Shock Tactics grants it; Q-002)
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
        self.locale = None
        self.mountain_ambush = False
        self.front: dict[str, Optional[str]] = {"left": None, "center": None, "right": None}
        self.reserve: list[str] = list(lord_ids)
        # Relief Sally rows (4.8.1). The Attacker may have a Sallying row (the
        # Besieged Lords who join the relief Attack, arrayed behind the
        # Defenders); the Defender may have a Rearguard row (Reserve Lords
        # positioned opposite the Sallying Attackers). Empty in a normal Battle.
        self.sally: dict[str, Optional[str]] = {"left": None, "center": None, "right": None}
        self.rearguard: dict[str, Optional[str]] = {"left": None, "center": None, "right": None}

    def front_lords(self) -> list[str]:
        return [self.front[s] for s in SLOTS if self.front[s]]

    def sally_lords(self) -> list[str]:
        return [self.sally[s] for s in SLOTS if self.sally[s]]

    def rearguard_lords(self) -> list[str]:
        return [self.rearguard[s] for s in SLOTS if self.rearguard[s]]

    def all_lords(self) -> list[str]:
        return self.front_lords() + self.sally_lords() + self.rearguard_lords() + list(self.reserve)


def _unrouted_units(lord: LordState) -> dict[str, int]:
    return {u: n for u, n in lord.forces.items() if n > 0}


def _is_routed(lord: LordState) -> bool:
    return sum(lord.forces.values()) == 0


def begin_battle(gs: GameState, attackers: list[str], defenders: list[str], locale: str,
                 scripted: Optional[list] = None, events: Optional[dict] = None,
                 sallying: Optional[set] = None, siegeworks: int = 0,
                 approach_origin: Optional[str] = None) -> dict[str, Any]:
    """Entry point from the Approach 'Stand' path (4.3.4 -> 4.8). ``events`` maps
    a side to the Held Battle Events it plays; ``sallying``/``siegeworks`` carry
    a Relief Sally (besieged Lords + the Defenders' Siegeworks Walls vs them)."""
    played, cc, charge = _consume_battle_events(gs, events)
    ctx = DecisionContext(scripted)
    roller = _roller(gs)
    result = resolve_battle(gs, attackers, defenders, locale, ctx, roller, played, cc, charge,
                            sallying=sallying, siegeworks=siegeworks, approach_origin=approach_origin)
    _save_roller(gs, roller)
    # remove the pending battle marker if present
    gs.meta.pending = [p for p in gs.meta.pending if p.get("type") != "battle"]
    return result


_BATTLE_HOLDS = {"R2", "S2", "S3", "R24", "S6"}  # Mountain Ambush, Betrayal, Cavalry Charge, Command Confusion


def _consume_battle_events(gs: GameState, events: Optional[dict]):
    """Validate/consume played Battle Hold Events. Returns (played, cc, charge):
    played[side] = simple cards (R2/S2/S3); cc = Roman Lords under Command
    Confusion (S6, played by Seljuk); charge = Roman Lords with Cavalry Charge
    (R24, played by Roman)."""
    played = {"seljuk": [], "roman": []}
    cc: set = set()
    charge: set = set()
    if not events:
        return played, cc, charge
    for side in ("seljuk", "roman"):
        for entry in events.get(side, []):
            cid = entry["card"] if isinstance(entry, dict) else entry
            if cid not in _BATTLE_HOLDS or cid not in gs.side_decks(side).held_events:
                continue
            gs.side_decks(side).held_events.remove(cid)
            gs.side_decks(side).draw_deck.append(cid)
            if cid == "S6" and isinstance(entry, dict):       # Command Confusion -> a Roman Lord
                cc.add(entry["lord"])
            elif cid == "R24" and isinstance(entry, dict):    # Cavalry Charge -> a Roman Lord
                charge.add(entry["lord"])
            else:
                played[side].append(cid)
    return played, cc, charge


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
                   locale: str, ctx: DecisionContext, roller: DiceRoller,
                   played: Optional[dict] = None, cc: Optional[set] = None,
                   charge: Optional[set] = None, sallying: Optional[set] = None,
                   siegeworks: int = 0, approach_origin: Optional[str] = None) -> dict[str, Any]:
    played = played or {"seljuk": [], "roman": []}
    cc = cc or set()
    charge = charge or set()
    sallying = sallying or set()
    active = gs.meta.active_lord if gs.meta.active_lord in attacker_ids else attacker_ids[0]
    for _lid in attacker_ids + defender_ids:
        gs.lords[_lid].flags["turkic_routed_battle"] = 0
    # Pursuit exception (4.8.2): a single Conceding Lord whose Forces are ONLY
    # Turkic Horse at the START of the battle, facing a single opposing Lord,
    # causes BOTH sides to halve Hits in the final Round.
    _turkic_only_start = {lid: (set(u for u, n in gs.lords[lid].forces.items() if n > 0) == {"turkic_horse"})
                          for lid in attacker_ids + defender_ids}
    _solo_battle = len(attacker_ids) == 1 and len(defender_ids) == 1
    # Sallying Lords (Relief Sally, 4.8.1) form their own row behind the
    # Defenders; they are kept out of the relieving force's Front/Reserve.
    relief = bool(sallying)
    att_front_pool = [a for a in attacker_ids if a != active and a not in sallying]
    att = _Side(gs, att_front_pool, "attacker")
    deff = _Side(gs, list(defender_ids), "defender")

    # --- Array (4.8.1): Active attacker at Front center; others fill L/R. ---
    if active in sallying:
        # A Besieged active Lord that Sallies has no relieving force at Front;
        # he leads the Sallying row instead.
        att.front["center"] = None
    else:
        att.front["center"] = active
    _fill_front(att, ctx, "initial_placement_attacker")
    # Defender opposite each Front attacker: center first, then L, R.
    _fill_defender(att, deff, ctx)
    # Relief Sally rows: Sallying Attackers (incl. an active Sallying Lord) form
    # a row behind the Defenders; the Defender's Reserve fills a Rearguard row
    # opposite them, then any extra Defenders remain in Reserve (4.8.1).
    if relief:
        sally_pool = ([active] if active in sallying else []) + \
                     [a for a in attacker_ids if a != active and a in sallying]
        _fill_row(att, "sally", sally_pool, ctx, "sally_placement")
        _fill_rearguard(att, deff, ctx)
    # Mountain Ambush (R2/S2): Round-1 Walls 1-3 vs Missiles for the playing
    # side, if the Locale is adjacent to a Pass (1.3.1).
    from . import map as gmap
    for side_obj, sname in ((att, gs.lords[active].side), (deff, gs.lords[defender_ids[0]].side)):
        side_obj.locale = locale
        amb = "R2" if sname == "roman" else "S2"
        if amb in played.get(sname, []) and gmap.adjacent_to_pass(locale):
            side_obj.mountain_ambush = True
    betrayal_pending = "S3" in played.get("seljuk", [])
    if betrayal_pending and "S3" not in gs.meta.asterisks_used:
        gs.meta.asterisks_used.append("S3")

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
                    if _solo_battle:  # 4.8.2 Turkic-only Conceding exception -> halve BOTH
                        conceding_lid = (attacker_ids if role == "attacker" else defender_ids)[0]
                        if _turkic_only_start.get(conceding_lid):
                            pursuit["attacker"] = True
                            pursuit["defender"] = True
            # Reposition
            _reposition(gs, att, deff, ctx)
            if betrayal_pending:  # S3 Betrayal: move a non-commander Roman Front Lord to Reserve
                for sd_obj in (att, deff):
                    for slot in SLOTS:
                        lid = sd_obj.front[slot]
                        if lid and gs.lords[lid].side == "roman" and not sd.lord(lid).get("commander"):
                            sd_obj.front[slot] = None
                            sd_obj.reserve.append(lid)
                            betrayal_pending = False
                            break
                    if not betrayal_pending:
                        break

        _strike_phase(gs, att, deff, pursuit, round_no, ctx, roller, rounds, cc=cc, charge=charge,
                      sallying=sallying, siegeworks=siegeworks)

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

    ending = _end_battle(gs, attacker_ids, defender_ids, loser, conceder, locale, ctx, roller,
                         approach_origin=approach_origin, sallying=sallying)
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


def _fill_row(side: _Side, row: str, pool: list[str], ctx: DecisionContext, dtype: str) -> None:
    """Place up to three Lords from ``pool`` into ``row`` (center, then L, R);
    any extra go to that side's Reserve (a row is at most 3 wide)."""
    rowmap = getattr(side, row)
    remaining = list(pool)
    for slot in ("center", "left", "right"):
        if not remaining:
            break
        choice = ctx.decide(dtype, list(remaining), {"slot": slot, "row": row})
        rowmap[slot] = choice
        remaining.remove(choice)
    side.reserve.extend(remaining)


def _fill_rearguard(att: _Side, deff: _Side, ctx: DecisionContext) -> None:
    """4.8.1: Defending Reserve Lords position opposite the Sallying Attackers
    as a Rearguard row (center first, then L, R), matching occupied Sally
    slots; any beyond that stay in Reserve."""
    order = [s for s in ("center", "left", "right") if att.sally[s]]
    for slot in order:
        if not deff.reserve:
            break
        choice = ctx.decide("rearguard_placement", list(deff.reserve), {"slot": slot})
        deff.rearguard[slot] = choice
        deff.reserve.remove(choice)


def _offer_concede(gs: GameState, side: _Side, ctx: DecisionContext, role: str) -> bool:
    choice = ctx.decide("concede", [False, True], {"role": role})
    return bool(choice)


def _purge_routed(side: _Side) -> None:
    for row in ("front", "sally", "rearguard"):
        rowmap = getattr(side, row)
        for slot in SLOTS:
            lid = rowmap[slot]
            if lid and _is_routed(side.gs.lords[lid]):
                rowmap[slot] = None
    side.reserve = [l for l in side.reserve if not _is_routed(side.gs.lords[l])]


def _adjust_rows(att: _Side, deff: _Side) -> None:
    """ADJUST ROWS (1.2.2 B, Relief Sally only): when a whole row has Routed.
    - If no Sallying Lords remain, the Rearguard becomes Reserve.
    - If no Front Defenders remain, the Rearguard faces about as Reserve.
    (The "no Rearguard -> Sallying Lords Flank Defenders" case needs no row
    move: striking falls back to the Front row automatically when the Rearguard
    is empty.)"""
    if not att.sally_lords() or not deff.front_lords():
        for slot in SLOTS:
            lid = deff.rearguard[slot]
            if lid:
                deff.rearguard[slot] = None
                deff.reserve.append(lid)


def _reposition(gs: GameState, att: _Side, deff: _Side, ctx: DecisionContext) -> None:
    _purge_routed(att)
    _purge_routed(deff)
    _adjust_rows(att, deff)
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


def _target_of(striker_slot: str, enemy: _Side, ctx: DecisionContext,
               row: str = "front") -> Optional[str]:
    """The enemy Lord a striker hits within the given enemy ``row``: directly
    opposite, else Flank the closest enemy in the row (Center may choose
    Left/Right)."""
    erow = getattr(enemy, row)
    if erow[striker_slot]:
        return erow[striker_slot]
    si = SLOTS.index(striker_slot)
    present = [(abs(SLOTS.index(s) - si), s) for s in SLOTS if erow[s]]
    if not present:
        return None
    present.sort()
    closest = [s for d, s in present if d == present[0][0]]
    if len(closest) == 1:
        return erow[closest[0]]
    choice = ctx.decide("flanker_target", [erow[s] for s in closest], {"striker_slot": striker_slot})
    return choice


import math as _math


def _lord_step_hits_caps(gs, lid, step, round_no):
    """(normal_hits, anti_armor_hits) for one Lord in a Strike step, applying
    Capabilities (Javelins, Alakatia, Shock Tactics, Bardoukia)."""
    lord = gs.lords[lid]
    names = capabilities.lord_capability_names(gs, lid)
    units = _unrouted_units(lord)
    normal = 0.0
    anti = 0.0
    if step == "missile":
        for u, n in units.items():
            normal += _MISSILE.get(u, 0.0) * n
        if "Javelins" in names:                       # S11: Infantry Missiles x1
            normal += units.get("infantry", 0) * 1.0
        if "Alakatia" in names and units.get("infantry", 0) >= 2:  # R23: +1 anti-armor Missile Hit
            anti += 1.0
    elif step == "horse_melee":
        for u, n in units.items():
            if _category(u) == "horse":
                normal += _HORSE_MELEE.get(u, 0.0) * n
        if "Shock Tactics" in names:                  # S4/S6: ceil(turkic/2) x1/2
            tk = units.get("turkic_horse", 0)
            normal += _math.ceil(tk / 2) * 0.5
        if "Bardoukia" in names:                       # R21: Tagmata Melee -> anti-armor
            tag = _HORSE_MELEE.get("tagmata", 1.0) * units.get("tagmata", 0)
            normal -= tag
            anti += tag
    elif step == "foot_melee":
        table = _strike_table("foot_melee", round_no)
        for u, n in units.items():
            if _category(u) == "foot":
                normal += table.get(u, 0.0) * n
    return max(0.0, normal), anti


def _front_set(side: _Side) -> set:
    return set(side.front_lords())


def _strike_phase(gs: GameState, att: _Side, deff: _Side, pursuit: dict, round_no: int,
                  ctx: DecisionContext, roller: DiceRoller, log: list,
                  cc: set | None = None, charge: set | None = None,
                  sallying: set | None = None, siegeworks: int = 0) -> None:
    cc = cc or set()
    charge = charge or set()
    sides = ((deff, att, "defender"), (att, deff, "attacker"))

    def _secondary(striking, target_side, role, step):
        """Relief Sally rows (4.8.1) Strike in their normal sub-step. Sallying
        Attackers Strike the Rearguard row (or Flank the Front Defenders if no
        Rearguard remains); their Hits are reduced by Siegeworks. The Rearguard
        Strikes the Sallying row (Siegeworks do not protect Attackers)."""
        if role == "attacker" and striking.sally_lords():
            tr = "rearguard" if target_side.rearguard_lords() else "front"
            _resolve_step(gs, step, striking, target_side, role, pursuit, round_no,
                          ctx, roller, log, striker_row="sally", target_row=tr,
                          step_walls=siegeworks)
        if role == "defender" and striking.rearguard_lords():
            _resolve_step(gs, step, striking, target_side, role, pursuit, round_no,
                          ctx, roller, log, striker_row="rearguard", target_row="sally",
                          step_walls=0)

    # Cavalry Charge (R24): Round 1, charged Lords' Horse Melee strikes before
    # all Missiles; those Horse skip the normal Horse-Melee step this Round.
    charged: set = set()
    if round_no == 1 and charge:
        for striking, target_side, role in (sides[1], sides[0]):  # attacker then defender
            ids = _front_set(striking) & charge
            if ids:
                _resolve_step(gs, "horse_melee", striking, target_side, role, pursuit, round_no,
                              ctx, roller, log, restrict=ids)
                charged |= ids
    cc_eff = cc - charge  # Cavalry Charge takes precedence over Command Confusion
    # Missiles: non-Command-Confusion Front Lords plus the Relief-Sally rows
    # first, then the CC Lords (who strike second).
    for striking, target_side, role in sides:
        _resolve_step(gs, "missile", striking, target_side, role, pursuit, round_no, ctx, roller, log,
                      restrict=_front_set(striking) - cc_eff)
        _secondary(striking, target_side, role, "missile")
    for striking, target_side, role in sides:
        ids = _front_set(striking) & cc_eff
        if ids:
            _resolve_step(gs, "missile", striking, target_side, role, pursuit, round_no, ctx, roller, log,
                          restrict=ids)
    # Melee (Horse then Foot, Defending then Attacking): non-CC Front Lords plus
    # the Relief-Sally rows first.
    for mstep in ("horse_melee", "foot_melee"):
        for striking, target_side, role in sides:
            _resolve_step(gs, mstep, striking, target_side, role, pursuit, round_no, ctx, roller, log,
                          restrict=_front_set(striking) - cc_eff, skip_charge=charged)
            _secondary(striking, target_side, role, mstep)
    # Then the CC Lords' Melee (strike second).
    for mstep in ("horse_melee", "foot_melee"):
        for striking, target_side, role in sides:
            ids = _front_set(striking) & cc_eff
            if ids:
                _resolve_step(gs, mstep, striking, target_side, role, pursuit, round_no, ctx, roller, log,
                              restrict=ids, skip_charge=charged)


def _resolve_step(gs, step, striking: _Side, target_side: _Side, role, pursuit, round_no,
                  ctx: DecisionContext, roller: DiceRoller, log: list,
                  restrict=None, skip_charge=None, striker_row: str = "front",
                  target_row: str = "front", step_walls: int = 0) -> None:
    hit_type = "missile" if step == "missile" else "melee"
    skip_charge = skip_charge or set()
    srow = getattr(striking, striker_row)
    by = {}        # target -> [normal, anti]
    for slot in SLOTS:
        lid = srow[slot]
        if not lid or _is_routed(gs.lords[lid]):
            continue
        if restrict is not None and lid not in restrict:
            continue
        if step == "horse_melee" and lid in skip_charge:
            continue  # Horse already struck via Cavalry Charge this Round
        target = _target_of(slot, target_side, ctx, row=target_row)
        if not target:
            continue
        normal, anti = _lord_step_hits_caps(gs, lid, step, round_no)
        cur = by.setdefault(target, [0.0, 0.0])
        cur[0] += normal
        cur[1] += anti

    def _emit(target, n_raw, a_raw, walls):
        if pursuit.get(role):  # Pursuit halving (4.8.2)
            n_raw /= 2.0
            a_raw /= 2.0
        n_hits = int(n_raw + 0.999)
        a_hits = int(a_raw + 0.999)
        if step == "missile" and round_no == 1 and target_side.mountain_ambush:
            n_hits = _roll_walls(roller, n_hits, (1, 3))  # Mountain Ambush (R2/S2)
            a_hits = _roll_walls(roller, a_hits, (1, 3))
        if walls > 0:  # Siegeworks vs Sallying strikes (Relief Sally, 4.8.1)
            n_hits = _roll_walls(roller, n_hits, (1, walls))
            a_hits = _roll_walls(roller, a_hits, (1, walls))
        applied = []
        if n_hits:
            applied += _apply_hits(gs, target, n_hits, hit_type, ctx, roller)
        if a_hits:
            applied += _apply_hits(gs, target, a_hits, hit_type, ctx, roller, anti_armor=True)
        if n_hits or a_hits:
            log.append({"round": round_no, "step": step, "by": role, "target": target,
                        "hits": n_hits + a_hits, "routed_units": applied,
                        **({"sallying": True} if striker_row == "sally" else {})})

    for target, (n, a) in by.items():
        _emit(target, n, a, step_walls)


def _apply_hits(gs: GameState, target_id: str, hits: int, hit_type: str,
                ctx: DecisionContext, roller: DiceRoller, anti_armor: bool = False) -> list[str]:
    lord = gs.lords[target_id]
    routed_units: list[str] = []
    reroll_used = False
    norman = capabilities.lord_has(gs, target_id, "Norman Heavy Cavalry")
    for _ in range(hits):
        avail = [u for u, n in lord.forces.items() if n > 0]
        if not avail:
            break
        unit = ctx.decide("hit_absorption", avail, {"lord": target_id, "hit_type": hit_type})
        lo, hi = capabilities.protection_range(gs, target_id, unit, hit_type, storm=False)
        if anti_armor and unit not in ("turkic_horse", "militia"):
            hi = max(lo, hi - 1)  # -1 to target Armor (Bardoukia/Alakatia)
        roll = roller.d6()
        ok = lo <= roll <= hi
        if not ok and norman and unit == "norman_knights" and not reroll_used:
            reroll_used = True  # Norman Heavy Cavalry: reroll 1 Armor per step (R5)
            ok = lo <= roller.d6() <= hi
        if not ok:
            lord.forces[unit] -= 1
            lord.routed[unit] = lord.routed.get(unit, 0) + 1
            routed_units.append(unit)
            if unit == "turkic_horse":
                lord.flags["turkic_routed_battle"] = int(lord.flags.get("turkic_routed_battle", 0)) + 1
    return routed_units


# --- Ending the Battle (4.8.3-4.8.6) ----------------------------------------

def _end_battle(gs: GameState, att_ids: list[str], def_ids: list[str], loser: str,
                conceder: Optional[str], locale: str, ctx: DecisionContext,
                roller: DiceRoller, approach_origin: Optional[str] = None,
                sallying: Optional[set] = None) -> dict[str, Any]:
    losing_ids = att_ids if loser == "attacker" else def_ids
    loser_role = loser
    conceded = (conceder == loser)
    events = {"retreat": [], "losses": [], "service": [], "removed": [],
              "spoils_to": "defender" if loser == "attacker" else "attacker"}

    sallying = sallying or set()
    for lid in losing_ids:
        lord = gs.lords[lid]
        # A Marching Attacker (not a Relief-Sally Lord) must Retreat to the
        # Locale it Approached from (4.8.3).
        marcher_origin = approach_origin if (loser_role == "attacker" and lid not in sallying) else None
        fate = _lord_fate(gs, lord, loser_role, locale, conceded, ctx,
                          approach_origin=approach_origin, marcher_origin=marcher_origin)
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


def _retreat_blocked(gs: GameState, dst: str, lord_side: str) -> bool:
    """4.8.3 A: a Retreat target must have no enemy Lords and no enemy
    Stronghold that is not already Besieged or Bypassed (Ruins never block)."""
    from . import campaign
    enemy = "roman" if lord_side == "seljuk" else "seljuk"
    if any(o.mustered and o.cylinder == dst and o.side == enemy for o in gs.lords.values()):
        return True
    info = sd.locale(dst)
    if info.get("is_stronghold") and not gs.locales[dst].ruins \
            and campaign.actions.current_allegiance(gs, dst) == enemy \
            and gs.locales[dst].siege_markers == 0 and not gs.locales[dst].bypass:
        return True
    return False


def _lord_fate(gs: GameState, lord: LordState, loser_role: str, locale: str,
               conceded: bool, ctx: DecisionContext, approach_origin: str | None = None,
               marcher_origin: str | None = None) -> str:
    """Retreat / Withdraw / Removal for a losing Lord (4.8.3)."""
    # Withdraw into a Friendly Stronghold here (Defender only, not Aleppo).
    from . import campaign
    can_withdraw = (loser_role == "defender"
                    and sd.locale(locale).get("is_stronghold") and not gs.locales[locale].ruins
                    and campaign.actions.current_allegiance(gs, locale) == lord.side
                    and locale != "aleppo")
    # Retreat targets: adjacent Locales free of enemy Lords / unbesieged-unbypassed
    # enemy Strongholds (4.8.3 A).
    from . import map as gmap
    retreat_opts = []
    for edge in gmap.ways_from(locale):
        dst = edge["to"]
        if _retreat_blocked(gs, dst, lord.side):
            continue
        # Defenders may NOT Retreat along the Way the Attackers Approached (4.8.3).
        if loser_role == "defender" and approach_origin is not None and dst == approach_origin:
            continue
        retreat_opts.append(dst)
    # A Marching Attacker MUST Retreat to the Locale it Approached from (4.8.3);
    # if that Locale is not a legal target it cannot Retreat (-> Removal).
    if marcher_origin is not None:
        retreat_opts = [marcher_origin] if marcher_origin in retreat_opts else []
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


# --- Shared combat-result helpers (Siege/Storm) -----------------------------

def _value(locale: str) -> int:
    return {"fort": 1, "town": 2, "city": 3}.get(sd.locale(locale)["type"], 0)


def conquer(gs: GameState, locale: str, by_side: str) -> dict[str, Any]:
    """Set a Stronghold to ``by_side``'s control (1.3.1, 4.5.1/4.9.1)."""
    loc = gs.locales[locale]
    info = sd.locale(locale)
    printed = info["allegiance"]
    enemy = "roman" if by_side == "seljuk" else "seljuk"
    loc.siege_markers = 0
    loc.bypass = False
    placed = None
    if printed == "fatimid" and by_side == "roman":
        # Fatimid exception: Roman only removes Seljuk Conquered, places none.
        if loc.conquered_side == "seljuk":
            loc.conquered_side = None
            loc.conquered_count = 0
    elif printed == by_side:
        loc.conquered_side = None  # re-conquering own territory removes enemy markers
        loc.conquered_count = 0
    else:
        loc.conquered_side = by_side
        loc.conquered_count = _value(locale)
        placed = by_side
    # Re-conquering a Friendly Stronghold flips a same-color Ravaged marker (4.9.1 play note)
    if loc.ravaged_side == by_side and printed == by_side:
        loc.ravaged_side = enemy
    if loc.strategic_objective:  # Roman claims a Strategic Objective here (4.5.1/4.9.1)
        gs.holding_boxes.constantinople_roman_vp_markers += 1
        loc.strategic_objective = False
    loc.themata_defending = []  # garrisoning Themata removed from the game
    return {"conquered_by": by_side, "placed_markers": placed}


def ruin(gs: GameState, locale: str) -> dict[str, Any]:
    """Seljuk-only Sack option on a Roman-Empire Stronghold (4.9.1)."""
    loc = gs.locales[locale]
    loc.siege_markers = 0
    loc.bypass = False
    loc.conquered_side = None
    loc.conquered_count = 0
    loc.ruins = True
    loc.ruins_color = "seljuk"
    if loc.strategic_objective:
        gs.holding_boxes.constantinople_roman_vp_markers += 1
        loc.strategic_objective = False
    loc.themata_defending = []
    return {"ruined": locale}


def award_spoils(gs: GameState, locale: str, to_lords: list[str]) -> dict[str, int]:
    """Sack Spoils by Stronghold Value (4.9.1): Coin/Loot/Provender to the first
    Besieging Lord (a player choice; deterministic here)."""
    sh = sd.stronghold_profile(locale)
    if not sh or not to_lords:
        return {}
    spoils = dict(sh["sack_spoils"])
    w = gs.lords[to_lords[0]]
    for k in ("coin", "loot", "provender"):
        setattr(w.assets, k, min(8, getattr(w.assets, k) + spoils.get(k, 0)))
    return spoils


# === Storm (4.9.1) ==========================================================
# Reuses the Strike/Protection model with Storm modifications: Garrison + Walls
# for the defender, Siegeworks for the attacker, all Defending Melee before
# Attacking, no Evade, Hits vs the attacker hit Armored first, a 6-Hit Melee cap
# per Lord, and a Storm length of (number of Siege markers) Rounds. The
# defender losing -> Sack (Conquer/Ruin/Spoils/remove Lords + Themata).

def _storm_protection(unit: str) -> tuple[int, int]:
    """Protection in Storm: Evade is not used, so Turkic Horse is Unarmored."""
    if unit in ("turkic_horse", "militia"):
        return (1, 1)
    return _ARMORED[unit]


def _garrison_column(gs: GameState, locale: str) -> str:
    info = sd.locale(locale)
    if info["allegiance"] == "fatimid":
        return "seljuk"  # Fatimid Caliphate always uses the Seljuk column (4.9.1)
    cur = (gs.locales[locale].conquered_side
           or ("seljuk" if info["allegiance"] == "seljuk" else "roman"))
    return cur


def _build_garrison(gs: GameState, locale: str, attacker_side: str = "seljuk") -> dict[str, int]:
    """Garrison foot units (by column) plus any Themata defenders, as a unit
    pool (4.9.1). Themata are expanded into units; their markers survive if the
    defender wins and are removed on a Sack. Capabilities: Armenian Garrisons
    (R16) adds both columns; Fortified Garrisons (S23) swaps a Garrison Militia
    for Infantry on a Roman Storm."""
    prof = sd.stronghold_profile(locale)
    info = sd.locale(locale)
    col = _garrison_column(gs, locale)
    defender_side = "roman" if attacker_side == "seljuk" else "seljuk"
    g: dict[str, int] = {}
    # Armenian Garrisons (R16): Roman-Conquered Stronghold outside the Roman
    # Empire uses BOTH columns.
    both = (defender_side == "roman" and capabilities.side_has(gs, "roman", "Armenian Garrisons")
            and gs.locales[locale].conquered_side == "roman" and info["allegiance"] != "roman")
    cols = ["roman", "seljuk"] if both else [col]
    for c in cols:
        for u, n in prof["garrison"][c].items():
            if n:
                g[u] = g.get(u, 0) + n
    # Fortified Garrisons (S23): on a Roman Storm, swap 1 Garrison Militia for Infantry.
    if attacker_side == "roman" and capabilities.side_has(gs, "seljuk", "Fortified Garrisons") and g.get("militia", 0) > 0:
        g["militia"] -= 1
        g["infantry"] = g.get("infantry", 0) + 1
    for marker in gs.locales[locale].themata_defending:
        g[marker.unit] = g.get(marker.unit, 0) + marker.symbols
    return g


def resolve_storm(gs: GameState, attacker_ids: list[str], locale: str,
                  ctx: DecisionContext, roller: DiceRoller) -> dict[str, Any]:
    a_side = gs.lords[attacker_ids[0]].side
    d_side = "roman" if a_side == "seljuk" else "seljuk"
    size = _value(locale)
    walls = sd.stronghold_profile(locale)["walls"]            # defender Walls range
    siege = gs.locales[locale].siege_markers                  # = Siegeworks Walls value for attacker
    defender_ids = [lid for lid, l in gs.lords.items()
                    if l.mustered and l.cylinder == locale and l.besieged and l.side == d_side]
    garrison = _build_garrison(gs, locale, a_side)
    garrison_routed: dict[str, int] = {}

    for _lid in attacker_ids + defender_ids:
        gs.lords[_lid].flags["turkic_routed_battle"] = 0
    att = _Side(gs, list(attacker_ids), "attacker")
    deff = _Side(gs, list(defender_ids), "defender")
    # Storm Array: at most one Lord in Front; the rest in Reserve.
    if att.reserve:
        att.front["center"] = att.reserve.pop(0)
    if deff.reserve:
        deff.front["center"] = deff.reserve.pop(0)

    log = []
    attacker_conceded = False
    round_no = 0
    while round_no < siege:
        round_no += 1
        if round_no > 1:
            if ctx.decide("concede", [False, True], {"role": "attacker"}):  # Attacker only (4.9.1)
                attacker_conceded = True
                break
            _storm_reposition(gs, att, deff, size, ctx)
        _storm_strike(gs, att, deff, garrison, garrison_routed, walls, siege, round_no, ctx, roller, log)
        if _garrison_and_lords_routed(gs, deff, garrison):
            break  # defender wiped -> Storm ends, defender loses
        if _all_routed(gs, att):
            break
        _purge_routed(att); _purge_routed(deff)

    defender_routed = _garrison_and_lords_routed(gs, deff, garrison)
    if defender_routed and not attacker_conceded:
        outcome = _sack(gs, attacker_ids, defender_ids, locale, a_side, ctx, roller)
        result = {"winner": "attacker", "sack": outcome}
    else:
        # Attacker loses: no Retreat, no Spoils; Siege continues (4.9.1).
        result = {"winner": "defender", "siege_continues": True}
        _storm_losses(gs, attacker_ids, defender_ids, defender_won=True, roller=roller, ctx=ctx, log=result)
    for lid in attacker_ids + defender_ids:  # Moved/Fought, even Reserve (4.9.1)
        if lid in gs.lords and gs.lords[lid].mustered:
            gs.lords[lid].moved_fought = True
    gs.meta.vp = scenarios.score(gs)
    result.update({"ok": True, "action": "storm", "locale": locale, "rounds": round_no,
                   "strikes": log, "decisions": ctx.trace})
    return result


def _all_routed(gs: GameState, side: _Side) -> bool:
    return all(_is_routed(gs.lords[l]) for l in side.front_lords() + side.reserve) \
        if (side.front_lords() or side.reserve) else True


def _garrison_and_lords_routed(gs: GameState, deff: _Side, garrison: dict[str, int]) -> bool:
    if any(n > 0 for n in garrison.values()):
        return False
    lords = deff.front_lords() + deff.reserve
    return all(_is_routed(gs.lords[l]) for l in lords) if lords else True


def _storm_reposition(gs: GameState, att: _Side, deff: _Side, size: int, ctx: DecisionContext) -> None:
    _purge_routed(att); _purge_routed(deff)
    for side in (att, deff):
        n_front = len(side.front_lords())
        if n_front < size and side.reserve:
            slot = next(s for s in SLOTS if side.front[s] is None)
            choice = ctx.decide("reserve_advance", list(side.reserve), {"role": side.role})
            side.front[slot] = choice
            side.reserve.remove(choice)


def _storm_strike(gs, att, deff, garrison, garrison_routed, walls, siege, round_no, ctx, roller, log):
    # Defending side (Garrison + Lords) strikes first, then Attacker.
    # Missiles, then all Defending Melee, then all Attacking Melee.
    # 1) Defending Missiles (Garrison 0.5 each foot, -1 Armor; + defending Lord missiles)
    d_missile = _garrison_missile_hits(garrison) + _lord_step_hits(gs, deff, "missile", round_no)
    _hit_attacker(gs, att, _round_up(d_missile), "missile", siege, anti_armor=True, roller=roller, ctx=ctx, log=log, step="def_missile", round_no=round_no)
    # 2) Attacking Missiles -> garrison/defender Lord, Walls cancel
    a_missile = _lord_step_hits(gs, att, "missile", round_no)
    eff_walls = _effective_walls(gs, att, walls)
    _hit_defender(gs, deff, garrison, garrison_routed, _round_up(a_missile), "missile", eff_walls, roller, ctx, log, "att_missile", round_no)
    # 3) Defending Melee (Horse then Foot), capped 6/Lord; Garrison foot melee
    d_melee = _garrison_melee_hits(garrison) + _lord_melee_capped(gs, deff, round_no)
    _hit_attacker(gs, att, _round_up(d_melee), "melee", siege, anti_armor=False, roller=roller, ctx=ctx, log=log, step="def_melee", round_no=round_no)
    # 4) Attacking Melee -> garrison/defender Lord
    a_melee = _lord_melee_capped(gs, att, round_no)
    _hit_defender(gs, deff, garrison, garrison_routed, _round_up(a_melee), "melee", _effective_walls(gs, att, walls), roller, ctx, log, "att_melee", round_no)


def _effective_walls(gs, att: _Side, walls: tuple) -> tuple:
    """Siege Weaponry (R20): an Unrouted attacking Lord (incl. Reserve) reduces
    Enemy Walls by 1."""
    lo, hi = walls
    for lid in att.front_lords() + att.reserve:
        if not _is_routed(gs.lords[lid]) and capabilities.lord_has(gs, lid, "Siege Weaponry"):
            return (lo, max(lo, hi - 1))
    return walls


def _round_up(x: float) -> int:
    return int(x + 0.999) if x > 0 else 0


def _garrison_missile_hits(garrison: dict[str, int]) -> float:
    """Garrison Missile Hits (4.9.1 / Strongholds player aid). Each garrison
    unit fires at its own Missile value (Tagmata x1/2, Turkic Horse x1, etc.);
    a foot unit that normally lacks Missiles gains x1/2 because it is a Garrison
    unit. Themata Horse defending as Garrison keep their Missile fire (Playbook
    Example of Play: Tagmata 1/2 + Turkic 1 + Militia 1/2 = x2)."""
    total = 0.0
    for u, n in garrison.items():
        m = _MISSILE.get(u)
        if m is None:
            m = 0.5 if _category(u) == "foot" else 0.0  # foot Garrison units gain x1/2
        total += m * n
    return total


def _garrison_melee_hits(garrison: dict[str, int]) -> float:
    total = 0.0
    for u, n in garrison.items():
        if _category(u) == "foot":
            total += {"infantry": 1.0, "militia": 0.5, "varangian_guard": 3.0}.get(u, 0.0) * n
        else:  # Themata Horse garrison (e.g. Tagmata, Turkic)
            total += _HORSE_MELEE.get(u, 0.0) * n
    return total


def _lord_step_hits(gs: GameState, side: _Side, step: str, round_no: int) -> float:
    table = _strike_table(step, round_no)
    total = 0.0
    for lid in side.front_lords():
        for u, n in _unrouted_units(gs.lords[lid]).items():
            total += table.get(u, 0.0) * n
    return total


def _lord_melee_capped(gs: GameState, side: _Side, round_no: int) -> float:
    total = 0.0
    for lid in side.front_lords():
        units = _unrouted_units(gs.lords[lid])
        h = sum(_HORSE_MELEE.get(u, 0.0) * n for u, n in units.items() if _category(u) == "horse")
        foot = _strike_table("foot_melee", round_no)
        h += sum(foot.get(u, 0.0) * n for u, n in units.items() if _category(u) == "foot")
        if "Shock Tactics" in capabilities.lord_capability_names(gs, lid):  # S4/S6
            h += _math.ceil(units.get("turkic_horse", 0) / 2) * 0.5
        total += min(h, 6.0)  # 6-Hit Melee cap per Lord (4.9.1)
    return total


def _hit_attacker(gs, att: _Side, hits, hit_type, siege, anti_armor, roller, ctx, log, step, round_no):
    """Hits onto the attacker: Siegeworks (Walls=Siege count) cancel, then assign
    Armored-first (4.9.1), Protection (no Evade)."""
    if hits <= 0:
        return
    front = att.front_lords()
    if not front:
        return
    target = gs.lords[front[0]]
    hits = _roll_walls(roller, hits, (1, siege)) if siege > 0 else hits
    routed = _absorb_storm(gs, target, hits, anti_armor, armored_first=True, ctx=ctx, roller=roller)
    log.append({"round": round_no, "step": step, "target": target.id, "hits": hits, "routed": routed})


def _hit_defender(gs, deff: _Side, garrison, garrison_routed, hits, hit_type, walls, roller, ctx, log, step, round_no):
    """Hits onto the defender: Walls cancel, then Garrison units first, then the
    Front defending Lord (4.9.1)."""
    if hits <= 0:
        return
    hits = _roll_walls(roller, hits, walls)
    # Garrison absorbs first.
    while hits > 0 and any(n > 0 for n in garrison.values()):
        unit = next(u for u, n in garrison.items() if n > 0)
        lo, hi = _storm_protection(unit)
        if not (lo <= roller.d6() <= hi):
            garrison[unit] -= 1
            garrison_routed[unit] = garrison_routed.get(unit, 0) + 1
        hits -= 1
    front = deff.front_lords()
    if hits > 0 and front:
        target = gs.lords[front[0]]
        _absorb_storm(gs, target, hits, anti_armor=False, armored_first=False, ctx=ctx, roller=roller)
    log.append({"round": round_no, "step": step, "hits_remaining_after_garrison": max(0, hits)})


def _roll_walls(roller: DiceRoller, hits: int, wrange: tuple[int, int]) -> int:
    """Roll dice = Hits; each roll within the Walls range cancels one Hit (4.8.2)."""
    lo, hi = wrange
    remaining = hits
    for _ in range(hits):
        if lo <= roller.d6() <= hi:
            remaining -= 1
    return max(0, remaining)


def _absorb_storm(gs: GameState, lord: LordState, hits: int, anti_armor: bool, armored_first: bool,
                  ctx: DecisionContext, roller: DiceRoller) -> list[str]:
    routed = []
    reroll_used = False
    norman = capabilities.lord_has(gs, lord.id, "Norman Heavy Cavalry")
    for _ in range(hits):
        avail = [u for u, n in lord.forces.items() if n > 0]
        if not avail:
            break
        if armored_first:  # Storm: Hits vs the attacker hit Armored before Unarmored (4.9.1)
            armored = [u for u in avail if u not in ("turkic_horse", "militia")]
            unit = armored[0] if armored else avail[0]
        else:
            unit = ctx.decide("hit_absorption", avail, {"lord": lord.id})
        lo, hi = capabilities.protection_range(gs, lord.id, unit, "missile" if anti_armor else "melee", storm=True)
        if anti_armor and unit not in ("turkic_horse", "militia"):
            hi = max(lo, hi - 1)  # Garrison Missiles: -1 to target Armor (min 1)
        roll = roller.d6()
        ok = lo <= roll <= hi
        if not ok and norman and unit == "norman_knights" and not reroll_used:
            reroll_used = True
            ok = lo <= roller.d6() <= hi
        if not ok:
            lord.forces[unit] -= 1
            lord.routed[unit] = lord.routed.get(unit, 0) + 1
            routed.append(unit)
            if unit == "turkic_horse":
                lord.flags["turkic_routed_battle"] = int(lord.flags.get("turkic_routed_battle", 0)) + 1
    return routed


def _sack(gs: GameState, attacker_ids, defender_ids, locale, a_side, ctx, roller) -> dict[str, Any]:
    """Defenders lost the Storm (4.9.1): Conquer or (Seljuk, Roman Empire) Ruin,
    Award Spoils, remove losing Lords and Themata."""
    info = sd.locale(locale)
    can_ruin = (a_side == "seljuk" and info["allegiance"] == "roman")
    choice = "conquer"
    if can_ruin:
        choice = ctx.decide("sack_choice", ["conquer", "ruin"], {"locale": locale})
    out = ruin(gs, locale) if choice == "ruin" else conquer(gs, locale, a_side)
    survivors = [l for l in attacker_ids if not _is_routed(gs.lords[l]) and gs.lords[l].mustered]
    out["spoils"] = award_spoils(gs, locale, survivors)
    # Losses first (both sides), then remove losing Lords with no Forces (4.8.5).
    _storm_losses(gs, attacker_ids, defender_ids, defender_won=False, roller=roller, ctx=ctx, log=out)
    out["removed"] = []
    for lid in defender_ids:
        if lid in gs.lords and gs.lords[lid].mustered:
            from . import actions
            actions._disband_beyond(gs, gs.lords[lid])
            out["removed"].append(lid)
    return out


def _storm_losses(gs, attacker_ids, defender_ids, defender_won, roller, ctx, log) -> None:
    """4.9.1: Routed Defending units roll inherent Protection; Routed Attacking
    units are Lost unless they roll a 1 (Harsh)."""
    losses = []
    for lid in attacker_ids:
        losses.append(_loss_roll(gs, gs.lords[lid], harsh=True, roller=roller))
    for lid in defender_ids:
        losses.append(_loss_roll(gs, gs.lords[lid], harsh=False, roller=roller))
    if isinstance(log, dict):
        log.setdefault("losses", []).extend([l for l in losses if l])


def _loss_roll(gs: GameState, lord: LordState, harsh: bool, roller: DiceRoller):
    recovered, lost = {}, {}
    for unit, n in list(lord.routed.items()):
        for _ in range(n):
            roll = roller.d6()
            ok = (roll == 1) if harsh else (lambda lh: lh[0] <= roll <= lh[1])(_natural_protection(unit))
            if ok:
                lord.forces[unit] = lord.forces.get(unit, 0) + 1
                recovered[unit] = recovered.get(unit, 0) + 1
            else:
                lost[unit] = lost.get(unit, 0) + 1
        lord.routed[unit] = 0
    lord.routed = {u: n for u, n in lord.routed.items() if n > 0}
    return {"lord": lord.id, "recovered": recovered, "lost": lost, "harsh": harsh} if (recovered or lost) else None


# === Sally (4.9.2) ==========================================================

def resolve_sally(gs: GameState, sallying_ids: list[str], besieger_ids: list[str], locale: str,
                  ctx: DecisionContext, roller: DiceRoller) -> dict[str, Any]:
    """A Besieged Lord Attacks the Besiegers (4.9.2). Battle rules, but the
    Besiegers (defenders here) get Siegeworks as Walls and the Sallying side
    gets no Walls/Garrison. Storm-like Array/Reposition. Raid on a failed Sally."""
    gs.meta.active_lord = sallying_ids[0]
    siege = gs.locales[locale].siege_markers
    for _lid in sallying_ids + besieger_ids:
        gs.lords[_lid].flags["turkic_routed_battle"] = 0
    att = _Side(gs, list(sallying_ids), "attacker")   # Sallying side attacks
    deff = _Side(gs, list(besieger_ids), "defender")  # Besiegers defend
    if att.reserve:
        att.front["center"] = att.reserve.pop(0)
    if deff.reserve:
        deff.front["center"] = deff.reserve.pop(0)
    size = _value(locale)
    log = []
    conceded = False
    round_no = 0
    while round_no < 30:
        round_no += 1
        if round_no > 1:
            if ctx.decide("concede", [False, True], {"role": "attacker"}):
                conceded = True
                break
            _storm_reposition(gs, att, deff, size, ctx)
        # Sally Strike order follows Storm (Defending then Attacking); Besiegers
        # benefit from Siegeworks (Walls = Siege count); Sallying side has none.
        d_missile = _lord_step_hits(gs, deff, "missile", round_no)
        _absorb_simple(gs, att, _round_up(d_missile), "missile", 0, roller, ctx, log, "def_missile", round_no)
        a_missile = _lord_step_hits(gs, att, "missile", round_no)
        _absorb_simple(gs, deff, _round_up(a_missile), "missile", siege, roller, ctx, log, "att_missile", round_no)
        d_melee = _lord_melee_capped(gs, deff, round_no)
        _absorb_simple(gs, att, _round_up(d_melee), "melee", 0, roller, ctx, log, "def_melee", round_no)
        a_melee = _lord_melee_capped(gs, att, round_no)
        _absorb_simple(gs, deff, _round_up(a_melee), "melee", siege, roller, ctx, log, "att_melee", round_no)
        if _all_routed(gs, deff) or _all_routed(gs, att):
            break
        _purge_routed(att); _purge_routed(deff)

    besiegers_routed = _all_routed(gs, deff)
    if besiegers_routed and not conceded:
        # Losing Besiegers Retreat; the Siege ends.
        winner = "sally"
        _end_sally_besiegers_lose(gs, besieger_ids, locale, ctx, roller)
        gs.locales[locale].siege_markers = 0
        gs.locales[locale].bypass = False
        for lid in sallying_ids:  # Sallying Lords stay (Withdraw back inside)
            gs.lords[lid].besieged = True
    else:
        # Sally fails: Sallying Lords Withdraw back inside; Raid removes all but
        # one Siege marker (4.9.2).
        winner = "besiegers"
        for lid in sallying_ids:
            gs.lords[lid].besieged = True
        gs.locales[locale].siege_markers = 1  # Raid: remove all but one Siege marker (4.9.2)
    # Losses for both sides.
    for lid in sallying_ids + besieger_ids:
        if lid in gs.lords:
            _loss_roll(gs, gs.lords[lid], harsh=False, roller=roller)
    for lid in sallying_ids + besieger_ids:
        if lid in gs.lords and gs.lords[lid].mustered and _is_routed(gs.lords[lid]):
            from . import actions
            actions._disband_beyond(gs, gs.lords[lid])
    for lid in sallying_ids + besieger_ids:
        if lid in gs.lords and gs.lords[lid].mustered:
            gs.lords[lid].moved_fought = True
    gs.meta.vp = scenarios.score(gs)
    return {"ok": True, "action": "sally", "locale": locale, "winner": winner,
            "rounds": round_no, "strikes": log, "decisions": ctx.trace}


def _end_sally_besiegers_lose(gs: GameState, besieger_ids, locale, ctx, roller) -> None:
    from . import map as gmap
    for lid in besieger_ids:
        lord = gs.lords[lid]
        if _is_routed(lord):
            continue
        # Losing Besiegers Retreat normally (4.8.3): adjacent Locale free of enemy
        # Lords and of unbesieged/unbypassed enemy Strongholds.
        opts = [e["to"] for e in gmap.ways_from(locale)
                if not _retreat_blocked(gs, e["to"], lord.side)]
        if opts:
            lord.cylinder = ctx.decide("retreat", opts, {"lord": lid})


def _absorb_simple(gs, side: _Side, hits, hit_type, walls_value, roller, ctx, log, step, round_no):
    """Battle-style Hit absorption for Sally, with optional Siegeworks Walls."""
    if hits <= 0:
        return
    front = side.front_lords()
    if not front:
        return
    target = gs.lords[front[0]]
    if walls_value > 0:
        hits = _roll_walls(roller, hits, (1, walls_value))
    routed = []
    for _ in range(hits):
        avail = [u for u, n in target.forces.items() if n > 0]
        if not avail:
            break
        unit = ctx.decide("hit_absorption", avail, {"lord": target.id})
        lo, hi = capabilities.protection_range(gs, target.id, unit, hit_type, storm=False)
        if not (lo <= roller.d6() <= hi):
            target.forces[unit] -= 1
            target.routed[unit] = target.routed.get(unit, 0) + 1
            routed.append(unit)
            if unit == "turkic_horse":
                target.flags["turkic_routed_battle"] = int(target.flags.get("turkic_routed_battle", 0)) + 1
    log.append({"round": round_no, "step": step, "target": target.id, "hits": hits, "routed": routed})
