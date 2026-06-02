"""Full-audit fixes: immediate victory by permanent disband, Manzikert end
conditions, Avoid-across-approach-Way, and Withdraw Stronghold-Size capacity."""
import pytest
from seljuk import scenarios as S, campaign
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def test_alp_arslan_permanent_disband_roman_immediate_victory():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.lords["alp_arslan"].cylinder = "removed"   # permanently Disbanded
    assert campaign._campaign_5_2_over(gs) is True
    assert gs.meta.notes["winner"] == "roman"


def test_setup_removed_lord_does_not_trigger_victory():
    gs = S.load_scenario("manzikert")   # Manuel/Ibn Khan are setup-removed here
    # A setup-removed Lord carries the flag and must NOT trigger 5.2 disband victory.
    assert not campaign._permanently_disbanded(gs, "manuel_komnenos")


def test_manzikert_romanos_disband_seljuk_victory():
    gs = S.load_scenario("manzikert")
    gs.lords["romanos_diogenes"].cylinder = "removed"
    assert campaign._campaign_5_2_over(gs) is True
    assert gs.meta.notes["winner"] == "seljuk"


def test_manzikert_aleppo_end_victory():
    gs = S.load_scenario("manzikert")
    gs.locales["aleppo"].conquered_side = "seljuk"
    assert S.end_of_scenario_winner(gs) == "seljuk"


def test_manzikert_control_end_victory():
    gs = S.load_scenario("manzikert")
    gs.locales["manzikert"].conquered_side = "roman"
    gs.locales["khliat"].conquered_side = "roman"
    assert gs.locales["aleppo"].conquered_side != "seljuk"
    assert S.end_of_scenario_winner(gs) == "roman"


def test_avoid_across_approach_way_rejected():
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["chatatourios"]; lord.mustered = True; lord.cylinder = "artah"
    # Cannot Avoid back to the Locale the attacker Approached from (manbij<->artah).
    with pytest.raises(IllegalAction):
        campaign._validate_avoid(gs, lord, "artah", "manbij", "roman", approach_origin="manbij")


def test_withdraw_capacity_enforced():
    gs = S.load_scenario("emperor_and_the_lion")
    loc = "melitene"   # Town, Size 2
    defs = ["chatatourios", "robert_crepin", "roussel_de_bailleul"]
    for d in defs:
        gs.lords[d].mustered = True; gs.lords[d].cylinder = loc; gs.lords[d].side = "roman"
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = loc
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.pending = [{"type": "approach_response", "locale": loc, "attackers": ["alp_arslan"],
                        "defenders": defs, "_owed_by": "roman", "from": "manbij"}]
    with pytest.raises(IllegalAction):   # 3 Lords into a Size-2 Town
        campaign.h_respond_approach(gs, {"choices": {d: {"action": "withdraw"} for d in defs}}, DiceRoller(1))
    assert campaign._stronghold_size(gs, loc) == 2


def test_treachery_reentry_conquers_enemy_seat():
    from seljuk import actions
    gs = S.load_scenario("emperor_and_the_lion")
    af = gs.lords["afsin_beg"]
    af.side = "roman"                 # switched to Roman via a failed Loyalty Check
    af.mustered = False; af.cylinder = "offboard"
    af.flags["treachery_reentry_box"] = 1
    gs.meta.calendar_box = 3
    for lid, l in gs.lords.items():   # free up Ani (his Seat)
        if l.side == "seljuk" and lid != "afsin_beg":
            l.mustered = False; l.cylinder = "calendar"
    placed = actions.resolve_treachery_reentry(gs)
    seat = next((p["seat"] for p in placed if p["lord"] == "afsin_beg"), None)
    assert seat == "ani"                                  # his (Seljuk-printed) Seat
    assert gs.locales["ani"].conquered_side == "roman"    # 1.4.2: new side's Conquered markers
    assert gs.locales["ani"].conquered_count >= 1
