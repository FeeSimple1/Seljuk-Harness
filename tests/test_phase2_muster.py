"""Phase 2 Levy: Muster (3.4) — Levy Lords, Vassals, Transport, Capabilities, Themata."""
import pytest

from seljuk import scenarios as S, engine, static_data as sd
from seljuk.actions import lordship_remaining
from seljuk.state import IllegalAction


def _to_muster(scenario="emperor_and_the_lion", seed=1):
    gs = S.load_scenario(scenario, seed=seed)
    engine.start_levy(gs)
    engine.apply_action(gs, {"type": "pass_step"})  # Seljuk done Pay
    engine.apply_action(gs, {"type": "pass_step"})  # Roman done Pay -> Disband -> Muster
    assert gs.meta.subphase == "levy.muster"
    return gs


def test_levy_transport_adds_cart_and_spends_lordship_343():
    gs = _to_muster()
    aa = gs.lords["alp_arslan"]
    before = aa.assets.carts
    engine.apply_action(gs, {"type": "levy_transport", "lord": "alp_arslan"})
    assert aa.assets.carts == before + 1
    assert lordship_remaining(gs, aa) == sd.lord("alp_arslan")["ratings"]["lordship"] - 1


def test_levy_capability_this_lord_attaches_and_leaves_deck_344():
    gs = _to_muster()
    engine.apply_action(gs, {"type": "levy_capability", "lord": "alp_arslan", "card": "S1"})
    assert "S1" in gs.lords["alp_arslan"].capabilities
    assert "S1" not in gs.seljuk.draw_deck


def test_levy_capability_max_two_this_lord_no_duplicate_344():
    gs = _to_muster()
    aa = gs.lords["alp_arslan"]
    aa.flags["lordship_spent"] = 0
    # Alp Arslan eligible: S1 (Lamellar), S4 (Shock Tactics), S16 (Parthian Shot)...
    engine.apply_action(gs, {"type": "levy_capability", "lord": "alp_arslan", "card": "S1"})
    engine.apply_action(gs, {"type": "levy_capability", "lord": "alp_arslan", "card": "S4"})
    # third "This Lord" cap rejected (max 2)
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "levy_capability", "lord": "alp_arslan", "card": "S16"})


def test_levy_capability_side_wide_goes_to_board_edge_344():
    gs = _to_muster()
    # S8 Marwanid Alliance is ALL -> board edge.
    engine.apply_action(gs, {"type": "levy_capability", "lord": "alp_arslan", "card": "S8"})
    assert "S8" in gs.seljuk.capabilities_in_play
    assert "S8" not in gs.lords["alp_arslan"].capabilities


def test_levy_capability_rejects_ineligible_lord_344():
    gs = _to_muster()
    # S5 Forced Conscription is Sav-Tekin only; Alp Arslan may not Levy it.
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "levy_capability", "lord": "alp_arslan", "card": "S5"})


def test_levy_vassal_adds_forces_342():
    gs = _to_muster()
    aa = gs.lords["alp_arslan"]
    # vassal #0 = 2 Turkic Horse
    th_before = aa.forces.get("turkic_horse", 0)
    engine.apply_action(gs, {"type": "levy_vassal", "lord": "alp_arslan", "vassal_index": 0})
    assert aa.forces["turkic_horse"] == th_before + 2
    assert aa.vassals[0].levied


def test_special_vassal_requires_its_capability_342():
    gs = _to_muster()
    aa = gs.lords["alp_arslan"]
    # Elite Ghulam Cavalry slot requires S20; not in play -> not levyable.
    sv_idx = next(i for i, v in enumerate(aa.vassals) if v.requires_capability == "S20")
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "levy_vassal", "lord": "alp_arslan", "vassal_index": sv_idx})


def test_levy_lord_fealty_roll_musters_ready_target_341():
    gs = _to_muster()
    # Make Afsin Beg Ready in the current box and have Alp Arslan roll for him.
    gs.lords["afsin_beg"].cylinder_calendar_box = gs.meta.calendar_box
    aa = gs.lords["alp_arslan"]
    mustered = False
    while lordship_remaining(gs, aa) > 0 and not mustered:
        r = engine.apply_action(gs, {"type": "levy_lord", "levyer": "alp_arslan", "target": "afsin_beg"})
        assert r["success"] == (r["roll"] <= r["fealty"])
        mustered = r["success"]
    if mustered:
        ab = gs.lords["afsin_beg"]
        assert ab.mustered and ab.cylinder in sd.lord("afsin_beg")["seats"]
        assert ab.service_box == gs.meta.calendar_box + sd.lord("afsin_beg")["ratings"]["service"]
        assert ab.flags.get("mustered_this_segment")  # may not Levy this segment (3.4)


def test_newly_mustered_lord_cannot_levy_this_segment_34():
    gs = _to_muster()
    gs.lords["afsin_beg"].cylinder_calendar_box = gs.meta.calendar_box
    aa = gs.lords["alp_arslan"]
    # force a muster
    while lordship_remaining(gs, aa) > 0 and not gs.lords["afsin_beg"].mustered:
        engine.apply_action(gs, {"type": "levy_lord", "levyer": "alp_arslan", "target": "afsin_beg"})
    if gs.lords["afsin_beg"].mustered:
        with pytest.raises(IllegalAction):
            engine.apply_action(gs, {"type": "levy_transport", "lord": "afsin_beg"})


def test_levy_themata_roman_commander_only_345():
    gs = S.load_scenario("year_of_treacherous_ambition", seed=2)
    # Manuel (Commander) is at Constantinople (Paphlagonia has no Themata box);
    # put a friendly Roman Commander in a Thema with markers to exercise the rule.
    engine.start_levy(gs)
    # advance to muster
    engine.apply_action(gs, {"type": "pass_step"})
    engine.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.subphase == "levy.muster"
    gs.meta.active_player = "roman"
    gs.meta.levy_step_passed = {}
    man = gs.lords["manuel_komnenos"]
    man.flags.pop("mustered_this_segment", None)
    man.cylinder = "kaisareia"  # Charsianon Thema (has a Militia after removals)
    before = len(gs.themata["Charsianon"])
    r = engine.apply_action(gs, {"type": "levy_themata", "lord": "manuel_komnenos", "thema": "Charsianon", "marker_index": 0})
    assert len(gs.themata["Charsianon"]) == before - 1
    assert len(man.themata_on_mat) == 1 and man.themata_on_mat[0].home_thema == "Charsianon"


def test_non_commander_cannot_levy_themata_345():
    gs = S.load_scenario("emperor_and_the_lion")
    engine.start_levy(gs)
    engine.apply_action(gs, {"type": "pass_step"})
    engine.apply_action(gs, {"type": "pass_step"})
    gs.meta.active_player = "roman"
    gs.meta.levy_step_passed = {}
    ch = gs.lords["chatatourios"]  # not a Commander
    ch.cylinder = "kaisareia"
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "levy_themata", "lord": "chatatourios", "thema": "Charsianon"})


def test_enumerator_offers_no_levy_for_lordship_exhausted_lord_341():
    """Negative-enumerator guard (cross-harness over-enumeration class): once a
    Lord has spent all his Lordship this Levy (3.4), the Muster menu must offer
    him NO levy_* action. enumerate_muster filters actors by _can_act_in_muster,
    the same predicate h_levy_* enforces, so the menu can't drift from the
    handler (cf. a sibling harness that offered levy_capability after
    lordship_exhausted)."""
    from seljuk.actions import _can_act_in_muster
    gs = _to_muster()
    actors = [lid for lid, l in gs.lords.items() if _can_act_in_muster(gs, l)]
    assert actors, "need at least one Lord with Lordship to exercise the gate"
    lid = actors[0]
    lord = gs.lords[lid]
    rating = sd.lord(lid)["ratings"]["lordship"] + int(lord.flags.get("lordship_bonus", 0))
    lord.flags["lordship_spent"] = rating  # exhaust his Lordship
    assert lordship_remaining(gs, lord) == 0 and not _can_act_in_muster(gs, lord)
    offered = [m for m in engine.legal_moves(gs)
               if m.get("levyer") == lid or m.get("lord") == lid]
    assert offered == [], f"menu over-enumerated for a Lordship-exhausted Lord: {offered}"
