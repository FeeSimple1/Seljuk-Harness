"""Bug fix: R21/S21 Turkic removal. A Lord reduced to no Forces Disbands (card
clarification: 'thereby causing a Disband'). S21 may also remove Turkic Horse
Themata Service Markers (defending or on a co-located mat), not only unit forces
(R21 removes units only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E, battle
from seljuk.state import ThemataMarker
from seljuk.rng import DiceRoller

LOC = "ani"


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _r():
    return DiceRoller(seed=1)


def test_r21_disbands_lord_left_with_no_forces():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = LOC
    aa.forces = {"turkic_horse": 2}; aa.service_box = 5
    r = E._hold_nomadic_tribes(gs, {"locale": LOC, "count": 2}, _r())
    assert r["turkic_removed"] == 2
    assert "alp_arslan" in r["disbanded"]
    assert aa.mustered is False                      # Disbanded (1.6)


def test_r21_does_not_disband_lord_with_remaining_forces():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = LOC
    aa.forces = {"turkic_horse": 2, "ghulam_cavalry": 1}; aa.service_box = 5
    r = E._hold_nomadic_tribes(gs, {"locale": LOC, "count": 2}, _r())
    assert r["disbanded"] == [] and aa.mustered is True


def test_s21_removes_turkic_themata_marker():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = LOC; aa.forces = {}
    gs.locales[LOC].themata_defending = [ThemataMarker(unit="turkic_horse", home_thema="Iberia")]
    r = E._hold_common_cultural(gs, {"locale": LOC, "count": 2}, _r())
    assert r["turkic_removed"] == 1
    assert gs.locales[LOC].themata_defending == []   # Themata marker removed


def test_r21_does_not_touch_themata_markers():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = LOC; aa.forces = {}
    gs.locales[LOC].themata_defending = [ThemataMarker(unit="turkic_horse", home_thema="Iberia")]
    r = E._hold_nomadic_tribes(gs, {"locale": LOC, "count": 2}, _r())
    assert r["turkic_removed"] == 0                  # R21 = units only
    assert len(gs.locales[LOC].themata_defending) == 1


def test_s21_in_battle_removes_themata_marker():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = LOC; aa.forces = {}
    gs.seljuk.held_events.append("S21")
    gs.locales[LOC].themata_defending = [ThemataMarker(unit="turkic_horse", home_thema="Iberia")]
    battle._consume_battle_events(gs, {"seljuk": ["S21"]}, locale=LOC)
    assert gs.locales[LOC].themata_defending == []
