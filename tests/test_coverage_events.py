"""Aggressive coverage of Event/Hold-Event resolver guard and edge branches."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S
from seljuk import events as E
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _r():
    return DiceRoller(seed=1)


# --- _shift_calendar guards -------------------------------------------------
def test_shift_calendar_guards():
    gs = _gs()
    with pytest.raises(IllegalAction):
        E._shift_calendar(gs, "nope", "cylinder", "left")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "ani"; aa.cylinder_calendar_box = None
    with pytest.raises(IllegalAction):           # not on calendar
        E._shift_calendar(gs, "alp_arslan", "cylinder", "left")
    aa.service_box = None
    with pytest.raises(IllegalAction):           # no service marker
        E._shift_calendar(gs, "alp_arslan", "service", "left")
    with pytest.raises(IllegalAction):           # bad 'what'
        E._shift_calendar(gs, "alp_arslan", "banana", "left")


def test_shift_calendar_cylinder_and_service_ok():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.cylinder = "calendar"; aa.cylinder_calendar_box = 5
    assert E._shift_calendar(gs, "alp_arslan", "cylinder", "right")["box"] == 6
    aa.service_box = 4
    assert E._shift_calendar(gs, "alp_arslan", "service", "left")["box"] == 3


def test_remove_themata_no_match():
    gs = _gs()
    with pytest.raises(IllegalAction):
        E._remove_themata(gs, "Charsianon", unit="does_not_exist")


# --- per-card no_op / guard branches ---------------------------------------
def test_r11_chrysoskoulos_no_op_when_arisighi_not_roman():
    gs = _gs(); gs.lords["arisighi"].side = "seljuk"
    assert E._ev_chrysoskoulos(gs, {}, _r()).get("no_op") is True


def test_r16_anglo_saxon_no_op_paths():
    gs = _gs()
    # Robert is excluded
    assert E._ev_anglo_saxon(gs, {"lord": "robert_crepin"}, _r()).get("no_op") is True
    # A Roman lord who already has a Varangian
    ch = gs.lords["chatatourios"]; ch.side = "roman"; ch.forces["varangian_guard"] = 1
    assert E._ev_anglo_saxon(gs, {"lord": "chatatourios"}, _r()).get("no_op") is True


def test_r22_assassination_shift_vs_disband():
    gs = _gs(); ik = gs.lords["ibn_khan"]
    ik.mustered = True; ik.cylinder = "aleppo"; ik.service_box = 6
    out = E._ev_assassination(gs, {}, _r())          # within 2 of Aleppo -> service shift
    assert out.get("shifted") == "service"
    gs2 = _gs(); ik2 = gs2.lords["ibn_khan"]
    ik2.mustered = True; ik2.cylinder = "larisa"      # far from Aleppo -> disband
    out2 = E._ev_assassination(gs2, {}, _r())
    assert out2.get("disbanded") == "ibn_khan"


def test_s11_norman_scheming_no_op():
    gs = _gs()
    gs.lords["robert_crepin"].side = "roman"; gs.lords["roussel_de_bailleul"].side = "roman"
    assert E._ev_norman_scheming(gs, {}, _r()).get("no_op") is True


def test_s15_thematic_desert_no_op_when_not_in_thema():
    gs = _gs(); gs.lords["alp_arslan"].mustered = False
    assert E._ev_thematic_desert(gs, {}, _r()).get("no_op") is True


def test_s22_massacre_requires_enemy_locale():
    from seljuk import actions
    gs = _gs()
    # An eligible Seljuk Lord IS at an Enemy Locale (so this is not a no-op)...
    loc = next(lid for lid in gs.locales if actions.current_allegiance(gs, lid) == "roman")
    st = gs.lords["sav_tekin"]; st.mustered = True; st.cylinder = loc
    # ...but the CHOSEN Lord sits at a Seljuk-controlled Locale -> rejected (S22).
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    with pytest.raises(IllegalAction):
        E._ev_massacre(gs, {"lord": "alp_arslan"}, _r())


def test_r14_aleppo_independence_no_op_when_conquered():
    gs = _gs(); gs.locales["aleppo"].conquered_side = "seljuk"
    assert E._ev_aleppo_independence(gs, {}, _r()).get("no_op") is True


def test_r20_bad_locale_and_s7_bad_thema():
    gs = _gs()
    with pytest.raises(IllegalAction):
        E._ev_armenian_resistance(gs, {"locale": "ani"}, _r())
    with pytest.raises(IllegalAction):
        E._ev_deserters(gs, {"thema": "NotABorderThema"}, _r())


def test_r1_flooded_river_already_marked_applies_lordship_penalty():
    gs = _gs(); gs.meta.asterisks_used.append("R1")
    out = E._ev_flooded_river(gs, {"lord": "alp_arslan"}, _r())
    assert out.get("already_marked") is True
    assert gs.lords["alp_arslan"].flags.get("lordship_spent") == 1


def test_s8_merchant_financing_both_directions():
    gs = _gs(); l = gs.lords["alp_arslan"]; l.assets.carts = 3; l.assets.coin = 2
    E._ev_merchant_financing(gs, {"lord": "alp_arslan", "to": "coin", "amount": 2}, _r())
    assert l.assets.carts == 1 and l.assets.coin == 4
    E._ev_merchant_financing(gs, {"lord": "alp_arslan", "to": "carts", "amount": 1}, _r())
    assert l.assets.coin == 3 and l.assets.carts == 2


# --- resolve_event wrapper branches ----------------------------------------
def _queue_event(gs, card, side="seljuk"):
    gs.meta.pending.append({"type": "event_pending_resolution", "card": card, "side": side})


def test_resolve_event_no_pending():
    gs = _gs()
    with pytest.raises(IllegalAction):
        E.resolve_event(gs, "R5", {}, _r())


def test_resolve_event_unimplemented_card_is_discarded():
    gs = _gs(); _queue_event(gs, "ZZ", "seljuk")
    out = E.resolve_event(gs, "ZZ", {}, _r())
    assert out["no_op"] is True
    assert not any(p["card"] == "ZZ" for p in gs.meta.pending)


def test_resolve_event_missing_arg_raises_illegal():
    gs = _gs(); _queue_event(gs, "R5", "roman")
    with pytest.raises(IllegalAction):           # R5 needs args['lord']
        E.resolve_event(gs, "R5", {}, _r())


def test_resolve_event_success_returns_card_to_deck():
    gs = _gs(); aa = gs.lords["alp_arslan"]; aa.cylinder = "calendar"; aa.cylinder_calendar_box = 5
    _queue_event(gs, "R5", "roman")
    before = list(gs.roman.draw_deck)
    out = E.resolve_event(gs, "R5", {"lord": "alp_arslan"}, _r())
    assert out["ok"] and "R5" in gs.roman.draw_deck and "R5" not in [c for c in before if c == "R5"] or "R5" in gs.roman.draw_deck


# --- play_hold_event wrapper + hold guards ---------------------------------
def test_play_hold_not_held_and_not_implemented():
    gs = _gs()
    with pytest.raises(IllegalAction):           # not in hand
        E.play_hold_event(gs, "R6", {}, _r())
    gs.roman.held_events.append("R2")            # a Battle hold w/o self-contained hook
    with pytest.raises(IllegalAction):
        E.play_hold_event(gs, "R2", {}, _r())


def test_hold_summer_heat_timing_and_season_guards():
    gs = _gs(); gs.roman.held_events.append("R3")
    gs.meta.subphase = "levy.muster"             # wrong timing
    with pytest.raises(IllegalAction):
        E.play_hold_event(gs, "R3", {}, _r())
    gs.meta.subphase = "campaign.command"; gs.meta.active_lord = "alp_arslan"
    gs.meta.calendar_box = 1                      # Spring, not Summer
    with pytest.raises(IllegalAction):
        E.play_hold_event(gs, "R3", {}, _r())


def test_hold_sultans_horse_not_applicable():
    gs = _gs(); gs.seljuk.held_events.append("R4")
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    gs.locales["ani"].siege_markers = 1          # needs > 1
    with pytest.raises(IllegalAction):
        E.play_hold_event(gs, "R4", {}, _r())


def test_hold_kleisourai_protected_and_eliminated_and_bad_target():
    gs = _gs(); gs.roman.held_events.append("R23")
    with pytest.raises(IllegalAction):           # must target a Seljuk lord
        E.play_hold_event(gs, "R23", {"lord": "chatatourios"}, _r())
    gs2 = _gs(); gs2.roman.held_events.append("R23")
    aa = gs2.lords["alp_arslan"]; aa.forces = {"turkic_horse": 1}
    out = E.play_hold_event(gs2, "R23", {"lord": "alp_arslan", "unit": "turkic_horse"}, DiceRoller(seed=2))
    assert ("eliminated" in out) or ("protected" in out)


def test_hold_bad_omens_no_op_when_fewer_than_two():
    gs = _gs(); gs.seljuk.held_events.append("S24")  # S24 is a Seljuk card
    gs.roman.command_plan = ["alp_arslan"]; gs.roman.plan_pointer = 0
    out = E.play_hold_event(gs, "S24", {}, _r())
    assert out.get("no_op") is True


# --- additional event branches ---------------------------------------------
def test_discard_random_held_no_op_when_none():
    gs = _gs(); gs.lords["arisighi"].side = "roman"; gs.seljuk.held_events.clear()
    assert E._ev_chrysoskoulos(gs, {}, _r()).get("no_op") is True


def test_s25_mercenary_discipline_wastes_roman_on_ravaged():
    gs = _gs(); ch = gs.lords["chatatourios"]
    ch.side = "roman"; ch.mustered = True; ch.cylinder = "ani"
    ch.assets.carts = 3
    gs.locales["ani"].ravaged_side = "seljuk"
    out = E._ev_mercenary_discipline(gs, {}, _r())
    assert out["roman_wastage"] >= 1


def test_s20_consolidates_power_lowers_unity():
    gs = _gs()
    # a permanently-disbanded Seljuk lord
    gs.lords["afsin_beg"].cylinder = "removed"
    gs.meta.seljuk_unity_targets = {"3": 2, "6": 3}
    out = E._ev_consolidates_power(gs, {}, _r())
    assert out["unity_lowered_by"] >= 1
    assert gs.meta.seljuk_unity_targets["6"] <= 3


def test_s5_siege_of_bari_removes_up_to_two_themata():
    gs = _gs()
    themas = [t for t, box in gs.themata.items() if box][:2]
    out = E._ev_siege_of_bari(gs, {"themata": themas}, _r())
    assert len(out["removed"]) <= 2
    assert "S5" in gs.meta.asterisks_used


def test_r13_thrakion_returns_themata_marker():
    gs = _gs()
    before = len(gs.themata.get("Charsianon", []))
    E._ev_thrakion(gs, {"thema": "Charsianon", "unit": "kavallarioi"}, _r())
    assert len(gs.themata["Charsianon"]) == before + 1


def test_kleisourai_no_op_when_no_units():
    gs = _gs(); gs.seljuk.held_events.append("R23")
    aa = gs.lords["alp_arslan"]; aa.forces = {}
    # R23 is a Roman card; put it in roman hand and target alp_arslan
    gs.seljuk.held_events.remove("R23"); gs.roman.held_events.append("R23")
    out = E.play_hold_event(gs, "R23", {"lord": "alp_arslan"}, _r())
    assert out.get("no_op") is True


def test_wastage_discards_capability_when_no_excess_asset():
    gs = _gs(); aa = gs.lords["alp_arslan"]
    aa.assets.carts = 1; aa.assets.provender = 0; aa.assets.coin = 0; aa.assets.loot = 0
    aa.capabilities = ["S1", "S4"]
    assert E._wastage_once(gs, aa) is True
    assert len(aa.capabilities) == 1


def test_s22_massacre_no_op_when_no_seljuk_lord_at_enemy_locale():
    """S22 (Massacre): with no Seljuk Lord at an Enemy Locale the Event is a
    clean no-op, not an error the consumer must hand-skip (ChatGPT report)."""
    from seljuk import actions
    gs = _gs()
    for l in gs.lords.values():           # clear all Seljuk Lords off the map
        if l.side == "seljuk":
            l.mustered = False; l.cylinder = "calendar"
    out = E._ev_massacre(gs, {}, _r())
    assert out.get("no_op") is True
    # with a Seljuk Lord at an Enemy (Roman) Locale, it adds Loot to the chosen Lord
    loc = next(lid for lid in gs.locales if actions.current_allegiance(gs, lid) == "roman")
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = loc; aa.assets.loot = 0
    with pytest.raises(IllegalAction):    # target exists but none chosen
        E._ev_massacre(gs, {}, _r())
    out2 = E._ev_massacre(gs, {"lord": "alp_arslan"}, _r())
    assert out2.get("loot_added") == "alp_arslan" and aa.assets.loot == 1
