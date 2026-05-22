"""The CLI play loop another agent uses: new -> briefing/legal-moves -> do -> ...
driven against a save file, exercising the LLMSession-backed subcommands."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import cli


def _run(argv, capsys):
    rc = cli.main(argv)
    out = capsys.readouterr()
    return rc, out.out, out.err


def test_cli_full_loop(tmp_path, capsys):
    f = str(tmp_path / "g.json")
    # new
    rc, out, _ = _run(["new", "emperor_and_the_lion", "--seed", "1", "--out", f], capsys)
    assert rc == 0 and Path(f).exists()

    # briefing
    rc, out, _ = _run(["briefing", "--file", f], capsys)
    assert rc == 0 and ("phase=" in out)

    # pending (first Levy may owe capability deployment)
    rc, out, _ = _run(["pending", "--file", f], capsys)
    assert rc == 0
    pend = json.loads(out)
    assert isinstance(pend, list)

    # legal-moves -> valid JSON palette
    rc, out, err = _run(["legal-moves", "--file", f], capsys)
    assert rc == 0
    moves = json.loads(out)
    assert isinstance(moves, list) and moves
    assert all("type" in m for m in moves)

    # do: apply the first non-template legal move (or pass_step)
    types = {m["type"]: m for m in moves}
    action = {"type": "pass_step"} if "pass_step" in types else \
        {k: v for k, v in moves[0].items() if not k.startswith("_")}
    rc, out, err = _run(["do", "--file", f, "--action", json.dumps(action)], capsys)
    assert rc == 0
    result = json.loads(out)
    assert result.get("ok") is True

    # state --side X --json -> hidden-info filtered, opponent secrets masked
    rc, out, _ = _run(["state", "--file", f, "--side", "seljuk", "--json"], capsys)
    assert rc == 0
    st = json.loads(out)
    assert st["_viewing_side"] == "seljuk"
    assert all(c == "<hidden>" for c in st["roman"]["draw_deck"])  # opponent deck masked

    # history records the applied action
    rc, out, _ = _run(["history", "--file", f, "--n", "5"], capsys)
    assert rc == 0


def test_cli_illegal_action_reports_cleanly(tmp_path, capsys):
    f = str(tmp_path / "g.json")
    _run(["new", "manzikert", "--out", f], capsys)
    rc, out, err = _run(["do", "--file", f, "--action", '{"type":"nonsense"}'], capsys)
    assert rc == 1 and "IllegalAction" in err


def test_cli_bad_json_action(tmp_path, capsys):
    f = str(tmp_path / "g.json")
    _run(["new", "manzikert", "--out", f], capsys)
    rc, out, err = _run(["do", "--file", f, "--action", "{not json}"], capsys)
    assert rc == 2 and "not valid JSON" in err


def test_cli_missing_file(capsys):
    rc, out, err = _run(["legal-moves", "--file", "/tmp/does_not_exist_xyz.json"], capsys)
    assert rc == 1 and "No state file" in err
