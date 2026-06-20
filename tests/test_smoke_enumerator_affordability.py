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


def test_over_laden_march_offered_via_discard():
    """4.3.2/1.7.2: an over-laden group (more than two Provender per Cart) may not
    move UNLESS it discards the excess Provender first. The menu must offer such
    Marches (flagged discard_excess) rather than suppressing March entirely, and
    each must round-trip through the handler. Marching without opting into the
    discard is still refused."""
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "ani"
    aa.assets.carts = 0; aa.assets.provender = 3  # prov > 2*carts -> over-laden
    _active_campaign(gs, "alp_arslan", actions=4)
    marches = [m for m in C.command_menu(gs) if m["type"] == "cmd_march"]
    assert marches, "over-laden Lord must still be offered discard-to-March"
    assert all(m.get("discard_excess") for m in marches)
    assert _all_enumerated_moves_apply(gs) == []  # every offered March applies cleanly
    # Applying a discard-March sheds exactly the excess Provender (carts=0 -> all of it).
    snap = GameState.from_json(gs.to_json())
    engine.apply_action(snap, {k: v for k, v in marches[0].items() if not k.startswith("_")})
    assert snap.lords["alp_arslan"].assets.provender == 0
    # Omitting the opt-in is refused, and Assets are untouched.
    snap2 = GameState.from_json(gs.to_json())
    try:
        engine.apply_action(snap2, {"type": "cmd_march", "lord": "alp_arslan",
                                    "to": marches[0]["to"], "way_type": marches[0]["way_type"]})
        assert False, "over-laden March must be refused without discard_excess"
    except IllegalAction:
        pass
    assert snap2.lords["alp_arslan"].assets.provender == 3


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


def test_s3_steppe_raid_one_action_offered_and_round_trips():
    """S3 clarification: adjacent Steppe-Raid Ravages "may be defended per the
    normal rules, depending on how many Command actions were spent" — so, like a
    normal Seljuk Ravage (4.5.5), a 1-action adjacent raid is legal (the Roman may
    defend with a Themata). The handler accepts it, so the enumerator must offer
    it; offering only the 2-action variant under-enumerated the legal 1-action
    raid (enumerator/handler divergence)."""
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    lid, adj = "sav_tekin", "artah"   # manbij (Seljuk) is adjacent to artah (Roman)
    lord = gs.lords[lid]
    lord.cylinder = "manbij"; lord.forces = {"turkic_horse": 2}; lord.capabilities = ["S3"]
    _active_campaign(gs, lid, actions=1)
    raids = [m for m in C.command_menu(gs)
             if m["type"] == "cmd_ravage" and m.get("target") == adj]
    # With 1 action: the 1-action raid IS offered, the 2-action raid is NOT.
    assert any(m.get("actions") == 1 for m in raids)
    assert all(m.get("actions") != 2 for m in raids)
    assert _all_enumerated_moves_apply(gs) == []


def test_s3_steppe_raid_offered_with_two_actions():
    """Guard against over-correction: with 2 actions the Steppe Raid is offered
    and round-trips through the handler cleanly."""
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    lid, adj = "sav_tekin", "artah"
    lord = gs.lords[lid]
    lord.cylinder = "manbij"; lord.forces = {"turkic_horse": 2}; lord.capabilities = ["S3"]
    _active_campaign(gs, lid, actions=2)
    raids = [m for m in C.command_menu(gs)
             if m["type"] == "cmd_ravage" and m.get("target") == adj]
    # With 2 actions both the auto (2-action) and defendable (1-action) raids appear.
    assert any(m.get("actions") == 2 for m in raids)
    assert any(m.get("actions") == 1 for m in raids)
    assert _all_enumerated_moves_apply(gs) == []
