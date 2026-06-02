"""Audit fixes: Manuel-Commander on-map test, Aleppo friendly-both, and the
4.3.6 Encamp / Sortie commands."""
import pytest
from seljuk import scenarios as S, campaign, actions, engine
from seljuk.rng import DiceRoller


def test_manuel_commander_only_when_romanos_off_map():
    gs = S.load_scenario("manzikert")
    rom = gs.lords["romanos_diogenes"]
    rom.mustered = True; rom.cylinder = "melitene"      # on the map
    assert actions.is_commander(gs, "manuel_komnenos") is False
    rom.mustered = True; rom.cylinder = "calendar"      # mustered but OFF the map
    assert actions.is_commander(gs, "manuel_komnenos") is True


def test_aleppo_friendly_to_both_after_independence():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.notes["aleppo_friendly_both"] = True
    assert actions.is_friendly_locale(gs, "aleppo", "seljuk") is True
    assert actions.is_friendly_locale(gs, "aleppo", "roman") is True


def test_encamp_converts_bypass_to_siege():
    gs = S.load_scenario("emperor_and_the_lion")
    loc = "melitene"
    sav = gs.lords["sav_tekin"]; sav.mustered = True; sav.cylinder = loc; sav.bypassed = True
    gs.locales[loc].bypass = True
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "sav_tekin"
    gs.meta.active_card = "sav_tekin"; gs.meta.actions_remaining = 2
    gs.seljuk.command_plan = ["sav_tekin"]; gs.seljuk.plan_pointer = 1
    engine.apply_action(gs, {"type": "cmd_encamp", "lord": "sav_tekin"})
    assert gs.locales[loc].bypass is False
    assert gs.locales[loc].siege_markers >= 1
    assert gs.lords["sav_tekin"].bypassed is False


def test_sortie_triggers_battle_vs_bypasser():
    gs = S.load_scenario("emperor_and_the_lion")
    loc = "ani"   # Seljuk-allegiance Locale
    defender = gs.lords["afsin_beg"]; defender.mustered = True; defender.cylinder = loc
    defender.forces = {"ghulam_cavalry": 3}
    bypasser = gs.lords["chatatourios"]; bypasser.mustered = True; bypasser.cylinder = loc
    bypasser.side = "roman"; bypasser.bypassed = True; bypasser.forces = {"tagmata": 2}
    gs.locales[loc].bypass = True
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "afsin_beg"
    gs.meta.active_card = "afsin_beg"; gs.meta.actions_remaining = 2
    gs.seljuk.command_plan = ["afsin_beg"]; gs.seljuk.plan_pointer = 1
    r = engine.apply_action(gs, {"type": "cmd_sortie", "lord": "afsin_beg"})
    assert r["action"] == "cmd_sortie" and "battle" in r
