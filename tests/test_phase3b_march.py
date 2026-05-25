"""Phase 3b: March (4.3), costs (4.3.2-.3), Group March (4.3.1),
Besiege/Bypass (4.3.5), Approach (4.3.4)."""
import pytest

from seljuk import scenarios as S, engine, campaign, map as gmap
from seljuk.state import IllegalAction


def _activate(gs, lord_id, actions=4):
    gs.meta.phase = "campaign"
    gs.meta.subphase = "campaign.command"
    gs.meta.active_player = gs.lords[lord_id].side
    gs.meta.active_lord = lord_id
    gs.meta.active_card = lord_id
    gs.meta.actions_remaining = actions
    # ongoing plans so card-end hands off rather than cascading to End Campaign
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["chatatourios"]; gs.roman.plan_pointer = 1


def _way(a, b, t=None):
    w = [e for e in gmap.ways_between(a, b)]
    return next((e for e in w if t is None or e["type"] == t), w[0])


def test_march_cost_turkic_first_road_is_zero_433():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.forces = {"turkic_horse": 4}  # all-Turkic
    aa.assets.loot = 0; aa.assets.provender = 0
    cost = campaign.march_cost(gs, [aa], _way("ani", "mempet"), first_march=True)
    assert cost == 0


def test_march_cost_turkic_first_pass_is_one_433():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.forces = {"turkic_horse": 4}; aa.assets.loot = 0; aa.assets.provender = 0
    cost = campaign.march_cost(gs, [aa], _way("ani", "ararat", "pass"), first_march=True)
    assert cost == 1


def test_march_cost_laden_doubles_and_pass_adds_433():
    gs = S.load_scenario("emperor_and_the_lion")
    ch = gs.lords["chatatourios"]
    ch.forces = {"tagmata": 1}  # not all-Turkic
    ch.assets.loot = 1  # Laden
    cost = campaign.march_cost(gs, [ch], _way("melitene", "amid", "pass"), first_march=True)
    assert cost == 3  # 2 (Laden) + 1 (Pass)


def test_cmd_march_moves_and_spends_actions():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]  # at Ani
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "mempet", "way_type": "road"})
    assert aa.cylinder == "mempet" and aa.moved_fought
    assert r["cost"] == 1 and gs.meta.actions_remaining == 3


def test_holding_box_march_is_whole_card_433():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "nusaybin"  # Road-WC to Mosul & Baghdad (Seljuk Holding Box)
    _activate(gs, "alp_arslan", actions=4)
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "to_mosul_and_baghdad"})
    assert r["cost"] == 4  # consumed the whole card
    assert aa.cylinder == "to_mosul_and_baghdad"


def test_enemy_holding_box_rejected_131():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "western_anatolia"  # Road-WC to (Roman) Constantinople
    _activate(gs, "alp_arslan")
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "to_constantinople"})


def test_march_to_enemy_stronghold_triggers_besiege_or_bypass_435():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "larisa"  # Roman, adjacent to Melitene (Roman town)
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    assert r.get("pending") == "besiege_or_bypass"
    moves = engine.legal_moves(gs)
    assert {m["choice"] for m in moves} == {"besiege", "bypass"}


def test_besiege_places_siege_and_ends_card_435():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "besiege_bypass", "choice": "besiege"})
    assert gs.locales["melitene"].siege_markers == 1
    # Besieging a Roman Stronghold pauses for the Roman Themata-defender choice (4.3.5);
    # resolving it (assign none) then ends the card.
    assert r.get("pending") == "assign_themata_defenders"
    engine.apply_action(gs, {"type": "assign_themata_defenders", "markers": []})
    assert gs.meta.active_lord != "alp_arslan"  # card ended (4.3.5)


def test_bypass_sets_marker_and_continues_435():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    _activate(gs, "alp_arslan", actions=4)
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    engine.apply_action(gs, {"type": "besiege_bypass", "choice": "bypass"})
    assert gs.locales["melitene"].bypass and aa.bypassed
    assert gs.meta.active_lord == "alp_arslan"  # still active (actions remain)


def test_approach_enemy_lord_triggers_response_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"  # Roman defender
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    assert r.get("pending") == "approach_response"
    assert "chatatourios" in r["defenders"]


def test_approach_avoid_moves_defender_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"
    ch.assets.loot = 0; ch.assets.provender = 0  # Unladen so it may Avoid
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    # Melitene neighbors include Germanikeia (Roman, no enemy) -> a legal Avoid.
    engine.apply_action(gs, {"type": "respond_approach", "choices": {"chatatourios": {"action": "avoid", "to": "germanikeia"}}})
    assert ch.cylinder == "germanikeia" and ch.moved_fought


def test_approach_withdraw_into_friendly_stronghold_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"  # Roman friendly town
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    engine.apply_action(gs, {"type": "respond_approach", "choices": {"chatatourios": {"action": "withdraw"}}})
    assert ch.besieged and ch.cylinder == "melitene"


def test_approach_stand_resolves_battle_434():
    gs = S.load_scenario("emperor_and_the_lion", seed=5)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"; ch.forces = {"militia": 1}
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "respond_approach", "choices": {"chatatourios": {"action": "stand"}}})
    # Stand resolves the Battle immediately (4.8) and clears the pending marker.
    assert r["battle"]["winner"] in ("attacker", "defender")
    assert not any(p["type"] == "battle" for p in gs.meta.pending)


def test_group_march_moves_commander_and_co_located_431():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]  # Commander at Ani
    ar = gs.lords["arisighi"]; ar.cylinder = "ani"  # co-locate
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "mempet", "way_type": "road", "group": ["arisighi"]})
    assert aa.cylinder == "mempet" and ar.cylinder == "mempet"


def test_avoid_blocked_when_laden_434():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"
    ch.assets.loot = 2  # Laden -> cannot Avoid
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "respond_approach", "choices": {"chatatourios": {"action": "avoid", "to": "germanikeia"}}})


def test_bypass_marker_cleared_when_bypasser_leaves_smoke005():
    """SMOKE-005 (4.3.5/4.4.1): "Whenever a Bypassed Stronghold becomes free of
    Enemy Lords, remove all Bypass markers." When the bypassing Lord marches
    away the marker (and his `bypassed` flag) must clear, so a later un-bypassed
    enemy Lord entering the Locale is correctly Approached (4.3.4) instead of
    being silently ignored by a stale Bypass marker."""
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    _activate(gs, "alp_arslan", actions=4)
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    engine.apply_action(gs, {"type": "besiege_bypass", "choice": "bypass"})
    assert gs.locales["melitene"].bypass and aa.bypassed
    # March back out: Melitene is now free of enemy Lords -> Bypass marker gone.
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "larisa", "way_type": "road"})
    assert not gs.locales["melitene"].bypass, "stale Bypass marker not cleared on departure"
    assert not aa.bypassed, "stale bypassed flag not cleared on departure"


def test_besieged_flag_cleared_when_besiegers_leave_smoke007():
    """SMOKE-007 (Inferno advisory #2 Door B): when the besiegers March away and
    the Stronghold becomes free of enemy Lords, a Lord who Withdrew inside is no
    longer Besieged. A stale `besieged` flag would otherwise persist forever and
    corrupt Sally/March/Feed legality."""
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"
    d = gs.lords["chatatourios"]; d.cylinder = "melitene"; d.besieged = True; d.forces = {"infantry": 2}
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "besiege_bypass", "choice": "besiege"})
    if r.get("pending") == "assign_themata_defenders":
        engine.apply_action(gs, {"type": "assign_themata_defenders", "markers": []})
    assert gs.locales["melitene"].siege_markers == 1 and d.besieged
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "larisa", "way_type": "road"})
    assert gs.locales["melitene"].siege_markers == 0
    assert not d.besieged, "inside defender left Besieged after besiegers departed"


def test_besieged_lord_menu_only_sally_pass_end_421():
    """Negative-enumerator guard (cross-harness over-enumeration class): a
    Besieged active Lord may only Sally / Pass / Forage (4.2.1) -- the command
    menu must NOT offer March/Tax/Supply/Ravage to him (cf. a sibling harness
    that offered cmd_march to a besieged Lord). command_menu gates every
    non-Sally option behind `not lord.besieged`."""
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["alp_arslan"]
    lord.cylinder = "melitene"; lord.besieged = True; lord.forces = {"turkic_horse": 3}
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "alp_arslan"
    gs.meta.actions_remaining = 4
    types = {m["type"] for m in engine.legal_moves(gs)}
    assert "cmd_march" not in types and "cmd_tax" not in types and "cmd_supply" not in types
    assert "cmd_forage" not in types and "cmd_ravage" not in types
    assert "cmd_sally" in types  # the one combat action a Besieged Lord may take


def test_siege_marks_only_besieging_lord_451():
    """4.5.1: a Siege marks the besieging (Encamping) Lord Moved/Fought, "but not
    any other Lords there" -- so a Besieged defender inside is NOT forced to Feed."""
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]; aa.cylinder = "larisa"; aa.assets.provender = 2
    d = gs.lords["chatatourios"]; d.cylinder = "melitene"; d.besieged = True
    d.forces = {"infantry": 2}; d.assets.provender = 1; d.assets.loot = 0
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "melitene", "way_type": "road"})
    r = engine.apply_action(gs, {"type": "besiege_bypass", "choice": "besiege"})
    if r.get("pending") == "assign_themata_defenders":
        engine.apply_action(gs, {"type": "assign_themata_defenders", "markers": []})
    d.assets.provender = 1  # reset after any setup Feed
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_siege", "lord": "alp_arslan"})
    # The besieged defender was not marked Moved/Fought -> not Fed -> keeps his Provender.
    assert d.assets.provender == 1, "besieged defender wrongly Fed by the besieger's Siege"


def test_ravage_marks_lords_moved_fought_455():
    """4.5.5: Ravage marks all Lords of both sides at the Locale Moved/Fought
    (so the ravaging Lord must Feed) -- it was previously left unmarked."""
    from seljuk import actions
    gs = S.load_scenario("emperor_and_the_lion")
    sav = gs.lords["sav_tekin"]; sav.mustered = True
    loc = next(lid for lid in gs.locales
               if actions.current_allegiance(gs, lid) == "roman"
               and not gs.locales[lid].ravaged_side and gs.locales[lid].siege_markers == 0)
    sav.cylinder = loc
    for l in gs.lords.values():
        l.moved_fought = False
    _activate(gs, "sav_tekin", actions=4)  # 2-action Ravage leaves actions -> no end-of-card clear
    engine.apply_action(gs, {"type": "cmd_ravage", "lord": "sav_tekin", "actions": 2})
    assert sav.moved_fought is True, "ravaging Lord left unmarked (would skip Feed)"
