"""Bounded self-play soak with Optional Rules (6.0) enabled, checking invariants
after every step. The full soak (all profiles x scenarios x many seeds) runs via
scripts/option_soak.py; this pins a fast subset so the option paths stay
invariant-clean in CI."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from option_soak import soak_game, PROFILES   # noqa: E402


@pytest.mark.parametrize("profile", ["all_on", "vassal_service", "sim_both", "deadlier_missiles"])
@pytest.mark.parametrize("scenario", ["emperor_and_the_lion", "manzikert"])
@pytest.mark.parametrize("seed", [1, 2])
def test_option_soak_terminates_invariant_clean(profile, scenario, seed):
    r = soak_game(scenario, seed, PROFILES[profile])
    assert r["over"] is True, f"{profile}/{scenario}#{seed} did not terminate"
    assert r["winner"] in ("roman", "seljuk", "draw")
    assert r["violations"] == [], r["violations"][:3]
