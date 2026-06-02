"""Phase 4: R17/S17 Unpredictable Weather (This Campaign)."""
import pytest
from seljuk import scenarios as S, campaign, engine, events, actions
from seljuk import map as gmap
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _spring(gs): gs.meta.calendar_box = 1   # Spring
def _summer(gs): gs.meta.calendar_box = 2   # Summer


def test_weather_spring_blocks_passes_for_march_and_supply():
    gs = S.load_scenario("emperor_and_the_lion"); _spring(gs)
    # Resolve R17 in Spring -> passes blocked.
    actions._classify_drawn_event(gs, "roman", "R17", DiceRoller(1))
    assert gs.meta.notes.get("weather_pass_block") is True
    # A Pass March is rejected.
    aa = gs.lords["alp_arslan"]; aa.mustered = True
    # find a pass way from somewhere
    pass_pair = None
    for a in gmap.sd.all_locale_ids():
        for e in gmap.ways_from(a):
            if e["type"] == "pass":
                pass_pair = (a, e["to"]); break
        if pass_pair: break
    a, b = pass_pair
    aa.cylinder = a; aa.assets.provender = 0; aa.assets.loot = 0
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "alp_arslan"
    gs.meta.active_card = "alp_arslan"; gs.meta.actions_remaining = 4
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    with pytest.raises(IllegalAction):
        campaign.h_cmd_march(gs, {"lord": "alp_arslan", "to": b, "way_type": "pass"}, DiceRoller(1))


def test_weather_summer_plan_nine_and_enemy_no_command():
    gs = S.load_scenario("emperor_and_the_lion"); _summer(gs)
    base = campaign.plan_size(gs)
    actions._classify_drawn_event(gs, "roman", "R17", DiceRoller(1))   # Roman plays -> Seljuk No Command
    assert gs.meta.notes.get("weather_plan9") is True
    assert gs.meta.notes.get("weather_no_command_side") == "seljuk"
    assert campaign.plan_size(gs) == 9 and base == 8
    # Seljuk plan must include >=1 No Command.
    campaign.start_campaign(gs)
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                                 "cards": ["alp_arslan"] * 4 + ["afsin_beg"] * 4 + ["arisighi"]})
