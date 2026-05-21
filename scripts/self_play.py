"""Greedy self-play driver (Phase 5; not part of the shipped harness).

Drives a full game with a minimal deterministic policy: resolve any pending
sub-decision, build a simple Plan, then Pass Levy steps and End each Campaign
activation, letting turns advance to a terminal state. Its purpose is
bug-finding and end-to-end exercise across Levy + Campaign + End-Campaign +
Winter + game end (CROSS_PROJECT_LESSONS.md: agents surface stalls and
unhandled IllegalActions). A combat-aggressive variant can build on this.

Usage:  PYTHONPATH=src python3 scripts/self_play.py <scenario> --seed N
"""
from __future__ import annotations

import argparse
import sys

from seljuk.llm import LLMSession
from seljuk import campaign, static_data as sd
from seljuk.state import IllegalAction


def _resolve_pending(s: LLMSession) -> bool:
    pend = s.gs.meta.pending
    if not pend:
        return False
    p = pend[0]
    t = p["type"]
    try:
        if t == "deploy_capability":
            s.apply({"type": "deploy_capability", "card": p["card"], "lord": p["eligible"][0]})
        elif t == "event_pending_resolution":
            try:
                s.apply({"type": "resolve_event", "card": p["card"], "args": {}})
            except IllegalAction:
                s.gs.meta.pending.remove(p)  # needs choices we won't make here -> discard (no effect)
        elif t == "approach_response":
            s.apply({"type": "respond_approach",
                     "choices": {d: {"action": "stand"} for d in p["defenders"]}})
        elif t == "besiege_or_bypass":
            s.apply({"type": "besiege_bypass", "choice": "besiege"})
        elif t == "assign_themata_defenders":
            s.apply({"type": "assign_themata_defenders", "markers": []})
        elif t == "ravage_defence":
            s.apply({"type": "resolve_ravage_defence", "defend_with": None})
        else:
            s.gs.meta.pending.remove(p)
        return True
    except IllegalAction:
        s.gs.meta.pending.remove(p)
        return True


def _build_plan_action(s: LLMSession, move: dict) -> dict:
    side = move["side"]
    avail = move["_available_lords"]
    need = move["_plan_size"]
    cards, per = [], {}
    i = 0
    while len(cards) < need:
        if avail:
            lid = avail[i % len(avail)]; i += 1
            if per.get(lid, 0) < 4:
                cards.append(lid); per[lid] = per.get(lid, 0) + 1; continue
        if cards.count("no_command") < 5 or not avail:
            cards.append("no_command")
        else:
            cards.append(avail[i % len(avail)]); i += 1
    return {"type": "build_plan", "side": side, "cards": cards}


def play_game(scenario: str, seed: int = 1, max_steps: int = 4000) -> dict:
    s = LLMSession.start_new(scenario, seed)
    steps = 0
    while not s.is_over() and steps < max_steps:
        steps += 1
        if _resolve_pending(s):
            continue
        moves = s.legal_actions()
        if not moves:
            break
        types = {m["type"]: m for m in moves}
        if "build_plan" in types:
            s.apply(_build_plan_action(s, types["build_plan"]))
        elif "pass_step" in types:
            s.apply({"type": "pass_step"})
        elif "end_activation" in types:
            s.apply({"type": "end_activation"})
        else:
            s.apply(moves[0])
    return {"scenario": scenario, "seed": seed, "steps": steps,
            "over": s.is_over(), "winner": s.winner(),
            "phase": s.gs.meta.phase, "box": s.gs.meta.calendar_box}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-steps", type=int, default=4000)
    a = ap.parse_args(argv)
    res = play_game(a.scenario, a.seed, a.max_steps)
    print(res)
    return 0 if res["over"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
