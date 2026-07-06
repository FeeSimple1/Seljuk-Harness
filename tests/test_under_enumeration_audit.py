"""Second-pass under-enumeration audit (2026-07): legal moves the handlers
accepted but the palette never offered, plus the hint/window gaps around them.

Each test cites the rule it pins. Findings G-N in SMOKE_TEST_FINDINGS.md.
"""
import pytest

from seljuk import scenarios as S, engine, campaign, actions, static_data as sd
from seljuk.legal_moves import legal_moves
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction, ThemataMarker


def _cmd(gs, lord, side, actions_n=4):
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = side
    gs.meta.active_lord = lord; gs.meta.active_card = lord; gs.meta.actions_remaining = actions_n
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1


def _to_muster(scenario="emperor_and_the_lion", seed=1):
    gs = S.load_scenario(scenario, seed=seed)
    engine.start_levy(gs)
    engine.apply_action(gs, {"type": "pass_step"})
    engine.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.subphase == "levy.muster"
    gs.meta.pending = [p for p in gs.meta.pending if p["type"] != "deploy_capability"]
    return gs


# --- G. cmd_fort (R1 Imperial Fortress Construction) was never enumerated ---

def test_cmd_fort_enumerated_with_capability_r1():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    rom = gs.lords["romanos_diogenes"]
    rom.capabilities = ["R1"]
    _cmd(gs, "romanos_diogenes", "roman")
    mvs = [m for m in campaign.command_menu(gs) if m["type"] == "cmd_fort"]
    assert mvs, "R1 holder must be offered cmd_fort (was handler-only)"
    # Every offered target is an unfortified Roman-Empire Locale, never a Holding Box.
    for m in mvs:
        info = sd.locale(m["target"])
        assert info["allegiance"] == "roman" and info["type"] != "holding_box"
        assert not (info.get("is_stronghold") and not gs.locales[m["target"]].ruins)
        assert not gs.locales[m["target"]].fort_marker
    # Applying one places the Fort marker (card: 2 markers max on the map).
    r = engine.apply_action(gs, mvs[0])
    assert r["ok"] and gs.locales[mvs[0]["target"]].fort_marker


def test_cmd_fort_not_offered_without_capability_r1():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _cmd(gs, "romanos_diogenes", "roman")
    assert not [m for m in campaign.command_menu(gs) if m["type"] == "cmd_fort"]


def test_cmd_fort_rejects_holding_box_and_besieged_r1():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    rom = gs.lords["romanos_diogenes"]
    rom.capabilities = ["R1"]
    _cmd(gs, "romanos_diogenes", "roman")
    with pytest.raises(IllegalAction):
        campaign.h_cmd_fort(gs, {"lord": "romanos_diogenes", "target": "to_constantinople"}, DiceRoller(1))
    rom.besieged = True
    with pytest.raises(IllegalAction):  # 4.2.1: Besieged -> only Sally/Pass/Forage
        campaign.h_cmd_fort(gs, {"lord": "romanos_diogenes", "target": "western_anatolia"}, DiceRoller(1))


# --- H. levy_lord: the Muster Seat choice (3.4.1 "one of his free Seats") ---

def test_levy_lord_offers_each_free_seat_341():
    gs = _to_muster()
    gs.meta.active_player = "seljuk"
    gs.lords["afsin_beg"].cylinder_calendar_box = gs.meta.calendar_box  # Ready
    mvs = [m for m in legal_moves(gs) if m["type"] == "levy_lord" and m["target"] == "afsin_beg"]
    seats = {m.get("seat") for m in mvs}
    # Afsin Beg's printed Seats: Ani and the Mosul & Baghdad Holding Box.
    assert {"ani", "to_mosul_and_baghdad"} <= seats, mvs


def test_levy_lord_seat_choice_is_honored_341():
    gs = _to_muster()
    gs.meta.active_player = "seljuk"
    gs.lords["afsin_beg"].cylinder_calendar_box = gs.meta.calendar_box
    aa = gs.lords["alp_arslan"]
    mustered = False
    while actions.lordship_remaining(gs, aa) > 0 and not mustered:
        r = engine.apply_action(gs, {"type": "levy_lord", "levyer": "alp_arslan",
                                     "target": "afsin_beg", "seat": "to_mosul_and_baghdad"})
        mustered = r["success"]
    if mustered:
        assert gs.lords["afsin_beg"].cylinder == "to_mosul_and_baghdad"


# --- I. levy_themata / cmd_recruit: WHICH marker (3.4.5 / 4.5.7) ---

def test_levy_themata_offers_each_marker_kind_345():
    gs = _to_muster("year_of_treacherous_ambition", seed=2)
    gs.meta.active_player = "roman"
    gs.meta.levy_step_passed = {}
    man = gs.lords["manuel_komnenos"]
    man.flags.pop("mustered_this_segment", None)
    man.cylinder = "kaisareia"  # Charsianon
    gs.meta.pending = []        # clear owed AoW windows; this test drives the Muster menu
    gs.themata["Charsianon"] = [ThemataMarker(unit="militia", symbols=1),
                                ThemataMarker(unit="tagmata", symbols=1)]
    mvs = [m for m in legal_moves(gs) if m["type"] == "levy_themata"]
    kinds = {(gs.themata["Charsianon"][m["marker_index"]].unit) for m in mvs}
    assert kinds == {"militia", "tagmata"}, mvs
    # Choosing the Tagmata takes the Tagmata (not silently index 0).
    tag = next(m for m in mvs if gs.themata["Charsianon"][m["marker_index"]].unit == "tagmata")
    engine.apply_action(gs, tag)
    assert man.themata_on_mat[-1].unit == "tagmata"


def test_cmd_recruit_offers_each_marker_kind_457():
    gs = S.load_scenario("year_of_treacherous_ambition", seed=2)
    man = gs.lords["manuel_komnenos"]
    man.mustered = True; man.besieged = False; man.cylinder = "kaisareia"
    gs.themata["Charsianon"] = [ThemataMarker(unit="militia", symbols=1),
                                ThemataMarker(unit="tagmata", symbols=1)]
    _cmd(gs, "manuel_komnenos", "roman")
    mvs = [m for m in campaign.command_menu(gs) if m["type"] == "cmd_recruit"]
    kinds = {gs.themata["Charsianon"][m["marker_index"]].unit for m in mvs}
    assert kinds == {"militia", "tagmata"}, mvs
    tag = next(m for m in mvs if gs.themata["Charsianon"][m["marker_index"]].unit == "tagmata")
    engine.apply_action(gs, tag)
    assert man.themata_on_mat[-1].unit == "tagmata"


# --- J. cmd_march unstoppable (S18 Unstoppable Turkmen) was never enumerated ---

def test_march_unstoppable_variant_offered_and_applies_s18():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    sav = gs.lords["sav_tekin"]
    sav.mustered = True; sav.besieged = False; sav.cylinder = "manbij"
    sav.forces = {"turkic_horse": 3}
    sav.capabilities = ["S18"]
    for l in gs.lords.values():   # keep Edessa free of (enemy) Lords
        if l.id != "sav_tekin" and l.cylinder == "edessa":
            l.cylinder = "to_constantinople"
    _cmd(gs, "sav_tekin", "seljuk")
    mvs = [m for m in campaign.command_menu(gs)
           if m["type"] == "cmd_march" and m["to"] == "edessa" and m.get("unstoppable")]
    assert mvs, "S18 holder must be offered the Bypass-without-stopping March"
    r = engine.apply_action(gs, mvs[0])
    assert r.get("bypassed_without_stopping") == "edessa"
    assert gs.locales["edessa"].bypass and sav.bypassed
    # Without the Capability the variant is not offered.
    gs2 = S.load_scenario("emperor_and_the_lion", seed=1)
    s2 = gs2.lords["sav_tekin"]; s2.mustered = True; s2.cylinder = "manbij"; s2.forces = {"turkic_horse": 3}
    _cmd(gs2, "sav_tekin", "seljuk")
    assert not [m for m in campaign.command_menu(gs2) if m["type"] == "cmd_march" and m.get("unstoppable")]


# --- K. Sally honors Battle/Storm Hold Events (4.9.2: a Sally is a Battle) ---

def test_sally_consumes_r21_battle_event_492():
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "azaz"; aa.besieged = True; aa.forces = {"turkic_horse": 4, "ghulam_cavalry": 2}
    rom = gs.lords["romanos_diogenes"]
    rom.cylinder = "azaz"; rom.besieged = False; rom.forces = {"tagmata": 3, "infantry": 2}
    gs.locales["azaz"].siege_markers = 2
    gs.roman.held_events = ["R21"]
    _cmd(gs, "alp_arslan", "seljuk")
    turkic_before = aa.forces.get("turkic_horse", 0)
    r = engine.apply_action(gs, {"type": "cmd_sally", "lord": "alp_arslan",
                                 "battle_events": {"roman": ["R21"]}})
    assert r["ok"]
    assert "R21" not in gs.roman.held_events and "R21" in gs.roman.draw_deck  # consumed
    # The two Turkic Horse were removed BEFORE the Sally resolved (R21 text);
    # combat may remove more, so assert via the pre-battle removal ceiling.
    assert aa.forces.get("turkic_horse", 0) + aa.routed.get("turkic_horse", 0) + \
        aa.lost.get("turkic_horse", 0) <= turkic_before - 2


def test_cmd_sally_menu_hints_available_holds_492():
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "azaz"; aa.besieged = True; aa.forces = {"turkic_horse": 4}
    rom = gs.lords["romanos_diogenes"]
    rom.cylinder = "azaz"; rom.besieged = False; rom.forces = {"tagmata": 3}
    gs.locales["azaz"].siege_markers = 1
    gs.roman.held_events = ["R21"]
    _cmd(gs, "alp_arslan", "seljuk")
    mv = next(m for m in campaign.command_menu(gs) if m["type"] == "cmd_sally")
    assert mv.get("_battle_holds_available", {}).get("defender") == ["R21"]


# --- L. Storm hints: the DEFENDER's holds (R21/S21) and R4 Sultan's Horse ---

def test_cmd_storm_hints_defender_holds_and_r4():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "tephrike"; aa.besieged = False; aa.forces = {"turkic_horse": 6}
    gs.locales["tephrike"].siege_markers = 2
    gs.roman.held_events = ["R21", "R4"]
    _cmd(gs, "alp_arslan", "seljuk")
    mv = next(m for m in campaign.command_menu(gs) if m["type"] == "cmd_storm")
    assert mv["_storm_events_available"]["defender"] == ["R21"]
    assert mv.get("_r4_sultans_horse_available") is True
    # With 1 Siege marker R4's Storm effect is ineligible (card: >1 Siege marker).
    gs.locales["tephrike"].siege_markers = 1
    mv = next(m for m in campaign.command_menu(gs) if m["type"] == "cmd_storm")
    assert not mv.get("_r4_sultans_horse_available")


# --- M. R4 campaign window requires Alp Arslan BESIEGING (not Besieged) ---

def test_r4_campaign_hold_requires_alp_besieging():
    from seljuk import events
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "azaz"; aa.besieged = True          # Alp is the one under Siege
    gs.locales["azaz"].siege_markers = 2
    gs.roman.held_events = ["R4"]
    _cmd(gs, "romanos_diogenes", "roman")
    assert not [m for m in events.held_event_menu(gs) if m.get("card") == "R4"]
    with pytest.raises(IllegalAction):
        events.play_hold_event(gs, "R4", {}, DiceRoller(1))
    aa.besieged = False                                # Alp besieging -> offered
    assert [m for m in events.held_event_menu(gs) if m.get("card") == "R4"]


# --- N. Loyalty coin DRMs (1.4.1) and Lieutenants (4.1.3) are hinted ---

def test_loyalty_check_menu_hints_coin_budgets_141():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    rob = gs.lords["robert_crepin"]
    rob.mustered = True; rob.cylinder = "edessa"; rob.besieged = False
    aa = gs.lords["alp_arslan"]; aa.assets.coin = 2       # Seljuk Commander coin
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.pending = [{"type": "loyalty_check", "side": "seljuk",
                        "targets": ["robert_crepin"], "_owed_by": "seljuk"}]
    mv = next(m for m in campaign.legal_moves_campaign(gs) if m["type"] == "resolve_loyalty")
    assert mv["_max_coins_for"] == actions.loyalty_coin_budget(gs, "seljuk", "robert_crepin") == 2
    assert mv["_max_coins_against"] == actions.loyalty_coin_budget(gs, "roman", "robert_crepin")
    rob.besieged = True                                   # 1.4.1: owner may not resist
    mv = next(m for m in campaign.legal_moves_campaign(gs) if m["type"] == "resolve_loyalty")
    assert mv["_max_coins_against"] == 0


def test_build_plan_hints_lieutenant_options_413():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    for lid in ("artuk_beg", "sav_tekin"):
        gs.lords[lid].mustered = True; gs.lords[lid].cylinder = "ani"; gs.lords[lid].besieged = False
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.plan"
    gs.meta.active_player = "seljuk"; gs.meta.plan_submitted = {}
    mv = next(m for m in campaign.legal_moves_campaign(gs) if m["type"] == "build_plan")
    opts = mv["_lieutenant_options"]
    assert {"lieutenant": "artuk_beg", "lower_lord": "sav_tekin"} in opts
    assert {"lieutenant": "sav_tekin", "lower_lord": "artuk_beg"} in opts
    # A Commander never appears in a pair (4.1.3).
    assert not any("alp_arslan" in (o["lieutenant"], o["lower_lord"]) for o in opts)
