"""Bug fix: R12 Afsin Recalled (and the sibling S14 Manuel Komnenos Falls Ill)
must resolve as a no-op when the target Lord is permanently removed -- he has
neither a Service Marker nor a cylinder on the Calendar, so there is nothing to
shift. Previously every offered choice raised, leaving the Event pending and
stalling the Levy. The card does not call for a replacement Event."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E, engine
from seljuk.rng import DiceRoller


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _r():
    return DiceRoller(seed=1)


def _remove(lord):
    lord.mustered = False
    lord.cylinder = "removed"
    lord.cylinder_calendar_box = None
    lord.service_box = None


def test_r12_no_op_when_afsin_permanently_removed():
    gs = _gs()
    _remove(gs.lords["afsin_beg"])
    for what in ("service", "cylinder"):
        for direction in ("left", "right"):
            r = E._ev_afsin_recalled(gs, {"what": what, "direction": direction}, _r())
            assert r.get("no_op") is True


def test_r12_pending_clears_so_levy_can_continue():
    gs = _gs()
    _remove(gs.lords["afsin_beg"])
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.pay"
    gs.meta.pending = [{"type": "event_pending_resolution", "side": "roman",
                        "card": "R12", "tags": ["asterisk"]}]
    res = engine.apply_action(gs, {"type": "resolve_event", "card": "R12",
                                   "args": {"what": "service", "direction": "left"}})
    assert res.get("no_op") is True or res.get("ok")
    assert not any(p["type"] == "event_pending_resolution" and p["card"] == "R12"
                   for p in gs.meta.pending)               # pending cleared


def test_r12_still_shifts_service_when_afsin_present():
    gs = _gs()
    af = gs.lords["afsin_beg"]; af.mustered = True; af.cylinder = "ani"; af.service_box = 5
    r = E._ev_afsin_recalled(gs, {"what": "service", "direction": "left"}, _r())
    assert r["shifted"] == "service" and r["box"] == 4


def test_s14_no_op_when_manuel_permanently_removed():
    gs = _gs()
    _remove(gs.lords["manuel_komnenos"])
    r = E._ev_manuel_ill(gs, {"what": "service", "direction": "right"}, _r())
    assert r.get("no_op") is True


def test_s14_still_shifts_when_manuel_present():
    gs = _gs()
    mk = gs.lords["manuel_komnenos"]; mk.mustered = True; mk.cylinder = "ani"; mk.service_box = 3
    r = E._ev_manuel_ill(gs, {"what": "service", "direction": "right"}, _r())
    assert r["shifted"] == "service" and r["box"] == 4
