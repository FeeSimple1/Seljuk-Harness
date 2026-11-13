"""Nomisma shifts Roman Service one box right during Levy Pay (2.2.3, 6.2)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import engine, scenarios as S
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface
from seljuk.llm.session import LLMSession
from seljuk.state import GameState, IllegalAction

ROMANOS = "romanos_diogenes"


def _gs():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.roman.draw_deck.remove("R19")
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
        assert l.service_box == min(13, before[l.id] + 1)
    for lid, sb in seljuk_before.items():
        assert gs.lords[lid].service_box == sb                   # Seljuk untouched
    assert gs.meta.notes["nomisma_debased_used"] is True
    assert "R19" not in gs.roman.capabilities_in_play and "R19" in gs.roman.draw_deck
    assert "R19" in gs.meta.asterisks_used


@pytest.mark.parametrize("pay_steps", [7, 8])
def test_nomisma_after_pay_preserves_off_calendar_service(pay_steps, tmp_path):
    gs = _gs()
    gs.meta.calendar_box = 3
    # Stage prior Tax earnings, then use public Pay for every Service step.
    gs.lords[ROMANOS].assets.coin = 8
    ui = CompactInterface(LLMSession(gs), player="roman")
    for _ in range(pay_steps):
        moves = ui.actions(type="pay", limit=100)["entries"]
        coin = next(row for row in moves
                    if row["action"].get("payer") == row["action"].get("target") == ROMANOS
                    and row["action"].get("asset") == "coin")
        ui.apply(coin["id"])
    assert ui.gs.lords[ROMANOS].service_box == 5 + pay_steps
    [move] = ui.actions(type="discard_nomisma")["entries"]
    path = tmp_path / "nomisma.json"
    ui.save(path)
    resumed = CompactInterface.load(path)
    ui.apply(move["id"])
    resumed.apply(move["id"])
    assert ui.gs.to_json() == resumed.gs.to_json()
    assert ui.gs.lords[ROMANOS].service_box == 13
    assert ui.gs.lords[ROMANOS].assets.coin == 8 - pay_steps
    assert ui.gs.meta.notes["nomisma_debased_used"]
    assert not _offered(ui.gs)
    assert not check_invariants(ui.gs)


@pytest.mark.parametrize(("vassal_start", "expected"), [(4, 5), (12, 13), (13, 13)])
def test_vassal_service_markers_shift_under_6_2(vassal_start, expected):
    gs = _gs()
    gs.meta.options["vassal_service"] = True
    rom = gs.lords[ROMANOS]
    rom.service_box = 13
    vassal = rom.vassals[0]
    vassal.levied = True
    vassal.service_box = vassal_start
    saved = GameState.from_json(gs.to_json())
    assert engine.apply_action(gs, {"type": "discard_nomisma"}) == engine.apply_action(
        saved, {"type": "discard_nomisma"},
    )
    assert gs.to_json() == saved.to_json()
    assert rom.service_box == 13
    assert vassal.service_box == expected


def test_not_triggerable_in_campaign_phase():
    gs = _gs(); gs.meta.phase = "campaign"
    with pytest.raises(IllegalAction, match="unknown_action"):
        engine.apply_action(gs, {"type": "discard_nomisma"})


@pytest.mark.parametrize(("step", "side"), [("levy.muster", "roman"), ("levy.pay", "seljuk")])
def test_nomisma_rejects_wrong_levy_step_or_side(step, side):
    gs = _gs()
    gs.meta.subphase, gs.meta.active_player = step, side
    before = gs.to_json()
    assert not _offered(gs)
    with pytest.raises(IllegalAction, match="wrong_step"):
        engine.apply_action(gs, {"type": "discard_nomisma"})
    assert gs.to_json() == before
