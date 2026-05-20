"""Phase 1 CLI: new + state (smoke)."""
import json
from pathlib import Path

from seljuk import cli


def test_cli_new_writes_state_file(tmp_path):
    out = tmp_path / "g.state.json"
    rc = cli.main(["new", "specter_of_norman_betrayal", "--seed", "2", "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["meta"]["scenario"] == "specter_of_norman_betrayal"
    assert data["meta"]["seed"] == 2


def test_cli_state_renders(tmp_path, capsys):
    out = tmp_path / "g.state.json"
    cli.main(["new", "emperor_and_the_lion", "--out", str(out)])
    capsys.readouterr()
    assert cli.main(["state", "--file", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Alp Arslan" in text and "VP" in text


def test_cli_state_missing_file_returns_1(tmp_path):
    assert cli.main(["state", "--file", str(tmp_path / "nope.json")]) == 1


def test_cli_legal_moves_not_yet_implemented():
    assert cli.main(["legal-moves"]) == 1
