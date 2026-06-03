"""Extended self-play soak across Optional Rule (6.0) combinations.

Replays the self-play driver with each option profile and runs check_invariants
after every step, so a rules-state violation introduced by an optional rule is
caught the moment it happens (not just at termination). Reports per (scenario,
seed, profile): terminal?, winner, steps, and any invariant violations.
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from self_play import _resolve_pending, _build_plan_action      # noqa: E402
from seljuk import scenarios as S                                 # noqa: E402
from seljuk.invariants import check_invariants                   # noqa: E402
from seljuk.llm.session import LLMSession                         # noqa: E402


def soak_game(scenario: str, seed: int, options: dict, max_steps: int = 4000) -> dict:
    s = LLMSession.start_new(scenario, seed, options=options)
    steps = 0
    violations: list[str] = []
    while not s.is_over() and steps < max_steps:
        steps += 1
        if _resolve_pending(s):
            bad = check_invariants(s.gs)
            if bad:
                violations.append(f"step{steps}(pending): {bad[0]}")
            continue
        moves = s.legal_actions()
        if not moves:
            break
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
        except Exception as e:  # noqa: BLE001 -- record, don't abort the batch
            violations.append(f"step{steps} EXC: {type(e).__name__}: {e}")
            break
        bad = check_invariants(s.gs)
        if bad:
            violations.append(f"step{steps}: {bad[0]}")
            if len(violations) > 5:
                break
    return {"scenario": scenario, "seed": seed, "options": options, "steps": steps,
            "over": s.is_over(), "winner": s.winner(), "violations": violations}


# Mechanically-active profiles (hidden_mats only affects the view, so one sample).
PROFILES = {
    "standard": {},
    "vassal_service": {"vassal_service": True},
    "sim_melee": {"simultaneous_horse": "melee"},
    "sim_missiles": {"simultaneous_horse": "missiles"},
    "sim_both": {"simultaneous_horse": "both"},
    "deadlier_missiles": {"deadlier_seljuk_missiles": True},
    "all_on": {"hidden_mats": True, "vassal_service": True,
               "simultaneous_horse": "both", "deadlier_seljuk_missiles": True},
}


def run(profiles, scenarios, seeds) -> int:
    fails = 0
    for pname in profiles:
        opts = PROFILES[pname]
        for sc in scenarios:
            for sd in seeds:
                r = soak_game(sc, sd, opts)
                ok = r["over"] and r["winner"] in ("roman", "seljuk", "draw") and not r["violations"]
                tag = "ok " if ok else "FAIL"
                if not ok:
                    fails += 1
                    print(f"[{tag}] {pname:18} {sc:28} seed={r['seed']} "
                          f"steps={r['steps']} over={r['over']} win={r['winner']} "
                          f"viol={r['violations'][:2]}")
        print(f"  done profile={pname} scenarios={len(scenarios)} seeds={len(seeds)}")
    print(f"TOTAL FAILS: {fails}")
    return fails


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", default=",".join(PROFILES))
    ap.add_argument("--scenarios", default=",".join(S.SCENARIOS))
    ap.add_argument("--seeds", default="1,2,3,4,5")
    a = ap.parse_args(argv)
    profiles = a.profiles.split(",")
    scenarios = a.scenarios.split(",")
    seeds = [int(x) for x in a.seeds.split(",")]
    return 1 if run(profiles, scenarios, seeds) else 0


if __name__ == "__main__":
    raise SystemExit(main())
