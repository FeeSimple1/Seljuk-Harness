"""Standalone enumerator/handler round-trip sweep (Phase 5; CROSS_PROJECT_LESSONS §2).

Drives self-play across scenarios/seeds and, at every state, replays each
concrete enumerated move through apply_action on a deep snapshot, reporting any
move the enumerator offers that the handler rejects. Bias: this is the single
highest-yield guard against the enumerator and handlers silently diverging.

Usage:  PYTHONPATH=src python3 scripts/roundtrip_sweep.py --seeds 1,2,3
"""
from __future__ import annotations

import argparse

from seljuk.llm import LLMSession
from seljuk import scenarios
from seljuk.state import GameState, IllegalAction
from self_play import _resolve_pending, _build_plan_action  # type: ignore

# moves the consumer must parameterise (not directly snapshot-appliable as-is)
_TEMPLATE = {"build_plan", "resolve_event"}


def sweep_game(scenario: str, seed: int, max_steps: int = 4000) -> list[str]:
    findings: list[str] = []
    s = LLMSession.start_new(scenario, seed)
    steps = 0
    while not s.is_over() and steps < max_steps:
        steps += 1
        if s.gs.meta.pending:
            _resolve_pending(s)
            continue
        moves = s.legal_actions()
        if not moves:
            break
        for mv in moves:
            if mv["type"] in _TEMPLATE:
                continue
            snap = GameState.from_json(s.gs.to_json())
            try:
                from seljuk import engine
                engine.apply_action(snap, {k: v for k, v in mv.items() if not k.startswith("_")})
            except IllegalAction as e:
                findings.append(f"{scenario}#{seed} {s.gs.meta.subphase}: {mv['type']} -> {e}")
        types = {m["type"]: m for m in moves}
        try:
            if "build_plan" in types:
                s.apply(_build_plan_action(s, types["build_plan"]))
            elif "pass_step" in types:
                s.apply({"type": "pass_step"})
            elif "end_activation" in types:
                s.apply({"type": "end_activation"})
            else:
                s.apply(moves[0])
        except IllegalAction as e:
            # A divergence-detector must report, not abort: record and stop this game.
            findings.append(f"{scenario}#{seed} {s.gs.meta.subphase}: advancing apply -> {e}")
            break
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3")
    a = ap.parse_args(argv)
    seeds = [int(x) for x in a.seeds.split(",")]
    all_findings = []
    for sc in scenarios.SCENARIOS:
        for sd in seeds:
            all_findings += sweep_game(sc, sd)
    if all_findings:
        print(f"{len(all_findings)} findings:")
        for f in all_findings[:50]:
            print("  ", f)
        return 1
    print(f"round-trip sweep clean across {len(scenarios.SCENARIOS)} scenarios x {len(seeds)} seeds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
