"""Bug fix: R20 Armenian Resistance clarifications -- a Strategic Objective marker
at the conquered Locale returns to available (not scored as VP), and a Seljuk
Lord present immediately places a Siege/Bypass marker (Seljuk choice) so he is
not left in the open at the now-Roman Stronghold."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E
from seljuk.rng import DiceRoller

LOC = "khliat"


def _gs():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.locales[LOC].conquered_side = "seljuk"   # ensure Seljuk-friendly
    return gs


def _r():
    return DiceRoller(seed=1)


def test_conquers_roman():
    gs = _gs()
    r = E._ev_armenian_resistance(gs, {"locale": LOC}, _r())
    assert r["roman_conquered"] == LOC and gs.locales[LOC].conquered_side == "roman"


def test_strategic_objective_returns_to_available():
    gs = _gs()
    gs.locales[LOC].strategic_objective = True
    gs.holding_boxes.constantinople_strategic_objectives_available = 0
    r = E._ev_armenian_resistance(gs, {"locale": LOC}, _r())
    assert r.get("strategic_objective_returned") is True
    assert gs.locales[LOC].strategic_objective is False
    assert gs.holding_boxes.constantinople_strategic_objectives_available == 1


def test_present_seljuk_lord_bypasses_by_default():
    gs = _gs()
    sj = gs.lords["alp_arslan"]; sj.side = "seljuk"; sj.mustered = True; sj.cylinder = LOC
    sj.bypassed = False; sj.besieged = False
    r = E._ev_armenian_resistance(gs, {"locale": LOC}, _r())
    assert r.get("invest") == "bypass"
    assert gs.locales[LOC].bypass is True and sj.bypassed is True


def test_present_seljuk_lord_can_siege():
    gs = _gs()
    sj = gs.lords["alp_arslan"]; sj.side = "seljuk"; sj.mustered = True; sj.cylinder = LOC
    r = E._ev_armenian_resistance(gs, {"locale": LOC, "invest": "siege"}, _r())
    assert r.get("invest") == "siege" and gs.locales[LOC].siege_markers >= 1
