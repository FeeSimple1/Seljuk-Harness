"""Enumerator/handler round-trip sweep for the Levy phase.

CROSS_PROJECT_LESSONS.md sections 1-2: every move the enumerator emits must be
applicable by its handler. At each Levy state we replay every emitted move
through apply_action on a deep snapshot and assert no IllegalAction comes back;
then we advance the real game and continue. This is the guard against the
enumerator and handlers silently diverging.
"""
import pytest

from seljuk import scenarios as S, engine
from seljuk.state import GameState, IllegalAction


@pytest.mark.parametrize("scenario", S.SCENARIOS)
def test_levy_enumerator_handler_roundtrip(scenario):
    gs = S.load_scenario(scenario, seed=1)
    # Make every scenario exercise a non-first Levy draw path deterministically.
    gs.meta.notes["first_aow_done"] = True
    gs.meta.phase = "levy"
    engine.start_levy(gs)

    guard = 0
    while gs.meta.subphase != "levy.complete" and guard < 60:
        guard += 1
        moves = engine.legal_moves(gs)
        # Every emitted move must apply cleanly on a fresh snapshot.
        for mv in moves:
            snap = GameState.from_json(gs.to_json())
            try:
                engine.apply_action(snap, {k: v for k, v in mv.items() if not k.startswith("_")})
            except IllegalAction as e:  # pragma: no cover
                pytest.fail(f"{scenario}: enumerator emitted inapplicable {mv.get('type')}: {e}")
        # Advance the real game: prefer a concrete action, else pass the step.
        concrete = [m for m in moves if m["type"] != "pass_step"]
        chosen = concrete[0] if concrete else {"type": "pass_step"}
        engine.apply_action(gs, {k: v for k, v in chosen.items() if not k.startswith("_")})

    assert gs.meta.subphase == "levy.complete", f"{scenario}: Levy did not complete (stuck at {gs.meta.subphase})"
