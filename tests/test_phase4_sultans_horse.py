"""Phase 4: R4 Sultan's Horse Is Killed -- played during a Storm by Alp Arslan
(>1 Siege marker) reduces the number of Storm Rounds by 1."""
from seljuk import scenarios as S, battle
from seljuk.state import GameState
from seljuk.rng import DiceRoller


def _storm_state():
    gs = S.load_scenario("emperor_and_the_lion")
    loc = "melitene"
    gs.locales[loc].siege_markers = 4
    aa = gs.lords["alp_arslan"]
    aa.mustered = True; aa.cylinder = loc; aa.forces = {"ghulam_cavalry": 1}  # weak -> storm runs long
    return gs, loc


def _rounds(reduction):
    gs, loc = _storm_state()
    ctx = battle.DecisionContext()
    r = battle.resolve_storm(gs, ["alp_arslan"], loc, ctx, DiceRoller(7), rounds_reduction=reduction)
    return r["rounds"]


def test_r4_reduces_storm_rounds_by_one():
    full = _rounds(0)
    reduced = _rounds(1)
    assert full >= 2                      # the base storm runs multiple Rounds
    assert reduced <= full - 1            # R4 cut it by (at least) one Round
    assert reduced <= 4 - 1               # capped at siege-1


def test_r4_only_with_alp_arslan_and_held(tmp_path=None):
    from seljuk import campaign, engine
    gs, loc = _storm_state()
    gs.roman.held_events = ["R4"]
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "alp_arslan"
    gs.meta.active_card = "alp_arslan"; gs.meta.actions_remaining = 1
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    # mark Alp Arslan as besieging
    gs.lords["alp_arslan"].besieged = False
    r = engine.apply_action(gs, {"type": "cmd_storm", "lord": "alp_arslan", "play_sultans_horse": True})
    assert "R4" not in gs.roman.held_events   # R4 was played (discarded back to deck)
