"""Phase 2 Levy: step machine, Pay (3.2), Disband (3.3)."""
import pytest

from seljuk import scenarios as S, engine, static_data as sd
from seljuk.actions import resolve_disband
from seljuk.state import IllegalAction


def _levy_at_pay(scenario="emperor_and_the_lion", seed=1):
    gs = S.load_scenario(scenario, seed=seed)
    engine.start_levy(gs)
    return gs


def test_levy_starts_at_pay_after_auto_arts_of_war():
    gs = _levy_at_pay()
    assert gs.meta.subphase == "levy.pay"
    assert gs.meta.active_player == "seljuk"  # Seljuk first (2.2.4)


def test_pay_with_coin_shifts_service_right_321():
    """3.2.1: a Lord may remove Coin to shift a Service Marker right 1 box per Coin."""
    gs = _levy_at_pay()
    aa = gs.lords["alp_arslan"]
    before = aa.service_box
    engine.apply_action(gs, {"type": "pay", "payer": "alp_arslan", "target": "alp_arslan", "asset": "coin", "amount": 2})
    assert aa.assets.coin == 0
    assert aa.service_box == before + 2


def test_pay_rejects_more_than_available():
    gs = _levy_at_pay()
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "pay", "payer": "alp_arslan", "target": "alp_arslan", "asset": "coin", "amount": 9})


def test_pay_loot_requires_friendly_unbesieged_locale_322():
    """3.2.2: Loot Pays only at a Friendly Locale free of Siege."""
    gs = _levy_at_pay()
    aa = gs.lords["alp_arslan"]
    aa.assets.loot = 1
    # Ani is Seljuk-friendly and unbesieged -> allowed.
    engine.apply_action(gs, {"type": "pay", "payer": "alp_arslan", "target": "alp_arslan", "asset": "loot", "amount": 1})
    assert aa.assets.loot == 0
    # Under Siege -> not allowed.
    aa.assets.loot = 1
    gs.locales["ani"].siege_markers = 1
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "pay", "payer": "alp_arslan", "target": "alp_arslan", "asset": "loot", "amount": 1})


def test_commander_pays_coin_at_any_distance_321():
    """3.2.1 exception: an Unbesieged Commander may Pay Coin for any Unbesieged friendly Lord."""
    gs = _levy_at_pay()
    # Alp Arslan (Commander @ Ani) pays for Ibn Khan @ Hama (different Locale).
    ik_before = gs.lords["ibn_khan"].service_box
    engine.apply_action(gs, {"type": "pay", "payer": "alp_arslan", "target": "ibn_khan", "asset": "coin", "amount": 1})
    assert gs.lords["ibn_khan"].service_box == ik_before + 1


def test_non_commander_cannot_pay_distant_lord():
    gs = _levy_at_pay()
    # Ibn Khan @ Hama (not a Commander) cannot pay Alp Arslan @ Ani.
    gs.lords["ibn_khan"].assets.coin = 1
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "pay", "payer": "ibn_khan", "target": "alp_arslan", "asset": "coin", "amount": 1})


def test_pass_step_advances_seljuk_then_roman_then_step():
    gs = _levy_at_pay()
    engine.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.active_player == "roman" and gs.meta.subphase == "levy.pay"
    engine.apply_action(gs, {"type": "pass_step"})
    # Pay done -> Disband auto-resolves -> Muster.
    assert gs.meta.subphase == "levy.muster"


def test_disband_beyond_service_is_permanent_331():
    """3.3.1: a Lord whose Service Marker is left of the current box is removed permanently."""
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 7
    gs.lords["ibn_khan"].service_box = 3  # < 7
    resolve_disband(gs, "seljuk")
    assert gs.lords["ibn_khan"].cylinder == "removed"
    assert not gs.lords["ibn_khan"].mustered
    assert gs.lords["ibn_khan"].service_box is None


def test_disband_at_limit_is_recyclable_332():
    """3.3.2: a Lord at his Service limit Disbands to the Calendar (Service Rating boxes right)."""
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 5
    gs.lords["chatatourios"].service_box = 5  # == current box
    resolve_disband(gs, "roman")
    ch = gs.lords["chatatourios"]
    assert ch.cylinder == "calendar"
    assert ch.cylinder_calendar_box == 5 + sd.lord("chatatourios")["ratings"]["service"]
    assert ch.service_box is None


def test_disband_seljuk_with_strategic_objective_claimed_by_roman_331():
    """3.3.1: a removed Seljuk Lord carrying a Roman Strategic Objective gives it to Constantinople."""
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 8
    gs.lords["arisighi"].service_box = 2
    gs.lords["arisighi"].strategic_objective = True
    before = gs.holding_boxes.constantinople_roman_vp_markers
    resolve_disband(gs, "seljuk")
    assert gs.holding_boxes.constantinople_roman_vp_markers == before + 1
    assert not gs.lords["arisighi"].strategic_objective


def test_disband_returns_this_lord_capabilities_to_deck_331():
    gs = S.load_scenario("year_of_treacherous_ambition")  # Arisighi has S3 levied
    gs.meta.calendar_box = 9
    gs.lords["arisighi"].service_box = 4  # beyond -> removed
    assert "S3" in gs.lords["arisighi"].capabilities
    resolve_disband(gs, "seljuk")
    assert "S3" in gs.seljuk.draw_deck
    assert gs.lords["arisighi"].capabilities == []
