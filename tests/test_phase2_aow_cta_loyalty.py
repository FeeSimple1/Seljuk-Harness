"""Phase 2 Levy: Arts of War draw (3.1), Call to Arms (3.5), Loyalty Checks (1.4).

Per-card EFFECTS are Phase 4; these test the draw/classification mechanic, the
self-contained Call to Arms options, and the Loyalty-Check resolution.
"""
import pytest

from seljuk import scenarios as S, engine, static_data as sd
from seljuk.actions import resolve_loyalty_check, _switch_side
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _seed_for_first_d6(value):
    for seed in range(200):
        if DiceRoller(seed).d6() == value:
            return seed
    raise AssertionError(f"no seed produced first d6 == {value}")


def test_later_levy_draws_two_events_per_side_and_classifies_313():
    gs = S.load_scenario("emperor_and_the_lion", seed=7)
    gs.meta.notes["first_aow_done"] = True  # force "later Levy" -> Events
    before = len(gs.seljuk.draw_deck)
    engine.start_levy(gs)
    assert len(gs.seljuk.draw_deck) == before - 2
    # every drawn event is filed somewhere (held / this_campaign / pending)
    filed = (len(gs.seljuk.held_events) + len(gs.seljuk.this_campaign_events)
             + sum(1 for p in gs.meta.pending if p["type"] == "event_pending_resolution" and p["side"] == "seljuk"))
    assert filed == 2


def test_first_levy_sidewide_capability_to_board_edge_312():
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    engine.start_levy(gs)  # first Levy -> Capabilities
    # any side-wide cards drawn went to board edge; any this-lord queued/returned
    for side in ("seljuk", "roman"):
        for cid in gs.side_decks(side).capabilities_in_play:
            assert sd.card(cid)["capability"]["scope"] == "side_wide"


def test_first_levy_this_lord_deploy_decision_312():
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    engine.start_levy(gs)
    deploys = [p for p in gs.meta.pending if p["type"] == "deploy_capability"]
    if deploys:
        p0 = deploys[0]
        lord = p0["eligible"][0]
        engine.apply_action(gs, {"type": "deploy_capability", "card": p0["card"], "lord": lord})
        assert p0["card"] in gs.lords[lord].capabilities
        assert p0 not in gs.meta.pending


def test_full_levy_reaches_complete():
    gs = S.load_scenario("emperor_and_the_lion", seed=11)
    gs.meta.notes["first_aow_done"] = True
    engine.start_levy(gs)
    # clear any pending deploys not relevant here; just pass through all steps
    for _ in range(2):  # pay: seljuk, roman
        engine.apply_action(gs, {"type": "pass_step"})
    for _ in range(2):  # muster: seljuk, roman
        engine.apply_action(gs, {"type": "pass_step"})
    for _ in range(2):  # call to arms: seljuk, roman
        engine.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.subphase == "levy.complete"


def _drive_to_cta(scenario, seed=1):
    gs = S.load_scenario(scenario, seed=seed)
    gs.meta.notes["first_aow_done"] = True
    engine.start_levy(gs)
    for _ in range(4):  # pay x2, muster x2
        engine.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.subphase == "levy.call_to_arms"
    return gs


def test_cta_loot_shifts_ready_seljuk_cylinder_352():
    gs = _drive_to_cta("emperor_and_the_lion")
    gs.holding_boxes.mosul_baghdad_loot = 1
    gs.meta.vp = S.score(gs)
    # robert_crepin is Ready (calendar box 1) on the Roman side in this scenario;
    # use a Ready Seljuk lord instead: afsin_beg is at calendar box 2.
    ready_seljuk = [lid for lid, l in gs.lords.items() if l.side == "seljuk" and l.cylinder == "calendar"]
    assert ready_seljuk
    lid = ready_seljuk[0]
    before = gs.lords[lid].cylinder_calendar_box
    r = engine.apply_action(gs, {"type": "cta_loot", "lord": lid, "direction": "left"})
    assert gs.lords[lid].cylinder_calendar_box == before - 1
    assert gs.holding_boxes.mosul_baghdad_loot == 0
    # one option ends the Seljuk Call to Arms -> Roman's turn
    assert gs.meta.active_player == "roman"


def test_cta_strategic_objective_take_requires_commander_in_constantinople_353():
    gs = _drive_to_cta("emperor_and_the_lion")
    engine.apply_action(gs, {"type": "pass_step"})  # Seljuk declines
    assert gs.meta.active_player == "roman"
    # Romanos is at Constantinople in this scenario -> take allowed
    r = engine.apply_action(gs, {"type": "cta_strategic_objective", "mode": "take"})
    assert gs.holding_boxes.constantinople_strategic_objectives_available == 1
    assert gs.meta.subphase == "levy.complete"  # single option ends Roman CtA -> Levy done


def test_cta_strategic_objective_place_on_enemy_sultanate_stronghold_353():
    gs = _drive_to_cta("emperor_and_the_lion")
    engine.apply_action(gs, {"type": "pass_step"})  # Seljuk declines
    gs.holding_boxes.constantinople_strategic_objectives_available = 1
    r = engine.apply_action(gs, {"type": "cta_strategic_objective", "mode": "place", "target": "ani"})
    assert gs.locales["ani"].strategic_objective
    assert gs.holding_boxes.constantinople_strategic_objectives_available == 0


def test_cta_strategic_objective_place_rejects_roman_locale():
    gs = _drive_to_cta("emperor_and_the_lion")
    engine.apply_action(gs, {"type": "pass_step"})
    gs.holding_boxes.constantinople_strategic_objectives_available = 1
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cta_strategic_objective", "mode": "place", "target": "antioch"})


def test_loyalty_natural_1_always_fails_and_6_always_succeeds_141():
    gs = S.load_scenario("emperor_and_the_lion")
    r1 = resolve_loyalty_check(gs, "arisighi", "roman", DiceRoller(_seed_for_first_d6(1)))
    assert r1["natural"] == 1 and r1["switched"] is False
    gs2 = S.load_scenario("emperor_and_the_lion")
    r6 = resolve_loyalty_check(gs2, "arisighi", "roman", DiceRoller(_seed_for_first_d6(6)))
    assert r6["natural"] == 6 and r6["switched"] is True
    assert gs2.lords["arisighi"].side == "roman"  # was seljuk -> switched


def test_loyalty_coin_modifiers_affect_modified_result_141():
    gs = S.load_scenario("emperor_and_the_lion")
    # natural 3 vs Fealty 4: base fails; +2 coins_for -> modified 5 > 4 -> switches
    seed3 = _seed_for_first_d6(3)
    r = resolve_loyalty_check(gs, "arisighi", "roman", DiceRoller(seed3), coins_for=2)
    assert r["natural"] == 3 and r["modified"] == 5 and r["switched"] is True


def test_switch_side_flips_allegiance_and_removes_from_map_142():
    gs = S.load_scenario("emperor_and_the_lion")
    arisighi = gs.lords["arisighi"]
    assert arisighi.side == "seljuk" and arisighi.mustered
    _switch_side(gs, arisighi)
    assert arisighi.side == "roman"
    assert not arisighi.mustered
