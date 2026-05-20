"""Phase 0 smoke tests: the skeleton imports and the infrastructure works.

These do not test game rules (there are none yet). They verify the package is
installable/importable, the CLI entry point responds, the deterministic RNG is
reproducible, the IllegalAction error carries a code, and the state-schema
draft is valid JSON. Real test-per-rule coverage accumulates from Phase 1.
"""
import json
from pathlib import Path

import seljuk
from seljuk import cli, rng
from seljuk.state import IllegalAction


def test_package_version():
    assert seljuk.__version__ == "0.0.0"


def test_cli_no_command_prints_help_and_returns_zero():
    assert cli.main([]) == 0


def test_cli_unimplemented_subcommand_returns_nonzero():
    # Phase 0: subcommands are registered but not implemented.
    assert cli.main(["state"]) == 1


def test_cli_parser_registers_core_subcommands():
    parser = cli.build_parser()
    # argparse stores subparser choices on the subparsers action.
    choices = set()
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices:
            choices.update(action.choices)
    for expected in ("new", "state", "legal-moves", "do", "pending", "history"):
        assert expected in choices


def test_rng_is_deterministic_for_a_seed():
    a = rng.DiceRoller(seed=1234).roll(20)
    b = rng.DiceRoller(seed=1234).roll(20)
    assert a == b
    assert all(1 <= v <= 6 for v in a)


def test_rng_state_round_trips():
    r = rng.DiceRoller(seed=7)
    r.roll(5)
    saved = r.get_state()
    expected = r.roll(10)
    r2 = rng.DiceRoller(seed=999)
    r2.set_state(saved)
    assert r2.roll(10) == expected


def test_illegal_action_carries_code():
    err = IllegalAction("bad_target", "no eligible Lord (3.4.1)")
    assert err.code == "bad_target"
    assert "3.4.1" in str(err)


def test_state_schema_draft_is_valid_json():
    schema = Path(__file__).resolve().parents[1] / "src" / "seljuk" / "data" / "schema" / "state.schema.json"
    data = json.loads(schema.read_text())
    assert data["type"] == "object"
    assert "meta" in data["properties"]
