"""The ChatGPT-in-sandbox play helper (scripts/chatgpt_play_helper.py): a clean
greedy drive records no anomalies, and an injected over-enumerated move is both
filtered from the menu and captured as a structured finding."""
import io
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import chatgpt_play_helper as nv          # noqa: E402
from self_play import _build_plan_action  # noqa: E402
from seljuk import engine                 # noqa: E402


class _Sess:
    def __init__(self, gs):
        self.gs = gs


def _drive_to_terminal(scenario, seed, max_turns=600):
    nv.start(scenario, seed)
    s = nv._S["session"]
    for _ in range(max_turns):
        if s.is_over():
            break
        moves = nv._menu(log_drops=False)
        if not moves:
            break
        concrete = [m for m in moves if not m.get("_unvalidated")]
        with contextlib.redirect_stdout(io.StringIO()):
            if concrete:
                pick = next((m for m in concrete if m["type"] in ("end_activation", "pass_step", "cmd_pass")),
                            concrete[0])
                nv.apply({k: v for k, v in pick.items() if not k.startswith("_")})
            else:
                t = moves[0]
                if t["type"] == "build_plan":
                    nv.apply(_build_plan_action(_Sess(s.gs), t))
                elif t["type"] == "respond_approach":
                    nv.apply({"type": "respond_approach",
                              "choices": {d: {"action": "stand"} for d in t["_defenders"]}})
                elif t["type"] == "assign_themata_defenders":
                    nv.apply({"type": "assign_themata_defenders", "markers": []})
                else:
                    break
    return s


def test_clean_greedy_drive_records_no_anomalies():
    with contextlib.redirect_stdout(io.StringIO()):
        s = _drive_to_terminal("manzikert", 3)
    assert s.is_over()
    notable = [f for f in nv._S["findings"] if f["kind"] != "no_legal_moves"]
    assert notable == [], notable


def test_helper_captures_over_enumeration(monkeypatch):
    with contextlib.redirect_stdout(io.StringIO()):
        nv.start("manzikert", 1)
        s = nv._S["session"]
        nv.apply(_build_plan_action(_Sess(s.gs), nv._menu(log_drops=False)[0]))
        nv.apply(_build_plan_action(_Sess(s.gs), nv._menu(log_drops=False)[0]))
        real = engine.legal_moves
        bogus = {"type": "cmd_march", "lord": "alp_arslan", "to": "ani", "way_type": "road",
                 "_desc": "BOGUS non-adjacent"}
        monkeypatch.setattr(engine, "legal_moves", lambda gs: list(real(gs)) + [bogus])
        menu = nv.show()
    assert all(not (m["type"] == "cmd_march" and m.get("to") == "ani") for m in menu)
    over = [f for f in nv._S["findings"] if f["kind"] == "over_enum_filtered"]
    assert len(over) == 1 and over[0]["code"] == "no_way"
