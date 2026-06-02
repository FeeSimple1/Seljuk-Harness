"""Campaign Feed/Pay/Disband Pay (4.6.2): after each Command card, any Seljuk
then Roman Lords may Pay (as per Levy 3.2) BEFORE Disband, so a Lord can be
paid to advance his Service and avoid Disband."""
from seljuk import scenarios as S, campaign, engine


def _setup_card():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    campaign.start_campaign(gs)
    sp = campaign.plan_size(gs)
    engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                             "cards": ["alp_arslan", "alp_arslan"] + ["no_command"] * (sp - 2)})
    engine.apply_action(gs, {"type": "build_plan", "side": "roman",
                             "cards": ["romanos_diogenes", "romanos_diogenes"] + ["no_command"] * (sp - 2)})
    assert gs.meta.active_lord == "alp_arslan"
    return gs


def test_campaign_pay_saves_lord_from_disband():
    gs = _setup_card()
    box = gs.meta.calendar_box
    afsin = gs.lords["afsin_beg"]
    afsin.mustered = True
    afsin.cylinder = gs.lords["alp_arslan"].cylinder   # co-located, Unbesieged
    afsin.besieged = False
    afsin.service_box = box - 1                          # Beyond Service -> would be removed
    gs.lords["alp_arslan"].assets.coin = 2
    # End the card -> Feed/Pay/Disband; Pay step opens for Seljuk.
    engine.apply_action(gs, {"type": "end_activation"})
    assert gs.meta.subphase == "campaign.fpd_pay" and gs.meta.active_player == "seljuk"
    # Pay 2 Coin to shift Afsin's Service right, above the calendar box.
    engine.apply_action(gs, {"type": "pay", "payer": "alp_arslan", "target": "afsin_beg",
                             "asset": "coin", "amount": 2})
    assert gs.lords["afsin_beg"].service_box == box + 1
    while gs.meta.subphase == "campaign.fpd_pay":
        engine.apply_action(gs, {"type": "fpd_done"})
    # Disband ran AFTER Pay: Afsin survived on the map.
    assert gs.lords["afsin_beg"].cylinder != "removed"
    assert gs.lords["afsin_beg"].mustered is True


def test_campaign_no_pay_lord_is_disbanded():
    gs = _setup_card()
    box = gs.meta.calendar_box
    afsin = gs.lords["afsin_beg"]
    afsin.mustered = True
    afsin.cylinder = gs.lords["alp_arslan"].cylinder
    afsin.besieged = False
    afsin.service_box = box - 1
    gs.lords["alp_arslan"].assets.coin = 0   # nobody can Pay
    engine.apply_action(gs, {"type": "end_activation"})
    # Decline Pay (or none available) -> Disband removes the Beyond-Service Lord.
    while gs.meta.subphase == "campaign.fpd_pay":
        engine.apply_action(gs, {"type": "fpd_done"})
    assert gs.lords["afsin_beg"].cylinder == "removed"


def test_campaign_pay_enumerated_and_finishable():
    gs = _setup_card()
    gs.lords["alp_arslan"].assets.coin = 1
    engine.apply_action(gs, {"type": "end_activation"})
    moves = engine.legal_moves(gs)
    types = {m["type"] for m in moves}
    assert "pay" in types and "fpd_done" in types
