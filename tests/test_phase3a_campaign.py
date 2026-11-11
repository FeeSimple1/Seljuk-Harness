"""Phase 3a: Campaign machine, Plan (4.1), Feed-Pay-Disband (4.6)."""
import pytest

from seljuk import scenarios as S, engine, campaign, static_data as sd
from seljuk.rng import DiceRoller
from seljuk.state import GameState, IllegalAction


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
    # Seljuk's first card is No Command -> Feed/Pay/Disband (4.6), then auto-passes
    # to Roman's Manuel. Drive through the (empty) FPD Pay step.
    while gs.meta.subphase == "campaign.fpd_pay":
        engine.apply_action(gs, {"type": "fpd_done"})
    assert gs.meta.active_lord == "manuel_komnenos"


@pytest.mark.parametrize("valid_pair_first", [False, True])
def test_plan_rejects_self_pair_before_any_plan_or_link_changes(valid_pair_first):
    gs = S.load_scenario("showdown_in_anatolia", seed=7)
    upper, lower = "chatatourios", "roussel_de_bailleul"
    gs.lords[lower].cylinder = gs.lords[upper].cylinder
    campaign.start_campaign(gs)
    engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                             "cards": ["no_command"] * 5 + ["alp_arslan"] * 2})
    cards = [upper] * 2 + ["no_command"] * 5
    valid_pair = {"lieutenant": upper, "lower_lord": lower}
    lieutenants = ([valid_pair] if valid_pair_first else []) + [
        {"lieutenant": upper, "lower_lord": upper},
    ]
    before = gs.to_json()

    with pytest.raises(IllegalAction) as exc:
        engine.apply_action(gs, {"type": "build_plan", "side": "roman",
                                 "cards": cards, "lieutenants": lieutenants})
    assert exc.value.code == "self_stack"
    assert gs.to_json() == before

    # Also check before the dispatcher's rollback can hide a partial assignment.
    with pytest.raises(IllegalAction) as exc:
        campaign.build_plan(gs, "roman", cards, lieutenants)
    assert exc.value.code == "self_stack"
    assert gs.to_json() == before

    engine.apply_action(gs, {"type": "build_plan", "side": "roman",
                             "cards": cards, "lieutenants": [valid_pair]})
    loaded = GameState.from_json(gs.to_json())
    for state in (gs, loaded):
        assert state.lords[upper].lower_lord == lower
        assert state.lords[lower].lieutenant_of == upper
        assert state.meta.subphase == "campaign.fpd_pay"
        for _ in range(2):
            engine.apply_action(state, {"type": "fpd_done"})
        assert state.meta.active_lord == upper and state.roman.plan_pointer == 1
    assert gs.to_json() == loaded.to_json()
    assert GameState.from_json(gs.to_json()).to_json() == gs.to_json()


@pytest.mark.parametrize("upper,lower", [
    ("chatatourios", "roussel_de_bailleul"),
    ("roussel_de_bailleul", "chatatourios"),
])
def test_lieutenant_designation_and_lower_lord_card_passes_413(upper, lower):
    gs = S.load_scenario("showdown_in_anatolia", seed=1)
    # Put two non-Commander Roman lords at the same Locale to stack them.
    a, b = gs.lords["chatatourios"], gs.lords["roussel_de_bailleul"]
    b.cylinder = a.cylinder  # co-locate at Antioch
    campaign.start_campaign(gs)
    # Seljuk plan
    engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                             "cards": ["alp_arslan", "arisighi", "no_command", "no_command", "no_command", "no_command", "no_command"]})
    # Roman Plan with a Lower Lord card followed by his Lieutenant's card.
    engine.apply_action(gs, {"type": "build_plan", "side": "roman",
                             "cards": [lower, upper] + ["no_command"] * 5,
                             "lieutenants": [{"lieutenant": upper, "lower_lord": lower}]})
    assert gs.lords[upper].lower_lord == lower
    assert gs.lords[lower].lieutenant_of == upper
    # A Lower Lord's revealed card is a Pass (4.1.3).
    activated = []
    guard = 0
    while gs.meta.subphase in ("campaign.command", "campaign.fpd_pay") and guard < 90:
        guard += 1
        if gs.meta.subphase == "campaign.fpd_pay":
            engine.apply_action(gs, {"type": "fpd_done"})  # 4.6.2 Pay step (decline)
            continue
        if gs.meta.active_lord is not None:
            activated.append(gs.meta.active_lord)
        engine.apply_action(gs, {"type": "end_activation"})
    assert lower not in activated
    assert upper in activated


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
