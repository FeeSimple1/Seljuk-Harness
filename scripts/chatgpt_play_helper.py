"""ChatGPT-in-sandbox play helper for the Seljuk harness.

Lets ChatGPT (GPT-5.x) play Seljuk in its own Python sandbox -- no API key, no
network -- while a baked-in instrumentation layer auto-captures every engine
anomaly (illegal action, crash, stall, broken invariant). Adapted from the
Nevsky cross-harness "ChatGPT plays your harness" template.

ChatGPT IS the player: it calls nv.show() to see the active side's briefing and
a NUMBERED legal-action list, decides, calls nv.apply(N), and loops. The menu is
the validated palette (engine.validated_legal_moves): every concrete move is
probed on a throwaway deep copy, handler-rejected moves are dropped AND logged as
over-enumeration diagnostics, so the model never sees an illegal move.

Quick start (in the ChatGPT sandbox / locally):
    import sys; sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
    import chatgpt_play_helper as nv
    nv.start("manzikert", seed=1)      # shortest scenario; see nv.SCENARIOS
    nv.show(); nv.apply(0); nv.auto()  # ... play to a terminal state ...
    nv.findings_report()

NOTE: Seljuk actions are FLAT dicts -- {"type": "cmd_march", "lord": "alp_arslan",
"to": "ani", "way_type": "road"} -- not {"type","args"}. Pass raw actions to
nv.apply() in that flat shape. Four moves are TEMPLATES the consumer must build:
build_plan, resolve_event, respond_approach, assign_themata_defenders (shown with
"<template>"); construct them with nv.apply({...}) using the hint fields.
"""
from __future__ import annotations

import json
import traceback

# ===================== Seljuk wiring =====================
from seljuk.llm import LLMSession
from seljuk import engine, scenarios
from seljuk.state import IllegalAction
from seljuk.invariants import check_invariants

SCENARIOS = list(scenarios.SCENARIOS)
_TEMPLATES = engine._PALETTE_TEMPLATES  # build_plan / resolve_event / respond_approach / assign_themata_defenders

_S = {"session": None, "scenario": None, "history": [], "findings": [], "turn": 0}


def _active_side():
    """Whose decision is owed: a pending sub-decision's owner, else the active
    player (a March's Approach is answered by the inactive defender)."""
    gs = _S["session"].gs
    if gs.meta.pending:
        p = gs.meta.pending[0]
        return p.get("_owed_by") or p.get("side") or gs.meta.active_player
    return gs.meta.active_player


def _menu(log_drops=True):
    """Validated palette via the engine's §2 probe-and-drop. Returns kept moves
    (templates flagged _unvalidated); records each drop as an over_enum finding."""
    gs = _S["session"].gs
    moves, dropped = engine.validated_legal_moves(gs)
    if log_drops:
        for d in dropped:
            _S["findings"].append({"kind": "over_enum_filtered", "turn": _S["turn"], **d})
    return moves


def _strip(move):
    """A ready-to-apply flat action: the move minus its _-prefixed hint fields."""
    return {k: v for k, v in move.items() if not k.startswith("_")}


def _record_invariants():
    try:
        bad = check_invariants(_S["session"].gs) or []
    except Exception as e:  # noqa: BLE001
        _S["findings"].append({"kind": "invariant_crash", "turn": _S["turn"],
                               "error": f"{type(e).__name__}: {e}"[:200]})
        return ["<crash>"]
    for v in bad:
        _S["findings"].append({"kind": "invariant", "turn": _S["turn"], "violation": v})
    return bad


def start(scenario, seed=1):
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {SCENARIOS}")
    _S.update(session=LLMSession.start_new(scenario, seed), scenario=scenario,
              history=[], findings=[], turn=0)
    print(f"started {scenario} (seed={seed}). You play BOTH sides. Call nv.show().")
    return show()


def show():
    s = _S["session"]
    if s.is_over():
        print("GAME OVER:", s.winner())
        return []
    side = _active_side()
    moves = _menu()
    gs = s.meta if False else s.gs
    print(f"\n===== turn {_S['turn']} | active: {side} | "
          f"{gs.meta.subphase} | box {gs.meta.calendar_box}/{gs.meta.final_box} =====")
    print(s.briefing())
    print(f"\nLEGAL ACTIONS ({len(moves)}):")
    for i, m in enumerate(moves):
        params = {k: v for k, v in m.items() if not k.startswith("_") and k != "type"}
        if m.get("type") == "build_plan":
            tag = "  <template: nv.plan([...]) -- see nv.plan_help()>"
        elif m.get("_unvalidated"):
            tag = "  <template: build with nv.apply({...})>"
        else:
            tag = ""
        hint = m.get("_desc", "")
        print(f"  [{i}] {m.get('type','?')}  {json.dumps(params, default=str)}{tag}"
              + (f"   // {hint}" if hint else ""))
    if not moves:
        _S["findings"].append({"kind": "no_legal_moves", "turn": _S["turn"], "side": side,
                               "subphase": gs.meta.subphase})
        print("!! no legal moves (stall) -- recorded")
    return moves


def apply(choice):
    s = _S["session"]
    side = _active_side()
    moves = _menu(log_drops=False)
    if isinstance(choice, int):
        if not (0 <= choice < len(moves)):
            print(f"index {choice} out of range (0..{len(moves)-1}); pass a valid index or a flat action dict")
            return show()
        m = moves[choice]
        if m.get("_unvalidated"):
            params = {k: v for k, v in m.items() if not k.startswith("_") and k != "type"}
            print(f"[{choice}] {m['type']} is a TEMPLATE -- it needs parameters you supply. "
                  f"Build it with nv.apply({{'type': '{m['type']}', ...}}). Hints: "
                  f"{json.dumps({k: v for k, v in m.items() if k.startswith('_') and k != '_desc'}, default=str)}")
            return moves
        action = _strip(m)
    elif isinstance(choice, dict):
        action = dict(choice)
    else:
        raise TypeError("choice must be an int index or a flat action dict")
    try:
        result = s.apply(action)
    except IllegalAction as e:
        _S["findings"].append({"kind": "illegal_action", "turn": _S["turn"], "side": side,
                               "action": action, "code": e.code, "reason": e.message[:160]})
        print(f"!! ILLEGAL (recorded): {e.code}: {e.message[:160]}")
        return show()
    except Exception as e:  # noqa: BLE001
        _S["findings"].append({"kind": "exception", "turn": _S["turn"], "side": side,
                               "action": action, "etype": type(e).__name__,
                               "msg": str(e)[:200], "tb": traceback.format_exc()[-700:]})
        print(f"!! EXCEPTION (recorded): {type(e).__name__}: {e}")
        return
    _S["history"].append({"turn": _S["turn"], "side": side, "action": action})
    _S["turn"] += 1
    if _record_invariants():
        print("!! INVARIANT VIOLATION (recorded)")
    print(f"applied: {action['type']} ({side})")
    return show()


def auto(max_steps=300):
    """Auto-apply purely-forced turns (exactly one concrete legal action) so you
    skip boilerplate; stop at the next real choice, a template, or game end."""
    s = _S["session"]
    n = 0
    while n < max_steps and not s.is_over():
        moves = _menu(log_drops=False)
        concrete = [m for m in moves if not m.get("_unvalidated")]
        if len(moves) != 1 or len(concrete) != 1:
            break
        try:
            s.apply(_strip(concrete[0]))
        except Exception as e:  # noqa: BLE001
            _S["findings"].append({"kind": "exception", "turn": _S["turn"],
                                   "action": _strip(concrete[0]), "etype": type(e).__name__,
                                   "msg": str(e)[:200], "tb": traceback.format_exc()[-700:]})
            print(f"!! EXCEPTION during auto (recorded): {type(e).__name__}: {e}")
            return
        _S["turn"] += 1
        n += 1
        _record_invariants()
    print(f"auto-advanced {n} forced turn(s).")
    return show()


def findings_report():
    notable_kinds = ("illegal_action", "over_enum_filtered", "exception", "exception_in_probe",
                     "no_legal_moves", "invariant", "invariant_crash")
    notable = [f for f in _S["findings"] if f["kind"] in notable_kinds]
    print(f"\n===== FINDINGS: {len(_S['findings'])} total, {len(notable)} notable =====")
    for f in notable:
        print("  ", json.dumps(f, default=str)[:240])
    if not notable:
        print("  (none -- no engine anomalies on this trajectory)")
    return _S["findings"]


# --- detail lookups & a build_plan helper (ease-of-use; no game effect) ------

def state(side=None):
    """Structured, hidden-information-filtered state for `side` (default: the
    side currently to act). Opponent deck/hand/unrevealed Plan are masked."""
    st = _S["session"].state(side or _active_side())
    print(json.dumps(st, default=str, indent=2)[:4000])
    return st


def pending():
    """The sub-decisions owed right now (resolve these before normal moves)."""
    p = list(_S["session"].gs.meta.pending)
    print(json.dumps(p, default=str, indent=2) if p else "no pending sub-decisions")
    return p


def lookup_card(card_id):
    """Full text/data for an Arts of War card (e.g. 'S1', 'R14')."""
    d = _S["session"].lookup_card(card_id)
    print(json.dumps(d, default=str, indent=2)[:2500])
    return d


def lookup_lord(lord_id):
    """Full stats for a Lord (ratings, seats, starting Forces/Assets, etc.)."""
    d = _S["session"].lookup_lord(lord_id)
    print(json.dumps(d, default=str, indent=2)[:2500])
    return d


def map(locale=None):  # noqa: A001 -- intentional nv.map() convenience name
    """Adjacency peek for routing Marches: ways_from(locale) (each {to,type,...}),
    or every Locale's neighbor list when called with no argument."""
    from seljuk import map as gmap, static_data as sd
    out = gmap.ways_from(locale) if locale is not None else {lid: gmap.neighbors(lid)
                                                             for lid in sd.all_locale_ids()}
    print(json.dumps(out, default=str, indent=2)[:3500])
    return out


def plan_help():
    """Show what the current Campaign Plan requires (size, available Lords, caps)."""
    t = next((m for m in engine.legal_moves(_S["session"].gs) if m["type"] == "build_plan"), None)
    if not t:
        print("No Campaign Plan is owed right now -- call nv.show().")
        return None
    treach = ("exactly one 'treachery' REQUIRED" if t["_treachery_required"]
              else "'treachery' NOT allowed this turn")
    print(f"Build a {t['_plan_size']}-card ordered Plan for {t['side']} (play order):")
    print(f"  - Lord ids (<=4 cards each): {t['_available_lords']}")
    print(f"  - 'no_command' (<=5);  {treach}")
    print(f"  Then: nv.plan([...])   # {t['_plan_size']} entries")
    return t


def plan(cards):
    """Build & apply the current Campaign Plan from an ordered list of entries
    (Lord ids / 'no_command' / 'treachery'). Pre-validates the common mistakes
    (size, unknown Lord, >4 per Lord, the treachery rule) with a clear message,
    so a planning slip is not mistaken for an engine bug."""
    from collections import Counter
    t = next((m for m in engine.legal_moves(_S["session"].gs) if m["type"] == "build_plan"), None)
    if not t:
        print("No build_plan is owed right now -- call nv.show().")
        return show()
    cards = list(cards)
    need, avail = t["_plan_size"], set(t["_available_lords"])
    errs = []
    if len(cards) != need:
        errs.append(f"need exactly {need} cards, got {len(cards)}")
    c = Counter(cards)
    if t["_treachery_required"] and c.get("treachery", 0) != 1:
        errs.append("exactly one 'treachery' is required this turn")
    if not t["_treachery_required"] and c.get("treachery", 0):
        errs.append("'treachery' is not allowed this turn")
    for k, n in c.items():
        if k in ("no_command", "treachery"):
            continue
        if k not in avail:
            errs.append(f"{k!r} is not an available Lord (choose from {sorted(avail)})")
        elif n > 4:
            errs.append(f"at most 4 cards per Lord ({n} given for {k})")
    if errs:
        print("Plan invalid: " + "; ".join(errs))
        return plan_help()
    return apply({"type": "build_plan", "side": t["side"], "cards": cards})


def save(path="chatgpt_game.json"):
    import pathlib
    s = _S["session"]
    data = {"scenario": _S["scenario"], "history": _S["history"], "findings": _S["findings"],
            "state_json": s.gs.to_json()}
    pathlib.Path(path).write_text(json.dumps(data, indent=2, default=str))
    print("saved ->", path)
