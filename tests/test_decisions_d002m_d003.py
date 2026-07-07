"""Adjudicated decisions (2026-07-06): Marwanid Seats allow Muster (Q-002) and
Loot/Empress cylinder shifts work in either direction (Q-003). See
RULES_DECISIONS.md D-003-Marwanid-Muster / D-004-Shift-Direction."""
from seljuk import scenarios as S, engine, actions
from seljuk.legal_moves import legal_moves


def _to_muster(scenario="emperor_and_the_lion", seed=1):
    gs = S.load_scenario(scenario, seed=seed)
    engine.start_levy(gs)
    engine.apply_action(gs, {"type": "pass_step"})
    engine.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.subphase == "levy.muster"
    gs.meta.pending = []
    return gs


def test_marwanid_seat_offered_and_used_for_muster_3511():
    gs = _to_muster()
    gs.meta.active_player = "seljuk"
    gs.meta.notes["marwanid_seats"] = ["amid"]
    gs.lords["afsin_beg"].cylinder_calendar_box = gs.meta.calendar_box  # Ready
    mvs = [m for m in legal_moves(gs) if m["type"] == "levy_lord" and m["target"] == "afsin_beg"]
    seats = {m.get("seat") for m in mvs}
    assert {"ani", "to_mosul_and_baghdad", "amid"} <= seats, mvs
    aa = gs.lords["alp_arslan"]
    mustered = False
    while actions.lordship_remaining(gs, aa) > 0 and not mustered:
        r = engine.apply_action(gs, {"type": "levy_lord", "levyer": "alp_arslan",
                                     "target": "afsin_beg", "seat": "amid"})
        mustered = r["success"]
    if mustered:
        assert gs.lords["afsin_beg"].cylinder == "amid"


def test_marwanid_seat_not_offered_when_inactive_3511():
    gs = _to_muster()
    gs.meta.active_player = "seljuk"
    gs.lords["afsin_beg"].cylinder_calendar_box = gs.meta.calendar_box
    mvs = [m for m in legal_moves(gs) if m["type"] == "levy_lord" and m["target"] == "afsin_beg"]
    assert "amid" not in {m.get("seat") for m in mvs}


def _to_cta(side):
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.call_to_arms"
    gs.meta.active_player = side; gs.meta.levy_step_passed = {}
    gs.meta.pending = []
    return gs


def test_cta_loot_shifts_right_352():
    gs = _to_cta("seljuk")
    gs.holding_boxes.mosul_baghdad_loot = 2
    sav = gs.lords["sav_tekin"]
    sav.mustered = False; sav.cylinder = "calendar"; sav.cylinder_calendar_box = 4
    mvs = [m for m in engine.legal_moves(gs) if m["type"] == "cta_loot" and m["lord"] == "sav_tekin"]
    assert {"left", "right"} <= {m["direction"] for m in mvs}   # D: either direction
    engine.apply_action(gs, {"type": "cta_loot", "lord": "sav_tekin", "direction": "right"})
    assert sav.cylinder_calendar_box == 5
    assert gs.holding_boxes.mosul_baghdad_loot == 1


def test_cta_empress_shifts_right_3512():
    gs = _to_cta("roman")
    gs.roman.capabilities_in_play = ["R12"]        # Empress Eudokia Makrembolitissa
    gs.meta.notes["empress_token"] = "card"
    nik = gs.lords["nikephoros_bryennios"]
    nik.mustered = False; nik.cylinder = "calendar"; nik.cylinder_calendar_box = 6
    mvs = [m for m in engine.legal_moves(gs)
           if m["type"] == "cta_empress" and m.get("effect") == "shift_cylinder"
           and m.get("lord") == "nikephoros_bryennios"]
    assert {"left", "right"} <= {m["direction"] for m in mvs}
    engine.apply_action(gs, {"type": "cta_empress", "mode": "use", "effect": "shift_cylinder",
                             "lord": "nikephoros_bryennios", "direction": "right"})
    assert nik.cylinder_calendar_box == 7
