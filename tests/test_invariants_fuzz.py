"""Property fuzzing: state invariants must hold after EVERY step of self-play,
across all scenarios and many seeds. A second safety net beyond the
enumerator/handler round-trip sweep."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from seljuk.llm import LLMSession
from seljuk import scenarios as S, engine
from seljuk.invariants import check_invariants
from seljuk.state import GameState, IllegalAction
from self_play import _resolve_pending, _build_plan_action  # noqa: E402


def _fuzz_one(scenario: str, seed: int, max_steps: int = 4000) -> list[str]:
    """Play one game with a simple policy, asserting invariants each step.
    Also round-trips every enumerated concrete move through a snapshot and
    checks invariants on the result (so even un-taken branches are validated)."""
    s = LLMSession.start_new(scenario, seed)
    v = check_invariants(s.gs)
    if v:
        return [f"{scenario}#{seed} @start: {v[:3]}"]
    steps = 0
    while not s.is_over() and steps < max_steps:
        steps += 1
        if s.gs.meta.pending:
            _resolve_pending(s)
        else:
            moves = s.legal_actions()
            if not moves:
                break
            # Validate invariants on a snapshot after each concrete enumerated move.
            for mv in moves:
                if mv["type"] in ("build_plan", "resolve_event"):
                    continue
                snap = GameState.from_json(s.gs.to_json())
                try:
                    engine.apply_action(snap, {k: w for k, w in mv.items() if not k.startswith("_")})
                except IllegalAction:
                    continue
                vv = check_invariants(snap)
                if vv:
                    return [f"{scenario}#{seed} after {mv['type']}: {vv[:3]}"]
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
            except IllegalAction:
                break
        v = check_invariants(s.gs)
        if v:
            return [f"{scenario}#{seed} @step {steps} ({s.gs.meta.subphase}): {v[:3]}"]
    return []


@pytest.mark.parametrize("scenario", S.SCENARIOS)
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6, 7, 8])
def test_invariants_hold_throughout_self_play(scenario, seed):
    violations = _fuzz_one(scenario, seed)
    assert violations == [], violations
