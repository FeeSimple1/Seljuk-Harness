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
        if nv._UI._joint:
            nv.apply({"type": "decline_inputs"}, version=nv._UI.version)
            continue
        moves = nv._menu(log_drops=False)
        if not moves:
            break
        concrete = [m for m in moves if not m.get("_unvalidated")]
        with contextlib.redirect_stdout(io.StringIO()):
            if concrete:
                pick = next((m for m in concrete if m["type"] in ("end_activation", "pass_step", "cmd_pass")),
                            concrete[0])
                nv.apply({k: v for k, v in pick.items() if not k.startswith("_")}, version=nv._UI.version)
            else:
                t = moves[0]
                if t["type"] == "build_plan":
                    nv.apply(_build_plan_action(_Sess(s.gs), t), version=nv._UI.version)
                elif t["type"] == "respond_approach":
                    nv.apply({"type": "respond_approach",
                              "choices": {d: {"action": "stand"} for d in t["_defenders"]}}, version=nv._UI.version)
                elif t["type"] == "assign_themata_defenders":
                    nv.apply({"type": "assign_themata_defenders", "markers": []}, version=nv._UI.version)
                elif t["type"] == "resolve_event":
                    card = t["card"]
                    with contextlib.redirect_stdout(io.StringIO()):
                        nv.apply({"type": "resolve_event", "card": card, "args": {}}, version=nv._UI.version)
                    # nv.apply swallows IllegalAction; if a choice-Event is still
                    # owed (needed args this stand-in can't supply), discard it.
                    if any(pp.get("type") == "event_pending_resolution" and pp.get("card") == card
                           for pp in s.gs.meta.pending):
                        s.gs.meta.pending = [pp for pp in s.gs.meta.pending
                                             if not (pp.get("type") == "event_pending_resolution"
                                                     and pp.get("card") == card)]
                else:
                    break
    return s


def test_clean_greedy_drive_records_no_anomalies():
    with contextlib.redirect_stdout(io.StringIO()):
        s = _drive_to_terminal("manzikert", 3)
    assert s.is_over()
    # template_build_rejected = the greedy stand-in couldn't supply a choice-Event's
    # args (a driver limitation, not an engine bug); no_legal_moves only at terminal.
    notable = [f for f in nv._S["findings"]
               if f["kind"] not in ("no_legal_moves", "template_build_rejected")]
    assert notable == [], notable


def test_helper_captures_over_enumeration(monkeypatch):
    with contextlib.redirect_stdout(io.StringIO()):
        nv.start("manzikert", 1)
        s = nv._S["session"]
        nv.apply(_build_plan_action(_Sess(s.gs), nv._menu(log_drops=False)[0]), version=nv._UI.version)
        nv.apply(_build_plan_action(_Sess(s.gs), nv._menu(log_drops=False)[0]), version=nv._UI.version)
        real = engine.legal_moves
        bogus = {"type": "cmd_march", "lord": "alp_arslan", "to": "ani", "way_type": "road",
                 "_desc": "BOGUS non-adjacent"}
        monkeypatch.setattr(engine, "legal_moves", lambda gs: list(real(gs)) + [bogus])
        nv._UI._cached_menu = None  # injected engine code changed, not the game state
        nv.show()
        menu = nv.actions(type="cmd_march", limit=100)["entries"]
    assert all(not (m["action"]["type"] == "cmd_march" and m["action"].get("to") == "ani") for m in menu)
    over = [f for f in nv._S["findings"] if f["kind"] == "over_enum_filtered"]
    assert len(over) == 1 and over[0]["code"] == "no_way"


def test_plan_helper_validates_and_applies():
    """nv.plan() pre-validates the common Plan mistakes with a clear message and
    applies a valid Plan (so a planning slip isn't logged as an engine finding)."""
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        nv.start("manzikert", 1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            nv.plan(["alp_arslan"], version=nv._UI.version)              # wrong size -> rejected locally
        bad = out.getvalue()
    assert "must have 4 cards" in bad
    before = len(nv._S["findings"])
    with contextlib.redirect_stdout(io.StringIO()):
        nv.plan(["alp_arslan", "sav_tekin", "no_command", "no_command"], version=nv._UI.version)  # valid
    assert nv._S["session"].gs.side_decks("seljuk").command_plan  # plan submitted
    assert len(nv._S["findings"]) == before  # no false finding from the rejected plan


def test_lookups_and_map_helpers():
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        nv.start("manzikert", 1)
        lord = nv.lookup_lord("alp_arslan")["data"]["reference"]
        ways = nv.map("ani")["data"]["ways"]
        st = nv.state(full=True)["data"]
    assert lord["id"] == "alp_arslan" and "ratings" in lord
    assert {w["to"] for w in ways} == {"ararat", "mempet"}
    assert "lords" in st and "meta" in st
