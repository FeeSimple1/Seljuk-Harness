"""Phase 5b: self-play completes all scenarios; round-trip sweep is clean."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from self_play import play_game            # noqa: E402
from roundtrip_sweep import sweep_game     # noqa: E402
from seljuk import scenarios as S          # noqa: E402


@pytest.mark.parametrize("scenario", S.SCENARIOS)
def test_self_play_reaches_terminal(scenario):
    res = play_game(scenario, seed=1)
    assert res["over"] is True
    assert res["winner"] in ("roman", "seljuk", "draw")
    assert res["steps"] < 4000


@pytest.mark.parametrize("scenario", S.SCENARIOS)
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_roundtrip_sweep_clean(scenario, seed):
    findings = sweep_game(scenario, seed=seed)
    assert findings == [], f"{scenario}#{seed}: enumerator/handler divergence: {findings[:5]}"
