"""Phase 4: R1 Imperial Fortress Construction -- build a Fort (Command), which
then acts as a size-1 Stronghold."""
import pytest
from seljuk import scenarios as S, campaign, battle, engine
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _roman_cmd(gs, lid):
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "roman"; gs.meta.active_lord = lid
    gs.meta.active_card = lid; gs.meta.actions_remaining = 2
    gs.roman.command_plan = [lid]; gs.roman.plan_pointer = 1


def test_r1_build_fort_and_remove_seljuk_ruins():
    gs = S.load_scenario("emperor_and_the_lion")
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = "to_constantinople"
    rom.capabilities = ["R1"]
    gs.locales["western_anatolia"].ruins = True
    gs.locales["western_anatolia"].ruins_color = "seljuk"
    _roman_cmd(gs, "romanos_diogenes")
    engine.apply_action(gs, {"type": "cmd_fort", "lord": "romanos_diogenes", "target": "western_anatolia"})
    assert gs.locales["western_anatolia"].fort_marker is True
    assert gs.locales["western_anatolia"].ruins is False       # Seljuk Ruins removed
    # Acts as a Stronghold now.
    assert campaign._is_stronghold(gs, "western_anatolia") is True
    assert battle._eff_value(gs, "western_anatolia") == 1       # Fort = Size 1


def test_r1_fort_impedes_seljuk_march_and_can_be_conquered():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.locales["western_anatolia"].fort_marker = True
    sav = gs.lords["sav_tekin"]; sav.mustered = True; sav.cylinder = "ikonion"
    # A Seljuk Lord marching in must Besiege/Bypass the Fort.
    r = campaign._resolve_arrival(gs, [sav], "western_anatolia")
    assert r.get("pending") == "besiege_or_bypass"
    # Conquering it captures the Fort (marker removed).
    battle.conquer(gs, "western_anatolia", "seljuk")
    assert gs.locales["western_anatolia"].conquered_side == "seljuk"
    assert gs.locales["western_anatolia"].fort_marker is False


def test_r1_two_fort_limit():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.locales["western_anatolia"].fort_marker = True
    gs.locales["lykandos"].fort_marker = True
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.capabilities = ["R1"]
    _roman_cmd(gs, "romanos_diogenes")
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cmd_fort", "lord": "romanos_diogenes", "target": "charsianon"})
