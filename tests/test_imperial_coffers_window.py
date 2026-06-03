"""SMOKE-008 follow-up: R14 Imperial Coffers discard is offered in its window
(end of Arts of War, after both sides resolve Events, before Pay) and only when
usable, and round-trips. Out of window it is never surfaced."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, engine, actions, campaign, map as gmap
from seljuk.rng import DiceRoller


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _setup_target(gs):
    """Make Robert a Mustered Seljuk-allied Lord adjacent to a Mustered Roman Lord."""
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True
    nb = next(n for n in gmap.neighbors(rom.cylinder))
    rob = gs.lords["robert_crepin"]; rob.side = "seljuk"; rob.mustered = True; rob.cylinder = nb
    return rob.id


def _aow(gs):
    """Run a non-first Arts of War with empty decks (no Event draws to mask R14)."""
    gs.meta.notes["first_aow_done"] = True
    gs.seljuk.draw_deck.clear(); gs.roman.draw_deck.clear()
    actions.resolve_arts_of_war(gs, DiceRoller(seed=1))


def _ic_pending(gs):
    return [p for p in gs.meta.pending if p["type"] == "imperial_coffers"]


def test_offered_when_in_play_with_valid_target():
    gs = _gs(); tid = _setup_target(gs)
    gs.roman.capabilities_in_play.append("R14")
    _aow(gs)
    assert _ic_pending(gs)
    types = {m["type"] for m in engine.legal_moves(gs)}
    assert "discard_imperial_coffers" in types and "pass_imperial_coffers" in types
    # the discard targets exactly the valid lord
    disc = [m for m in engine.legal_moves(gs) if m["type"] == "discard_imperial_coffers"]
    assert {m["target"] for m in disc} == {tid}


def test_discard_roundtrips_and_consumes_capability():
    gs = _gs(); tid = _setup_target(gs)
    gs.roman.capabilities_in_play.append("R14")
    _aow(gs)
    engine.apply_action(gs, {"type": "discard_imperial_coffers", "target": tid})
    assert "R14" not in gs.roman.capabilities_in_play
    assert "R14" in gs.roman.draw_deck
    assert _ic_pending(gs) == []                 # decision consumed


def test_decline_roundtrips_and_keeps_capability():
    gs = _gs(); _setup_target(gs)
    gs.roman.capabilities_in_play.append("R14")
    _aow(gs)
    engine.apply_action(gs, {"type": "pass_imperial_coffers"})
    assert "R14" in gs.roman.capabilities_in_play   # kept
    assert _ic_pending(gs) == []


def test_not_offered_when_capability_not_in_play():
    gs = _gs(); _setup_target(gs)                # target exists, but R14 not deployed
    _aow(gs)
    assert _ic_pending(gs) == []


def test_not_offered_without_a_valid_target():
    gs = _gs()
    gs.roman.capabilities_in_play.append("R14")  # in play, but no adjacent Seljuk Robert/Roussel
    for tid in ("robert_crepin", "roussel_de_bailleul"):
        gs.lords[tid].side = "roman"
    _aow(gs)
    assert _ic_pending(gs) == []


def test_not_offered_on_first_levy():
    gs = _gs(); _setup_target(gs)
    gs.roman.capabilities_in_play.append("R14")
    gs.meta.notes.pop("first_aow_done", None)    # first Arts of War deploys caps, no discard
    gs.seljuk.draw_deck.clear(); gs.roman.draw_deck.clear()
    actions.resolve_arts_of_war(gs, DiceRoller(seed=1))
    assert _ic_pending(gs) == []
