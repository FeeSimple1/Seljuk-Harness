"""Phase 3a: Campaign machine, Plan (4.1), Feed-Pay-Disband (4.6)."""
import pytest

from seljuk import scenarios as S, engine, campaign, static_data as sd
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def test_plan_size_by_season_and_first_turn_override():
    gs = S.load_scenario("year_of_treacherous_ambition")  # first_turn_plan_size 6
    campaign.start_campaign(gs)
    assert campaign.plan_size(gs) == 6
    gs.meta.notes["first_plan_done"] = True
    gs.meta.calendar_box = 8  # Summer
    assert campaign.plan_size(gs) == 8
    gs.meta.calendar_box = 7  # Spring
    assert campaign.plan_size(gs) == 7


def test_capability_discard_trims_excess_side_wide_40():
    gs = S.load_scenario("manzikert")
    # Seljuk has only Marwanid in play but 4 Mustered Lords -> no discard.
    gs.seljuk.capabilities_in_play = ["S8", "S9", "S23"]  # 3 side-wide
    # leave 1 mustered seljuk lord
    for lid, l in list(gs.lords.items()):
        if l.side == "seljuk" and l.mustered and lid != "alp_arslan":
            l.mustered = False
    campaign._capability_discard(gs)
    assert len(gs.seljuk.capabilities_in_play) == 1  # trimmed to # Mustered Lords (1)


def test_build_plan_size_validation_41():
    gs = S.load_scenario("year_of_treacherous_ambition")
    campaign.start_campaign(gs)
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "build_plan", "side": "seljuk", "cards": ["alp_arslan"]})  # wrong size


def test_build_plan_rejects_too_many_cards_for_one_lord_192():
    gs = S.load_scenario("year_of_treacherous_ambition")
    campaign.start_campaign(gs)
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                                 "cards": ["alp_arslan"] * 5 + ["no_command"]})  # 5 > 4 cap


def test_both_plans_begin_command_seljuk_first_42():
    gs = S.load_scenario("year_of_treacherous_ambition", seed=2)
    campaign.start_campaign(gs)
    engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                             "cards": ["alp_arslan", "arisighi", "emir_of_arran", "alp_arslan", "no_command", "no_command"]})
    assert gs.meta.active_player == "roman"
    engine.apply_action(gs, {"type": "build_plan", "side": "roman",
                             "cards": ["manuel_komnenos", "chatatourios", "roussel_de_bailleul", "manuel_komnenos", "no_command", "no_command"]})
    assert gs.meta.subphase == "campaign.command"
    assert gs.meta.active_card == "alp_arslan"  # Seljuk reveals first
    assert gs.meta.actions_remaining == sd.lord("alp_arslan")["ratings"]["command"]


def test_no_command_card_auto_passes_423():
    gs = S.load_scenario("year_of_treacherous_ambition", seed=2)
    campaign.start_campaign(gs)
    engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                             "cards": ["no_command", "no_command", "no_command", "no_command", "no_command", "alp_arslan"]})
    engine.apply_action(gs, {"type": "build_plan", "side": "roman",
                             "cards": ["manuel_komnenos", "no_command", "no_command", "no_command", "no_command", "no_command"]})
    # Seljuk's first card is No Command -> auto-passes to Roman's Manuel.
    assert gs.meta.active_lord == "manuel_komnenos"


def test_lieutenant_designation_and_lower_lord_card_passes_413():
    gs = S.load_scenario("showdown_in_anatolia", seed=1)
    # Put two non-Commander Roman lords at the same Locale to stack them.
    a, b = gs.lords["chatatourios"], gs.lords["roussel_de_bailleul"]
    b.cylinder = a.cylinder  # co-locate at Antioch
    campaign.start_campaign(gs)
    # Seljuk plan
    engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                             "cards": ["alp_arslan", "arisighi", "no_command", "no_command", "no_command", "no_command", "no_command"]})
    # Roman plan with a Lieutenant stack (Chatatourios over Roussel)
    engine.apply_action(gs, {"type": "build_plan", "side": "roman",
                             "cards": ["roussel_de_bailleul", "chatatourios", "no_command", "no_command", "no_command", "no_command", "no_command"],
                             "lieutenants": [{"lieutenant": "chatatourios", "lower_lord": "roussel_de_bailleul"}]})
    assert gs.lords["chatatourios"].lower_lord == "roussel_de_bailleul"
    assert gs.lords["roussel_de_bailleul"].lieutenant_of == "chatatourios"
    # Drive the whole Campaign; a Lower Lord's revealed card is a Pass (4.1.3),
    # so Roussel never activates, while his Lieutenant Chatatourios does.
    activated = []
    guard = 0
    while gs.meta.subphase == "campaign.command" and guard < 50:
        guard += 1
        if gs.meta.active_lord is not None:
            activated.append(gs.meta.active_lord)
        engine.apply_action(gs, {"type": "end_activation"})
    assert "roussel_de_bailleul" not in activated
    assert "chatatourios" in activated


def test_feed_requirement_thresholds_461():
    assert campaign._feed_requirement(8) == 1
    assert campaign._feed_requirement(9) == 2
    assert campaign._feed_requirement(13) == 3
    assert campaign._feed_requirement(17) == 4


def test_feed_unfed_shifts_service_left_461():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.moved_fought = True
    aa.forces = {"turkic_horse": 9}     # needs 2 Provender
    aa.assets.provender = 1             # only 1 available -> Unfed
    aa.assets.loot = 0
    aa.assets.coin = 0
    sb = aa.service_box
    res = campaign.feed_pay_disband(gs, DiceRoller(1))
    assert any(f["lord"] == "alp_arslan" and f["unfed"] for f in res["feed"])
    assert aa.service_box == sb - 1  # shifted left for being Unfed
    assert aa.moved_fought is False   # markers removed (4.6.3)


def test_feed_sharing_covers_shortfall_461():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    arisighi = gs.lords["arisighi"]
    arisighi.cylinder = aa.cylinder  # co-locate at Ani
    aa.moved_fought = True
    aa.forces = {"turkic_horse": 9}  # needs 2
    aa.assets.provender = 1
    aa.assets.loot = 0
    arisighi.assets.provender = 2    # co-located Lord Shares
    res = campaign.feed_pay_disband(gs, DiceRoller(1))
    assert any(f["lord"] == "alp_arslan" and not f["unfed"] for f in res["feed"])
