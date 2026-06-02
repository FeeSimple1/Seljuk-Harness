"""Phase 4 batch 1: S7 Trusted Commander, S3 Steppe Raiders, S17 Deep Raids."""
import pytest
from seljuk import scenarios as S, campaign, engine, actions
from seljuk import map as gmap
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def test_s7_trusted_commander_group_march():
    gs = S.load_scenario("emperor_and_the_lion")
    a, b, c = gs.lords["afsin_beg"], gs.lords["artuk_beg"], gs.lords["sav_tekin"]
    for L in (a, b, c):
        L.mustered = True; L.besieged = False; L.cylinder = "ani"
    # Non-Commander cannot lead a Group March without Trusted Commander.
    with pytest.raises(IllegalAction):
        campaign._marching_group(gs, a, ["artuk_beg"])
    a.capabilities = ["S7"]
    grp = campaign._marching_group(gs, a, ["artuk_beg"])
    assert {L.id for L in grp} >= {"afsin_beg", "artuk_beg"}
    # ...but with 1 (only) other Seljuk Lord.
    with pytest.raises(IllegalAction):
        campaign._marching_group(gs, a, ["artuk_beg", "sav_tekin"])


def test_s3_steppe_raiders_ravage_adjacent():
    gs = S.load_scenario("emperor_and_the_lion")
    lid, adj = "sav_tekin", "artah"   # place at manbij (Seljuk), adjacent to artah (Roman)
    lord = gs.lords[lid]; lord.mustered = True; lord.cylinder = "manbij"
    lord.forces = {"turkic_horse": 2}; lord.capabilities = ["S3"]
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = lid
    gs.meta.active_card = lid; gs.meta.actions_remaining = 2
    gs.seljuk.command_plan = [lid]; gs.seljuk.plan_pointer = 1
    r = engine.apply_action(gs, {"type": "cmd_ravage", "lord": lid, "target": adj, "actions": 2})
    assert gs.locales[adj].ravaged_side == "seljuk"
    # Without the Capability the adjacent target is rejected.
    gs2 = S.load_scenario("emperor_and_the_lion")
    l2 = gs2.lords[lid]; l2.mustered = True; l2.cylinder = "manbij"; l2.forces = {"turkic_horse": 2}
    gs2.meta.phase = "campaign"; gs2.meta.active_lord = lid; gs2.meta.actions_remaining = 2
    with pytest.raises(IllegalAction):
        campaign.h_cmd_ravage(gs2, {"lord": lid, "target": adj, "actions": 2}, DiceRoller(1))


def test_s17_deep_raids_disband_for_loot():
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["sav_tekin"]
    lord.mustered = True; lord.cylinder = "ikonion"; lord.capabilities = ["S17"]
    gs.meta.subphase = "levy.call_to_arms"; gs.meta.active_player = "seljuk"
    gs.meta.levy_step_passed = {}
    before = gs.holding_boxes.mosul_baghdad_loot
    r = engine.apply_action(gs, {"type": "cta_deep_raids", "lord": "sav_tekin"})
    assert gs.holding_boxes.mosul_baghdad_loot == before + 2   # Ikonion = 2
    assert gs.lords["sav_tekin"].cylinder != "ikonion"          # Disbanded off the map
    # Western Anatolia = 3.
    gs2 = S.load_scenario("emperor_and_the_lion")
    l2 = gs2.lords["sav_tekin"]; l2.mustered = True; l2.cylinder = "western_anatolia"; l2.capabilities = ["S17"]
    gs2.meta.subphase = "levy.call_to_arms"; gs2.meta.active_player = "seljuk"; gs2.meta.levy_step_passed = {}
    b2 = gs2.holding_boxes.mosul_baghdad_loot
    engine.apply_action(gs2, {"type": "cta_deep_raids", "lord": "sav_tekin"})
    assert gs2.holding_boxes.mosul_baghdad_loot == b2 + 3


def test_s17_deep_raids_enumerated_in_cta():
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["sav_tekin"]; lord.mustered = True; lord.cylinder = "ikonion"; lord.capabilities = ["S17"]
    gs.meta.subphase = "levy.call_to_arms"; gs.meta.active_player = "seljuk"
    types = {m["type"] for m in actions.enumerate_call_to_arms(gs)}
    assert "cta_deep_raids" in types
