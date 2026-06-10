"""Immediate Events that target Themata must resolve as a no-op (not raise) when
there is nothing to remove, so the event_pending_resolution clears and the Levy
continues. Regression for S7 Deserters and S15 Thematic Troops Desert."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, engine
from seljuk import static_data as sd


def _queue(gs, card, side):
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.pay"
    gs.meta.pending = [{"type": "event_pending_resolution", "side": side, "card": card, "tags": ["immediate"]}]


def _pending(gs, card):
    return any(p["type"] == "event_pending_resolution" and p["card"] == card for p in gs.meta.pending)


def test_s7_no_op_and_clears_when_all_border_themata_empty():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    for t in ("Iberia", "Mesopotamia", "Melitene", "Antiocheia"):
        gs.themata[t] = []
    _queue(gs, "S7", "seljuk")
    res = engine.apply_action(gs, {"type": "resolve_event", "card": "S7", "args": {"thema": "Iberia"}})
    assert res.get("no_op") is True
    assert not _pending(gs, "S7")


def test_s15_no_op_and_clears_when_no_marker_anywhere():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ankyra"
    thema = sd.locale("ankyra")["thema"]
    gs.themata[thema] = []; gs.locales["ankyra"].themata_defending = []
    for l in gs.lords.values():
        if l.cylinder == "ankyra":
            l.themata_on_mat = []
    _queue(gs, "S15", "seljuk")
    res = engine.apply_action(gs, {"type": "resolve_event", "card": "S15", "args": {}})
    assert res.get("no_op") is True
    assert not _pending(gs, "S15")
