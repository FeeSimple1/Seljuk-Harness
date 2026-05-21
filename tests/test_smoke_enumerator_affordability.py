"""Regression tests for the enumerator/handler divergences the randomized smoke
fuzzer found: the Command menu must not offer a March or Seljuk Ravage the
active Lord cannot actually afford (cost > actions_remaining) or that is
over-laden. Each enumerated move must round-trip through its handler cleanly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, campaign as C, engine
from seljuk.state import GameState, IllegalAction
from seljuk.rng import DiceRoller


def _active_campaign(gs, lord_id, actions, side="seljuk"):
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = side; gs.meta.active_lord = lord_id
    gs.meta.active_card = lord_id; gs.meta.actions_remaining = actions
    gs.seljuk.command_plan = [lord_id]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = []; gs.roman.plan_pointer = 0
    gs.lords[lord_id].mustered = True


def _all_enumerated_moves_apply(gs):
    """Every concrete enumerated command applies without IllegalAction (round-trip)."""
    bad = []
    for mv in C.command_menu(gs):
        snap = GameState.from_json(gs.to_json())
        try:
            engine.apply_action(snap, {k: v for k, v in mv.items() if not k.startswith("_")})
        except IllegalAction as e:
            bad.append(f"{mv['type']} -> {e}")
    return bad


def test_no_unaffordable_march_with_one_action():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "ani"
    aa.assets.loot = 1   # Laden -> Road March costs 2, Pass costs 3
    _active_campaign(gs, "alp_arslan", actions=1)
    moves = C.command_menu(gs)
    # No March should be offered (every Way costs >= 2 while Laden, only 1 action).
    assert not any(m["type"] == "cmd_march" for m in moves)
    assert _all_enumerated_moves_apply(gs) == []


def test_over_laden_suppresses_march():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "ani"
    aa.assets.carts = 0; aa.assets.provender = 3  # prov > 2*carts -> over-laden, cannot move
    _active_campaign(gs, "alp_arslan", actions=4)
    moves = C.command_menu(gs)
    assert not any(m["type"] == "cmd_march" for m in moves)
    assert _all_enumerated_moves_apply(gs) == []


def test_seljuk_two_action_ravage_not_offered_with_one_action():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]
    # Park on an enemy (Roman) un-ravaged locale so Ravage is offered.
    from seljuk import static_data as sd
    target = next(l for l in sd.all_locale_ids()
                  if sd.locale(l)["allegiance"] == "roman" and not gs.locales[l].ruins
                  and not sd.locale(l).get("is_holding_box"))
    aa.cylinder = target
    _active_campaign(gs, "alp_arslan", actions=1)
    ravages = [m for m in C.command_menu(gs) if m["type"] == "cmd_ravage"]
    # With only 1 action, the 2-action Ravage must NOT be offered.
    assert all(m.get("actions") != 2 for m in ravages)
    assert _all_enumerated_moves_apply(gs) == []


def test_affordable_road_march_still_offered():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "ani"
    aa.assets.loot = 0; aa.assets.provender = 0  # Unladen -> Road March costs 1
    _active_campaign(gs, "alp_arslan", actions=1)
    moves = C.command_menu(gs)
    assert any(m["type"] == "cmd_march" and m["way_type"] == "road" for m in moves)
    assert _all_enumerated_moves_apply(gs) == []
