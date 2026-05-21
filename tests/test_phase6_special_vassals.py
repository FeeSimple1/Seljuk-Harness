"""Phase 6 (R1): special-Vassal-adder Capabilities (R2/R7/R17/S20)."""
from seljuk import scenarios as S, engine
from seljuk.actions import reset_muster_segment


def _muster_ctx(gs, side):
    engine.start_levy(gs)
    gs.meta.subphase = "levy.muster"; gs.meta.active_player = side; gs.meta.levy_step_passed = {}
    reset_muster_segment(gs)


def test_s20_adds_elite_ghulam_slot_to_non_printed_lord():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _muster_ctx(gs, "seljuk")
    sav = gs.lords["sav_tekin"]; sav.mustered = True; sav.cylinder = "ani"; sav.flags.pop("mustered_this_segment", None)
    engine.apply_action(gs, {"type": "levy_capability", "lord": "sav_tekin", "card": "S20"})
    slots = [v for v in sav.vassals if v.requires_capability == "S20"]
    assert len(slots) == 1 and slots[0].forces == {"ghulam_cavalry": 1}


def test_r2_oghuz_added_to_any_roman():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _muster_ctx(gs, "roman")
    ch = gs.lords["chatatourios"]; ch.flags.pop("mustered_this_segment", None)
    engine.apply_action(gs, {"type": "levy_capability", "lord": "chatatourios", "card": "R2"})
    slots = [v for v in ch.vassals if v.requires_capability == "R2"]
    assert len(slots) == 1 and slots[0].forces == {"turkic_horse": 2}


def test_r7_not_double_added_to_romanos_printed_slot():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _muster_ctx(gs, "roman")
    rom = gs.lords["romanos_diogenes"]; rom.flags.pop("mustered_this_segment", None)
    engine.apply_action(gs, {"type": "levy_capability", "lord": "romanos_diogenes", "card": "R7"})
    assert sum(1 for v in rom.vassals if v.requires_capability == "R7") == 1
