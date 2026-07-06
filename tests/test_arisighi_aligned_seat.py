"""Bug fix: a dual-allegiance Lord uses his alignment-specific Seat. Roman-aligned
Arisighi's Seat is the Constantinople Holding Box, not his printed Seljuk Seat
(to_mosul_and_baghdad) -- otherwise Muster / treachery re-entry / Winter Quarters
send him into the Seljuk box, co-locating him with Seljuk Lords."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, actions, campaign as C
from seljuk.invariants import check_invariants


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def test_muster_seats_prefers_constantinople_when_roman_aligned():
    gs = _gs()
    seats = actions._muster_seats(gs, "arisighi", "roman")
    assert seats == ["to_constantinople"]
    assert "to_mosul_and_baghdad" not in seats


def test_muster_seats_uses_mosul_when_seljuk_aligned():
    gs = _gs()
    seats = actions._muster_seats(gs, "arisighi", "seljuk")
    assert "to_mosul_and_baghdad" in seats
    assert "to_constantinople" not in seats


def test_winter_quarters_returns_roman_arisighi_to_constantinople():
    gs = _gs()
    ar = gs.lords["arisighi"]; ar.side = "roman"; ar.mustered = True; ar.cylinder = "ankyra"
    ab = gs.lords["artuk_beg"]; ab.side = "seljuk"; ab.mustered = True; ab.cylinder = "to_mosul_and_baghdad"
    C._begin_winter_quarters(gs)   # Arisighi has a single aligned Seat -> applied immediately
    assert ar.cylinder == "to_constantinople"
    assert ar.cylinder != "to_mosul_and_baghdad"
    assert check_invariants(gs) == []          # not co-located with Seljuk Artuk Beg
