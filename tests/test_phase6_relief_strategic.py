"""Phase 6 (R5/R6): Relief Sally (4.8.1) + combat-aggressive self-play."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from seljuk import scenarios as S, engine
from strategic_agent import play_game as strategic_play  # noqa: E402


def test_relief_sally_besieged_lord_joins_attack_481():
    gs = S.load_scenario("emperor_and_the_lion", seed=2)
    ch = gs.lords["chatatourios"]; ch.cylinder = "antioch"; ch.besieged = True
    ch.forces = {"tagmata": 2, "infantry": 2}
    aa = gs.lords["alp_arslan"]; aa.cylinder = "antioch"; aa.forces = {"turkic_horse": 2}
    gs.locales["antioch"].siege_markers = 2
    rom = gs.lords["romanos_diogenes"]; rom.cylinder = "laodikeia"
    rom.forces = {"tagmata": 2, "infantry": 1, "turkic_horse": 2}
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = "roman"
    gs.meta.active_lord = "romanos_diogenes"; gs.meta.active_card = "romanos_diogenes"; gs.meta.actions_remaining = 4
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1
    engine.apply_action(gs, {"type": "cmd_march", "lord": "romanos_diogenes", "to": "antioch", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "respond_approach", "choices": {"alp_arslan": {"action": "stand"}}})
    assert r["battle"].get("relief_sally") == ["chatatourios"]  # besieged Roman joined the relief Attack


def test_relief_sally_loss_reduces_siege_to_one_481():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    ch = gs.lords["chatatourios"]; ch.cylinder = "antioch"; ch.besieged = True; ch.forces = {"militia": 1}
    aa = gs.lords["alp_arslan"]; aa.cylinder = "antioch"; aa.forces = {"turkic_horse": 6, "ghulam_cavalry": 2}
    gs.locales["antioch"].siege_markers = 3
    rom = gs.lords["romanos_diogenes"]; rom.cylinder = "laodikeia"; rom.forces = {"militia": 1}  # weak relief
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = "roman"
    gs.meta.active_lord = "romanos_diogenes"; gs.meta.active_card = "romanos_diogenes"; gs.meta.actions_remaining = 4
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1
    engine.apply_action(gs, {"type": "cmd_march", "lord": "romanos_diogenes", "to": "antioch", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "respond_approach", "choices": {"alp_arslan": {"action": "stand"}}})
    if r["battle"]["winner"] == "defender":
        assert gs.locales["antioch"].siege_markers == 1


@pytest.mark.parametrize("scenario", S.SCENARIOS)
def test_strategic_agent_reaches_terminal(scenario):
    res = strategic_play(scenario, seed=1)
    assert res["over"] is True
    assert res["winner"] in ("roman", "seljuk", "draw")
