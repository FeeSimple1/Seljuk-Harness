"""Phase 5b: self-play completes all scenarios; round-trip sweep is clean."""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from self_play import play_game            # noqa: E402
from roundtrip_sweep import sweep_game     # noqa: E402
from seljuk import scenarios as S          # noqa: E402


@pytest.mark.parametrize("scenario", S.SCENARIOS)
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_self_play_reaches_terminal(scenario, seed):
    # Multiple seeds so Plan paths that reveal a Treachery card (which owes a
    # Loyalty Check sub-decision, 1.4.1) are exercised: a driver that fails to
    # resolve that pending strands the Treachery card as active_card with no
    # legal moves, so the game never terminates (emperor_and_the_lion seed=2).
    res = play_game(scenario, seed=seed)
    assert res["over"] is True
    assert res["winner"] in ("roman", "seljuk", "draw")
    assert res["steps"] < 4000


@pytest.mark.parametrize("scenario", S.SCENARIOS)
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_roundtrip_sweep_clean(scenario, seed):
    findings = sweep_game(scenario, seed=seed)
    assert findings == [], f"{scenario}#{seed}: enumerator/handler divergence: {findings[:5]}"


def test_self_play_resolves_loyalty_check():
    """SMOKE-002 regression: the self-play driver must resolve a `loyalty_check`
    pending (revealed Treachery card, 1.4.1) through the handler, not silently
    drop it. Dropping it strands the Treachery card as active_card with no legal
    moves -> the game never terminates. Source-marker guard so a refactor that
    removes the handler trips this test as well as test_self_play_reaches_terminal."""
    import self_play
    assert "SMOKE-002" in inspect.getsource(self_play._resolve_pending)
    assert "loyalty_check" in inspect.getsource(self_play._resolve_pending)
