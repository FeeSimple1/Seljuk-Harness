"""SMOKE-008 follow-up: the self-contained Hold Events whose play window
coincides with an active-player decision point must be SURFACED in the menu in
that window and NOT offered out of window. Every surfaced entry must round-trip
through its handler. Hold Events whose window is an out-of-turn reaction
(R3/S4 Summer Heat, R23 Kleisourai) or a Battle/Storm "play events" step
(R21/S21) or the auto-resolved Arts of War step (R14) have no modelled decision
point yet and must never appear in the normal menu."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, engine
from seljuk.state import GameState, IllegalAction


def _gs():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.pending.clear()            # ignore any scenario AoW pendings for these tests
    return gs


def _muster(gs, side):
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.muster"; gs.meta.active_player = side


def _command(gs, side, lord, actions=2):
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = side; gs.meta.active_lord = lord
    gs.meta.active_card = lord; gs.meta.actions_remaining = actions
    gs.meta.notes["card_full_actions"] = actions   # "before any action" marker


def _holds(gs):
    return [m for m in engine.legal_moves(gs) if m["type"] == "play_hold_event"]


def _cards(gs):
    return {m["card"] for m in _holds(gs)}


def _roundtrips(gs):
    """Every offered play_hold_event applies cleanly on a throwaway copy."""
    bad = []
    for m in _holds(gs):
        snap = GameState.from_json(gs.to_json())
        try:
            engine.apply_action(snap, {k: v for k, v in m.items() if not k.startswith("_")})
        except IllegalAction as e:
            bad.append(f"{m['card']} -> {e}")
    return bad


# --------------------------------------------------------------------------- #
# Muster window: R6 (Roman) / S10 (Seljuk)
# --------------------------------------------------------------------------- #
def test_r6_offered_in_roman_muster_and_roundtrips():
    gs = _gs(); gs.roman.held_events.append("R6")
    gs.lords["romanos_diogenes"].mustered = True
    _muster(gs, "roman")
    assert "R6" in _cards(gs)
    assert _roundtrips(gs) == []


def test_s10_offered_in_seljuk_muster_and_roundtrips():
    gs = _gs(); gs.seljuk.held_events.append("S10")
    gs.lords["alp_arslan"].mustered = True
    _muster(gs, "seljuk")
    assert "S10" in _cards(gs)
    assert _roundtrips(gs) == []


def test_r6_not_offered_when_romanos_not_mustered():
    gs = _gs(); gs.roman.held_events.append("R6")
    gs.lords["romanos_diogenes"].mustered = False
    _muster(gs, "roman")
    assert "R6" not in _cards(gs)


def test_r6_not_offered_during_seljuk_muster():
    gs = _gs(); gs.roman.held_events.append("R6")
    gs.lords["romanos_diogenes"].mustered = True
    _muster(gs, "seljuk")               # not the Roman muster
    assert "R6" not in _cards(gs)


def test_muster_holds_not_offered_during_command():
    gs = _gs(); gs.roman.held_events.append("R6"); gs.seljuk.held_events.append("S10")
    gs.lords["romanos_diogenes"].mustered = True; gs.lords["alp_arslan"].mustered = True
    _command(gs, "roman", "romanos_diogenes")
    assert "R6" not in _cards(gs)
    assert "S10" not in _cards(gs)


# --------------------------------------------------------------------------- #
# Command window: S24 Bad Omens (Seljuk, before acting), R4 Sultan's Horse (Roman)
# --------------------------------------------------------------------------- #
def test_s24_offered_before_action_and_roundtrips():
    gs = _gs(); gs.seljuk.held_events.append("S24")
    gs.roman.command_plan = ["romanos_diogenes", "romanos_diogenes"]; gs.roman.plan_pointer = 0
    _command(gs, "seljuk", "alp_arslan", actions=2)
    assert "S24" in _cards(gs)
    assert _roundtrips(gs) == []


def test_s24_not_offered_after_an_action():
    gs = _gs(); gs.seljuk.held_events.append("S24")
    gs.roman.command_plan = ["romanos_diogenes", "romanos_diogenes"]; gs.roman.plan_pointer = 0
    _command(gs, "seljuk", "alp_arslan", actions=2)
    gs.meta.actions_remaining = 1       # one Command action already spent
    assert "S24" not in _cards(gs)


def test_s24_not_offered_with_fewer_than_two_unrevealed_roman_cards():
    gs = _gs(); gs.seljuk.held_events.append("S24")
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 0
    _command(gs, "seljuk", "alp_arslan", actions=2)
    assert "S24" not in _cards(gs)


def test_r4_offered_when_alp_arslan_besieging_and_roundtrips():
    gs = _gs(); gs.roman.held_events.append("R4")
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    gs.locales["ani"].siege_markers = 2
    _command(gs, "roman", "romanos_diogenes")
    assert "R4" in _cards(gs)
    assert _roundtrips(gs) == []


def test_r4_not_offered_with_one_siege_marker():
    gs = _gs(); gs.roman.held_events.append("R4")
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    gs.locales["ani"].siege_markers = 1
    _command(gs, "roman", "romanos_diogenes")
    assert "R4" not in _cards(gs)


# --------------------------------------------------------------------------- #
# Other windows: these holds must never appear as plain muster/command items
# (they are surfaced in their own windows, covered by dedicated test files).
# --------------------------------------------------------------------------- #
def test_summer_heat_not_a_plain_command_menu_item():
    gs = _gs(); gs.roman.held_events.append("R3"); gs.seljuk.held_events.append("S4")
    gs.meta.calendar_box = 4            # a Summer box
    _command(gs, "seljuk", "alp_arslan")
    assert "R3" not in _cards(gs) and "S4" not in _cards(gs)
    _command(gs, "roman", "romanos_diogenes")
    assert "R3" not in _cards(gs) and "S4" not in _cards(gs)


def test_kleisourai_not_a_plain_command_menu_item():
    gs = _gs(); gs.roman.held_events.append("R23")
    _command(gs, "roman", "romanos_diogenes")
    assert "R23" not in _cards(gs)
    _command(gs, "seljuk", "alp_arslan")
    assert "R23" not in _cards(gs)


def test_battle_storm_turkic_holds_not_a_plain_command_menu_item():
    gs = _gs(); gs.roman.held_events.append("R21"); gs.seljuk.held_events.append("S21")
    _command(gs, "roman", "romanos_diogenes")
    assert "R21" not in _cards(gs)
    _command(gs, "seljuk", "alp_arslan")
    assert "S21" not in _cards(gs)


def test_imperial_coffers_not_a_plain_command_menu_item():
    gs = _gs(); gs.roman.held_events.append("R14")
    _muster(gs, "roman")
    assert "R14" not in _cards(gs)
    _command(gs, "roman", "romanos_diogenes")
    assert "R14" not in _cards(gs)
