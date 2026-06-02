"""Fixes from the rulebook-accuracy audit:
- The 6-Hit Melee cap is Storm-only (4.9.1); a Sally (4.9.2) is uncapped.
- "This Campaign" Events establish their effect when drawn (3.1.3), e.g. S9.
"""
from seljuk import scenarios as S, battle, actions as A
from seljuk.rng import DiceRoller


def test_sally_melee_uncapped_but_storm_capped():
    gs = S.load_scenario("emperor_and_the_lion")
    side = battle._Side(gs, [], "attacker")
    lid = "alp_arslan"
    gs.lords[lid].mustered = True
    gs.lords[lid].forces = {"ghulam_cavalry": 8}   # 8 x melee 1 = 8
    side.front["center"] = lid
    assert battle._lord_melee_capped(gs, side, 1, storm=False) == 8.0   # Sally: uncapped
    assert battle._lord_melee_capped(gs, side, 1, storm=True) == 6.0    # Storm: capped at 6


def test_this_campaign_event_resolves_on_draw():
    gs = S.load_scenario("emperor_and_the_lion")
    assert gs.meta.notes.get("moustache_campaign") is None
    A._classify_drawn_event(gs, "seljuk", "S9", DiceRoller(1))   # S9 Moustache (this_campaign)
    # Effect established AND card filed for end-of-Campaign discard.
    assert gs.meta.notes.get("moustache_campaign") is True
    assert "S9" in gs.seljuk.this_campaign_events


def test_this_campaign_peace_offering_enters_play_on_draw():
    gs = S.load_scenario("emperor_and_the_lion")
    A._classify_drawn_event(gs, "seljuk", "S13", DiceRoller(1))   # S13 Gifts Exchanged
    assert gs.meta.notes.get("peace_offering_season") is True
    assert "S13" in gs.seljuk.capabilities_in_play
