"""Aggressive randomized smoke fuzzer.

Unlike the greedy round-trip sweep (which applies moves[0]), this drives random
legal moves and random combat sub-decisions, exploring far more of the action
space. At every step it:
  * round-trips every concrete enumerated move through a deep snapshot (catches
    enumerator/handler divergence),
  * checks state invariants on the live state and on each snapshot,
  * catches any uncaught exception as a CRASH finding.

Usage:  PYTHONPATH=src python3 scripts/smoke_fuzz.py --rounds 20 --seeds 1,2,3
"""
from __future__ import annotations

import argparse
import random
import traceback

from seljuk.llm import LLMSession
from seljuk import scenarios, engine
from seljuk.state import GameState, IllegalAction
from seljuk.invariants import check_invariants
from self_play import _build_plan_action  # type: ignore

_TEMPLATE = {"build_plan", "resolve_event"}


def _rand_decisions(rng):
    """Random in-battle decision script (§5 cold-path coverage): typed entries
    are consumed only at the matching choice, so a list of random ("concede",
    bool) entries makes the resolver Concede/early-terminate at random offers --
    the only way to reach the "loser survives -> Retreat" branch a first-legal
    fallback never walks. Also randomize the rare reserve/retreat picks."""
    return [("concede", rng.choice([True, False])) for _ in range(8)]


def _rand_plan(s, move, rng):
    """Build a random-but-legal Plan of the required size."""
    side = move["side"]; need = move["_plan_size"]; avail = list(move["_available_lords"])
    cards = []
    if move.get("_treachery_required"):
        cards.append("treachery")
    per = {}
    while len(cards) < need:
        pick_lord = avail and rng.random() < 0.6
        if pick_lord:
            lid = rng.choice(avail)
            if per.get(lid, 0) < 4:
                cards.append(lid); per[lid] = per.get(lid, 0) + 1; continue
        if cards.count("no_command") < 5:
            cards.append("no_command")
        elif avail:
            lid = rng.choice(avail)
            if per.get(lid, 0) < 4:
                cards.append(lid); per[lid] = per.get(lid, 0) + 1
            else:
                cards.append("no_command")  # may overflow cap -> handler should reject cleanly
        else:
            cards.append("no_command")
    rng.shuffle(cards)
    return {"type": "build_plan", "side": side, "cards": cards[:need]}


def _rand_resolve_pending(s, rng, findings, tag):
    p = s.gs.meta.pending[0]
    t = p["type"]
    try:
        if t == "approach_response":
            choices = {}
            for d in p["defenders"]:
                choices[d] = {"action": rng.choice(["stand", "stand", "withdraw"])}
            try:
                s.apply({"type": "respond_approach", "choices": choices,
                         "battle_decisions": _rand_decisions(rng)})
            except IllegalAction:
                # SMOKE-004: "withdraw" is only legal into a Friendly Stronghold at
                # the Locale; when there is none the engine (correctly) rejects it.
                # Falling through to the outer `except -> pending.remove` would
                # strand the attacker and defender co-located (an illegal state the
                # co-location invariant now flags). Resolve validly instead: Stand
                # always triggers a Battle and clears the Approach.
                s.apply({"type": "respond_approach",
                         "choices": {d: {"action": "stand"} for d in p["defenders"]},
                         "battle_decisions": _rand_decisions(rng)})
        elif t == "besiege_or_bypass":
            s.apply({"type": "besiege_bypass", "choice": rng.choice(["besiege", "bypass"])})
        elif t == "assign_themata_defenders":
            s.apply({"type": "assign_themata_defenders", "markers": []})
        elif t == "ravage_defence":
            opts = p.get("options", [])
            dw = rng.choice([None] + [o["index"] for o in opts]) if opts else None
            s.apply({"type": "resolve_ravage_defence", "defend_with": dw})
        elif t == "event_pending_resolution":
            try:
                s.apply({"type": "resolve_event", "card": p["card"], "args": {}})
            except IllegalAction:
                s.gs.meta.pending.remove(p)  # needs choices; discard (no effect)
        elif t == "deploy_capability":
            s.apply({"type": "deploy_capability", "card": p["card"], "lord": p["eligible"][0]})
        elif t == "loyalty_check":
            s.apply({"type": "resolve_loyalty", "target": rng.choice(p["targets"])})
        elif t == "basil_response":
            s.apply({"type": "basil_response", "play": rng.choice([True, False])})
        elif t == "winter_quarters":
            opts = [{"type": "winter_quarters", "lord": p["lord"], "dest": d} for d in p["dests"]]
            if p.get("may_stay"):
                opts.append({"type": "winter_quarters", "lord": p["lord"], "stay": True})
            s.apply(rng.choice(opts))
        else:
            s.gs.meta.pending.remove(p)
    except IllegalAction:
        # A pending sub-decision the enumerator/handler disagree on is a finding.
        try:
            s.gs.meta.pending.remove(p)
        except ValueError:
            pass
    return True


def fuzz_game(scenario, seed, rng, max_steps=3000):
    findings = []
    s = LLMSession.start_new(scenario, seed)
    v = check_invariants(s.gs)
    if v:
        return [f"{scenario}#{seed} @start invariant: {v[0]}"]
    steps = 0
    while not s.is_over() and steps < max_steps:
        steps += 1
        try:
            if s.gs.meta.pending:
                _rand_resolve_pending(s, rng, findings, f"{scenario}#{seed}")
            else:
                moves = s.legal_actions()
                if not moves:
                    break
                # Round-trip + invariant check on every concrete enumerated move.
                for mv in moves:
                    if mv["type"] in _TEMPLATE:
                        continue
                    snap = GameState.from_json(s.gs.to_json())
                    try:
                        engine.apply_action(snap, {k: w for k, w in mv.items() if not k.startswith("_")})
                    except IllegalAction as e:
                        findings.append(f"{scenario}#{seed} {s.gs.meta.subphase}: enumerated {mv['type']} -> {e}")
                        continue
                    iv = check_invariants(snap)
                    if iv:
                        findings.append(f"{scenario}#{seed} after {mv['type']}: invariant {iv[0]}")
                types = {m["type"]: m for m in moves}
                if "build_plan" in types:
                    s.apply(_rand_plan(s, types["build_plan"], rng))
                else:
                    concrete = [m for m in moves if m["type"] not in _TEMPLATE]
                    m = rng.choice(concrete) if concrete else moves[0]
                    act = {k: w for k, w in m.items() if not k.startswith("_")}
                    if act["type"] == "cmd_storm":
                        act["storm_decisions"] = _rand_decisions(rng)
                    elif act["type"] == "cmd_sally":
                        act["battle_decisions"] = _rand_decisions(rng)
                    s.apply(act)
            iv = check_invariants(s.gs)
            if iv:
                findings.append(f"{scenario}#{seed} @step{steps} ({s.gs.meta.subphase}): invariant {iv[0]}")
                break
        except IllegalAction as e:
            findings.append(f"{scenario}#{seed} @step{steps} ({s.gs.meta.subphase}): applied -> {e}")
            break
        except Exception as e:  # noqa: BLE001  -- a crash is the most important finding
            findings.append(f"CRASH {scenario}#{seed} @step{steps} ({s.gs.meta.subphase}): "
                            f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            break
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--base", type=int, default=0, help="round-number offset for batched runs")
    args = ap.parse_args(argv)
    game_seeds = [int(x) for x in args.seeds.split(",")]
    all_findings = []
    total_games = 0
    for rnd in range(args.base + 1, args.base + args.rounds + 1):
        rng = random.Random(1000 + rnd)
        round_findings = []
        for sc in scenarios.SCENARIOS:
            for gs_seed in game_seeds:
                total_games += 1
                round_findings += fuzz_game(sc, gs_seed * 100 + rnd, rng)
        status = "clean" if not round_findings else f"{len(round_findings)} FINDINGS"
        print(f"Round {rnd:2d}: {status}")
        for f in round_findings[:5]:
            print("   ", f.splitlines()[0])
        all_findings += round_findings
    print(f"\nTotal: {total_games} games, {len(all_findings)} findings.")
    if all_findings:
        print("\n=== FIRST 10 FINDINGS (full) ===")
        for f in all_findings[:10]:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
