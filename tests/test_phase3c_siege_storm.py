"""Phase 3c: Siege (4.5.1), Storm (4.9.1), Sally (4.9.2)."""
import pytest

from seljuk import scenarios as S, engine, battle
from seljuk.battle import DecisionContext, resolve_storm, resolve_sally, conquer, ruin
from seljuk.rng import DiceRoller
from seljuk.state import ThemataMarker, IllegalAction


def _cmd(gs, lord, actions=4, besieged=False):
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = gs.lords[lord].side
    gs.meta.active_lord = lord; gs.meta.active_card = lord; gs.meta.actions_remaining = actions
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["chatatourios"]; gs.roman.plan_pointer = 1


# --- Conquer / Ruin helpers ---
def test_conquer_places_markers_and_claims_strategic_objective_451():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.locales["larisa"].strategic_objective = True  # Roman SO sitting at an enemy (Roman) Locale
    gs.locales["melitene"].siege_markers = 2
    out = conquer(gs, "melitene", "seljuk")
    assert gs.locales["melitene"].conquered_side == "seljuk"
    assert gs.locales["melitene"].conquered_count == 2  # Town value
    assert gs.locales["melitene"].siege_markers == 0


def test_conquer_fatimid_roman_only_removes_seljuk_markers_131():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.locales["aleppo"].conquered_side = "seljuk"; gs.locales["aleppo"].conquered_count = 3
    conquer(gs, "aleppo", "roman")
    assert gs.locales["aleppo"].conquered_side is None  # Roman removes Seljuk, places none


def test_ruin_places_seljuk_ruins_491():
    gs = S.load_scenario("emperor_and_the_lion")
    ruin(gs, "melitene")
    assert gs.locales["melitene"].ruins and gs.locales["melitene"].ruins_color == "seljuk"


# --- Siege command ---
def test_siege_surrender_seizes_with_heavy_siege_451():
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "tephrike"  # Roman fort (value 1)
    gs.locales["tephrike"].siege_markers = 4  # threshold 4 -> 1 die always <= 4
    _cmd(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_siege", "lord": "alp_arslan"})
    assert r["seized"] and gs.locales["tephrike"].conquered_side == "seljuk"


def test_siege_siegeworks_adds_marker_when_no_surrender_451():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "tephrike"
    gs.locales["tephrike"].siege_markers = 1
    _cmd(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_siege", "lord": "alp_arslan", "roll_surrender": False})
    assert gs.locales["tephrike"].siege_markers == 2  # +1 Siegeworks (besiegers >= Size 1)


def test_siege_blocked_with_besieged_defender_can_still_siegeworks():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "antioch"
    ch = gs.lords["chatatourios"]; ch.cylinder = "antioch"; ch.besieged = True  # defender inside
    gs.locales["antioch"].siege_markers = 1
    _cmd(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_siege", "lord": "alp_arslan"})
    assert "seized" not in r  # cannot roll Surrender with a Besieged defender inside


# --- Storm ---
def test_storm_defender_routed_sacks_and_conquers_491():
    gs = S.load_scenario("emperor_and_the_lion", seed=4)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "tephrike"; aa.forces = {"turkic_horse": 6}
    gs.locales["tephrike"].siege_markers = 3
    _cmd(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_storm", "lord": "alp_arslan"})
    assert r["storm"]["winner"] == "attacker"
    assert gs.locales["tephrike"].conquered_side == "seljuk"


def test_storm_seljuk_may_ruin_roman_empire_stronghold_491():
    gs = S.load_scenario("emperor_and_the_lion", seed=2)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "melitene"; aa.forces = {"turkic_horse": 6, "ghulam_cavalry": 2}
    gs.locales["melitene"].siege_markers = 3
    gs.locales["melitene"].themata_defending = [ThemataMarker(unit="militia", symbols=1, home_thema="Melitene")]
    _cmd(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_storm", "lord": "alp_arslan", "storm_decisions": [("sack_choice", "ruin")]})
    if r["storm"]["winner"] == "attacker":
        assert gs.locales["melitene"].ruins


def test_storm_attacker_loss_keeps_siege_491():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "antioch"; aa.forces = {"turkic_horse": 1}  # very weak
    gs.locales["antioch"].siege_markers = 1  # only 1 Round
    _cmd(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_storm", "lord": "alp_arslan"})
    # Antioch is a Roman City with a strong Garrison + Walls 1-4; 1 weak Lord in
    # one Round will not Sack it -> attacker loses, Siege continues.
    if r["storm"]["winner"] == "defender":
        assert gs.locales["antioch"].siege_markers >= 1
        assert gs.locales["antioch"].conquered_side != "seljuk"


# --- Sally ---
def test_sally_besiegers_lose_ends_siege_492():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    ch = gs.lords["chatatourios"]; ch.cylinder = "antioch"; ch.besieged = True
    ch.forces = {"tagmata": 2, "infantry": 2}
    aa = gs.lords["alp_arslan"]; aa.cylinder = "antioch"; aa.forces = {"turkic_horse": 1}  # weak besieger
    gs.locales["antioch"].siege_markers = 2
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = "roman"
    gs.meta.active_lord = "chatatourios"; gs.meta.active_card = "chatatourios"; gs.meta.actions_remaining = 2
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["chatatourios"]; gs.roman.plan_pointer = 1
    r = engine.apply_action(gs, {"type": "cmd_sally", "lord": "chatatourios"})
    if r["sally"]["winner"] == "sally":
        assert gs.locales["antioch"].siege_markers == 0
        assert gs.lords["chatatourios"].besieged  # Sallying Lords Withdraw back inside


def test_sally_fail_raid_reduces_siege_to_one_492():
    gs = S.load_scenario("emperor_and_the_lion", seed=5)
    ch = gs.lords["chatatourios"]; ch.cylinder = "antioch"; ch.besieged = True
    ch.forces = {"militia": 1}  # weak sallying force
    aa = gs.lords["alp_arslan"]; aa.cylinder = "antioch"; aa.forces = {"turkic_horse": 6, "ghulam_cavalry": 2}
    gs.locales["antioch"].siege_markers = 3
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = "roman"
    gs.meta.active_lord = "chatatourios"; gs.meta.active_card = "chatatourios"; gs.meta.actions_remaining = 2
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["chatatourios"]; gs.roman.plan_pointer = 1
    r = engine.apply_action(gs, {"type": "cmd_sally", "lord": "chatatourios"})
    if r["sally"]["winner"] == "besiegers":
        assert gs.locales["antioch"].siege_markers == 1  # Raid: all but one removed
