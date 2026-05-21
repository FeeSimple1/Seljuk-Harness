"""Phase 3a: non-combat Commands — Tax (4.5.6), Forage (4.5.4), Ravage (4.5.5),
Supply (4.4), Recruit (4.5.7)."""
import pytest

from seljuk import scenarios as S, engine, campaign
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _activate(gs, lord_id, actions=4):
    """Put a Lord on a Command card in isolation (empty Plans -> the card ends
    cleanly into End Campaign)."""
    gs.meta.phase = "campaign"
    gs.meta.subphase = "campaign.command"
    gs.meta.active_player = gs.lords[lord_id].side
    gs.meta.active_lord = lord_id
    gs.meta.active_card = lord_id
    gs.meta.actions_remaining = actions


def test_tax_at_own_seat_adds_coin_and_ends_card_456():
    gs = S.load_scenario("emperor_and_the_lion")
    _activate(gs, "alp_arslan")  # at Ani, his Seat
    before = gs.lords["alp_arslan"].assets.coin
    r = engine.apply_action(gs, {"type": "cmd_tax", "lord": "alp_arslan"})
    assert gs.lords["alp_arslan"].assets.coin == before + 1
    assert r["placed_ravaged"] is False
    assert gs.meta.active_lord is None  # whole card consumed


def test_roman_commander_empire_tax_places_seljuk_ravaged_456():
    gs = S.load_scenario("emperor_and_the_lion")
    man = gs.lords["manuel_komnenos"]
    man.mustered = True
    man.cylinder = "ankyra"  # Roman Empire Stronghold, not his Seat, unravaged
    man.service_box = 6
    # Make Manuel the Commander (Romanos off map) so he may Empire-Tax.
    gs.lords["romanos_diogenes"].mustered = False
    gs.lords["romanos_diogenes"].cylinder = "calendar"
    _activate(gs, "manuel_komnenos")
    r = engine.apply_action(gs, {"type": "cmd_tax", "lord": "manuel_komnenos"})
    assert r["placed_ravaged"] is True
    assert gs.locales["ankyra"].ravaged_side == "seljuk"


def test_tax_rejected_off_seat_for_non_commander_456():
    gs = S.load_scenario("emperor_and_the_lion")
    ch = gs.lords["chatatourios"]
    ch.cylinder = "ankyra"  # not his Seat; not a Commander
    _activate(gs, "chatatourios")
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cmd_tax", "lord": "chatatourios"})


def test_forage_auto_at_friendly_garden_454():
    gs = S.load_scenario("emperor_and_the_lion")
    ch = gs.lords["chatatourios"]  # at Antioch (Roman city w/ garden)
    before = ch.assets.provender
    _activate(gs, "chatatourios")
    r = engine.apply_action(gs, {"type": "cmd_forage", "lord": "chatatourios"})
    assert r["auto"] and ch.assets.provender == before + 1
    assert gs.meta.actions_remaining == 3


def test_forage_blocked_by_ravaged_454():
    gs = S.load_scenario("emperor_and_the_lion")
    ch = gs.lords["chatatourios"]
    gs.locales[ch.cylinder].ravaged_side = "seljuk"
    _activate(gs, "chatatourios")
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cmd_forage", "lord": "chatatourios"})


def test_ravage_roman_auto_succeeds_455():
    gs = S.load_scenario("emperor_and_the_lion")
    ch = gs.lords["chatatourios"]
    ch.cylinder = "azaz"  # Seljuk Sultanate fort -> enemy to Roman
    _activate(gs, "chatatourios")
    r = engine.apply_action(gs, {"type": "cmd_ravage", "lord": "chatatourios"})
    assert r["success"]
    assert gs.locales["azaz"].ravaged_side == "roman"
    assert ch.assets.provender >= 1 and ch.assets.loot >= 1  # at a Stronghold


def test_ravage_seljuk_two_actions_auto_455():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "larisa"  # Roman unfortified settlement -> enemy to Seljuk
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_ravage", "lord": "alp_arslan", "actions": 2})
    assert r["success"] and gs.locales["larisa"].ravaged_side == "seljuk"
    assert gs.meta.actions_remaining == 2  # spent 2 of 4


def test_ravage_seljuk_one_action_themata_defence_declined_455():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "larisa"  # Thema Lykandos has 1 Militia
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_ravage", "lord": "alp_arslan", "actions": 1})
    assert r.get("pending") == "ravage_defence"
    # Roman is owed the response; legal_moves surfaces the defence options.
    opts = engine.legal_moves(gs)
    assert any(m["type"] == "resolve_ravage_defence" for m in opts)
    r2 = engine.apply_action(gs, {"type": "resolve_ravage_defence", "defend_with": None})
    assert r2["success"] and gs.locales["larisa"].ravaged_side == "seljuk"


def test_ravage_seljuk_one_action_themata_defends_455():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "larisa"
    _activate(gs, "alp_arslan")
    engine.apply_action(gs, {"type": "cmd_ravage", "lord": "alp_arslan", "actions": 1})
    before = len(gs.themata["Lykandos"])
    r = engine.apply_action(gs, {"type": "resolve_ravage_defence", "defend_with": 0})
    # Militia Protection 1-1: success on a 1 (Ravage fails, marker kept), else lost.
    if r["success"]:
        assert len(gs.themata["Lykandos"]) == before - 1  # Themata eliminated
    else:
        assert gs.locales["larisa"].ravaged_side is None
        assert len(gs.themata["Lykandos"]) == before


def test_ravage_rejects_friendly_locale_455():
    gs = S.load_scenario("emperor_and_the_lion")
    _activate(gs, "alp_arslan")  # at Ani, Seljuk-friendly
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cmd_ravage", "lord": "alp_arslan", "actions": 2})


def test_supply_at_seat_costs_zero_44():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]  # at Ani (a Seat)
    before = aa.assets.provender
    _activate(gs, "alp_arslan")
    r = engine.apply_action(gs, {"type": "cmd_supply", "lord": "alp_arslan"})
    assert r["route_cost"] == 0 and aa.assets.provender == before + 1


def test_supply_needs_carts_for_distant_seat_441():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "mempet"  # 1 Road from Ani (a Seat) -> cost 1
    aa.assets.carts = 0
    _activate(gs, "alp_arslan")
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cmd_supply", "lord": "alp_arslan"})
    aa.assets.carts = 1
    r = engine.apply_action(gs, {"type": "cmd_supply", "lord": "alp_arslan"})
    assert r["route_cost"] == 1


def test_recruit_roman_commander_takes_themata_457():
    gs = S.load_scenario("emperor_and_the_lion")
    rom = gs.lords["romanos_diogenes"]
    rom.cylinder = "kaisareia"  # Charsianon Thema (has 1 Militia after removal)
    _activate(gs, "romanos_diogenes")
    before = len(gs.themata["Charsianon"])
    r = engine.apply_action(gs, {"type": "cmd_recruit", "lord": "romanos_diogenes", "marker_index": 0})
    assert len(gs.themata["Charsianon"]) == before - 1
    assert len(rom.themata_on_mat) == 1
