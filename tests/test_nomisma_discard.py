"""Ruling 1 -- R19 Nomisma Debased discard during the Levy Pay step: shift ALL
Roman Service Markers 1 box RIGHT (later), capped at box 12, bypassing Pay
eligibility; set the permanent Non-Commander Tax prohibition; once per game.
Triggerable only in the Levy Pay step (not Campaign Feed/Pay/Disband)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, engine, actions
from seljuk.state import IllegalAction


def _gs():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.roman.capabilities_in_play.append("R19")
    gs.meta.notes["nomisma_debased_used"] = False
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.pay"; gs.meta.active_player = "roman"
    return gs


def _offered(gs):
    return any(m["type"] == "discard_nomisma" for m in engine.legal_moves(gs))


def test_offered_in_pay_when_in_play_and_unused():
    gs = _gs()
    assert _offered(gs)


def test_not_offered_when_already_used():
    gs = _gs(); gs.meta.notes["nomisma_debased_used"] = True
    assert _offered(gs) is False


def test_not_offered_when_not_in_play():
    gs = _gs(); gs.roman.capabilities_in_play.remove("R19")
    assert _offered(gs) is False


def test_discard_shifts_all_roman_service_right_and_marks():
    gs = _gs()
    romans = [l for l in gs.lords.values() if l.side == "roman" and l.service_box is not None]
    before = {l.id: l.service_box for l in romans}
    seljuk_before = {l.id: l.service_box for l in gs.lords.values()
                     if l.side == "seljuk" and l.service_box is not None}
    engine.apply_action(gs, {"type": "discard_nomisma"})
    for l in romans:
        assert l.service_box == min(12, before[l.id] + 1)        # right (later), cap 12
    for lid, sb in seljuk_before.items():
        assert gs.lords[lid].service_box == sb                   # Seljuk untouched
    assert gs.meta.notes["nomisma_debased_used"] is True
    assert "R19" not in gs.roman.capabilities_in_play and "R19" in gs.roman.draw_deck
    assert "R19" in gs.meta.asterisks_used


def test_cap_at_box_12():
    gs = _gs()
    rom = gs.lords["romanos_diogenes"]; rom.service_box = 12
    engine.apply_action(gs, {"type": "discard_nomisma"})
    assert rom.service_box == 12                                 # capped


def test_vassal_service_markers_shift_under_6_2():
    gs = _gs()
    gs.meta.options = dict(gs.meta.options or {}); gs.meta.options["vassal_service"] = True
    rom = gs.lords["romanos_diogenes"]
    v = next((v for v in rom.vassals), None)
    if v is not None:
        v.levied = True; v.service_box = 4
        engine.apply_action(gs, {"type": "discard_nomisma"})
        assert v.service_box == 5


def test_not_triggerable_in_campaign_phase():
    gs = _gs(); gs.meta.phase = "campaign"
    try:
        engine.apply_action(gs, {"type": "discard_nomisma"})
        assert False, "expected no campaign handler"
    except IllegalAction as e:
        assert "unknown_action" in str(e)
