"""Phase 4: S5 Forced Conscription / S19 Baghdad Reinforcements -- restore 1
Lost unit for free during Muster (once per Muster phase)."""
import pytest
from seljuk import scenarios as S, engine, actions, battle
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def test_s5_restore_lost_unit_at_muster():
    gs = S.load_scenario("emperor_and_the_lion")
    sav = gs.lords["sav_tekin"]
    sav.mustered = True; sav.cylinder = "ani"          # Seljuk Friendly Locale
    sav.capabilities = ["S5"]                           # Forced Conscription
    sav.lost = {"turkic_horse": 2}; sav.forces = {}
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.muster"; gs.meta.active_player = "seljuk"
    assert "muster_restore" in {m["type"] for m in actions.enumerate_muster(gs)}
    engine.apply_action(gs, {"type": "muster_restore", "lord": "sav_tekin", "unit": "turkic_horse"})
    assert sav.forces.get("turkic_horse") == 1
    assert sav.lost["turkic_horse"] == 1
    # Once per Muster phase.
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "muster_restore", "lord": "sav_tekin", "unit": "turkic_horse"})
    # Reset clears the once-per-phase flag.
    actions.reset_muster_segment(gs)
    engine.apply_action(gs, {"type": "muster_restore", "lord": "sav_tekin", "unit": "turkic_horse"})
    assert sav.forces.get("turkic_horse") == 2


def test_no_restore_without_capability_or_lost_units():
    gs = S.load_scenario("emperor_and_the_lion")
    sav = gs.lords["sav_tekin"]; sav.mustered = True; sav.cylinder = "ani"
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.muster"; gs.meta.active_player = "seljuk"
    # No capability -> not offered, handler rejects.
    with pytest.raises(IllegalAction):
        actions.h_muster_restore(gs, {"lord": "sav_tekin", "unit": "turkic_horse"}, DiceRoller(1))


def test_loss_roll_records_lost_units():
    gs = S.load_scenario("emperor_and_the_lion")
    l = gs.lords["sav_tekin"]
    l.forces = {}; l.routed = {"militia": 3}; l.lost = {}
    battle._loss_roll(gs, l, harsh=True, roller=DiceRoller(1))  # harsh: most fail -> Lost
    assert l.lost.get("militia", 0) >= 1
