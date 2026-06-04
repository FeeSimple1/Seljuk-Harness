"""Bug fix: R15 Emir of Aleppo Spurns Alp Arslan was a generic no-op. It now
implements the Aleppo state transition (Seljuk-Conquered + no Siege -> place
Independent Aleppo; if already present -> Roman Conquered), marks the once-per-
game Calendar, adjusts VP, and -- when it has no effect or was already marked --
discards and draws a replacement Event."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, events as E
from seljuk.rng import DiceRoller


def _gs():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    al = gs.locales["aleppo"]; al.conquered_side = "seljuk"; al.conquered_count = 3; al.siege_markers = 0
    gs.meta.independent_aleppo_on_map = False
    if "R15" in gs.meta.asterisks_used:
        gs.meta.asterisks_used.remove("R15")
    return gs


def _r():
    return DiceRoller(seed=1)


def test_eligible_places_independent_aleppo():
    gs = _gs()
    r = E._ev_emir_spurns(gs, {}, _r())
    assert r.get("independent_aleppo") is True
    assert gs.meta.independent_aleppo_on_map is True
    assert gs.locales["aleppo"].conquered_side is None      # no longer Seljuk-held
    assert "R15" in gs.meta.asterisks_used                  # once-per-game marked


def test_independent_already_present_becomes_roman_conquered():
    gs = _gs(); gs.meta.independent_aleppo_on_map = True
    r = E._ev_emir_spurns(gs, {}, _r())
    assert r.get("roman_conquered") == "aleppo"
    assert gs.locales["aleppo"].conquered_side == "roman"
    assert gs.meta.independent_aleppo_on_map is False
    assert "R15" in gs.meta.asterisks_used


def test_already_marked_draws_replacement():
    gs = _gs(); gs.meta.asterisks_used.append("R15")
    gs.roman.draw_deck.clear(); gs.roman.draw_deck.append("R19")   # an immediate Event
    r = E._ev_emir_spurns(gs, {}, _r())
    assert r.get("no_op") is True and r.get("replacement") == "R19"
    assert any(p["type"] == "event_pending_resolution" and p["card"] == "R19"
               for p in gs.meta.pending)                           # replacement queued


def test_no_effect_when_seljuk_lord_in_aleppo_draws_replacement():
    gs = _gs()
    sl = gs.lords["alp_arslan"]; sl.side = "seljuk"; sl.mustered = True; sl.cylinder = "aleppo"
    gs.roman.draw_deck.clear(); gs.roman.draw_deck.append("R19")
    r = E._ev_emir_spurns(gs, {}, _r())
    assert r.get("no_op") is True and r.get("replacement") == "R19"
    assert gs.locales["aleppo"].conquered_side == "seljuk"         # unchanged
    assert "R15" not in gs.meta.asterisks_used


def test_no_effect_when_aleppo_roman_conquered():
    gs = _gs(); gs.locales["aleppo"].conquered_side = "roman"
    gs.roman.draw_deck.clear(); gs.roman.draw_deck.append("R19")
    r = E._ev_emir_spurns(gs, {}, _r())
    assert r.get("no_op") is True and r.get("replacement") == "R19"


def test_no_effect_when_not_seljuk_conquered():
    gs = _gs(); gs.locales["aleppo"].conquered_side = None
    gs.roman.draw_deck.clear(); gs.roman.draw_deck.append("R19")
    r = E._ev_emir_spurns(gs, {}, _r())
    assert r.get("no_op") is True
