"""Phase 6 (R2): remaining immediate / This-Campaign Event resolvers."""
from seljuk import scenarios as S, engine, campaign
from seljuk.rng import DiceRoller


def _q(gs, card, side):
    gs.meta.phase = "levy"
    gs.meta.pending.append({"type": "event_pending_resolution", "card": card, "side": side, "tags": ["immediate"]})


def test_flooded_river_wastages_alp_arslan_r1():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.lords["alp_arslan"].assets.carts = 3  # excess to discard
    _q(gs, "R1", "roman")
    r = engine.apply_action(gs, {"type": "resolve_event", "card": "R1", "args": {}})
    assert r["alp_arslan_wastage_times"] >= 1
    assert "R1" in gs.meta.asterisks_used


def test_chrysoskoulos_discards_seljuk_held_when_arisighi_roman_r11():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.lords["arisighi"].side = "roman"
    gs.seljuk.held_events = ["S4"]
    _q(gs, "R11", "roman")
    r = engine.apply_action(gs, {"type": "resolve_event", "card": "R11", "args": {}})
    assert r.get("discarded_held") == "S4"


def test_anglo_saxon_adds_varangian_r16():
    gs = S.load_scenario("emperor_and_the_lion")
    ch = gs.lords["chatatourios"]; ch.forces.pop("varangian_guard", None)
    _q(gs, "R16", "roman")
    engine.apply_action(gs, {"type": "resolve_event", "card": "R16", "args": {"lord": "chatatourios"}})
    assert ch.forces.get("varangian_guard", 0) == 1


def test_assassination_disbands_ibn_khan_when_far_r22():
    gs = S.load_scenario("emperor_and_the_lion")
    ik = gs.lords["ibn_khan"]; ik.mustered = True; ik.cylinder = "ani"  # far from Aleppo
    _q(gs, "R22", "roman")
    r = engine.apply_action(gs, {"type": "resolve_event", "card": "R22", "args": {}})
    assert r.get("disbanded") == "ibn_khan" and gs.lords["ibn_khan"].cylinder == "removed"


def test_assassination_shifts_when_near_aleppo_r22():
    gs = S.load_scenario("emperor_and_the_lion")
    ik = gs.lords["ibn_khan"]; ik.mustered = True; ik.cylinder = "hama"; ik.service_box = 6  # adjacent to Aleppo
    _q(gs, "R22", "roman")
    r = engine.apply_action(gs, {"type": "resolve_event", "card": "R22", "args": {"direction": "left"}})
    assert "shifted" in r and gs.lords["ibn_khan"].cylinder == "hama"


def test_norman_scheming_discards_roman_held_s11():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.lords["robert_crepin"].side = "seljuk"
    gs.roman.held_events = ["R3"]
    _q(gs, "S11", "seljuk")
    r = engine.apply_action(gs, {"type": "resolve_event", "card": "S11", "args": {}})
    assert r.get("discarded_held") == "R3"


def test_moustache_makes_alp_arslan_forage_harder_s9():
    gs = S.load_scenario("emperor_and_the_lion")
    _q(gs, "S9", "seljuk")
    engine.apply_action(gs, {"type": "resolve_event", "card": "S9", "args": {}})
    assert gs.meta.notes.get("moustache_campaign") is True


def test_mercenary_discipline_wastages_roman_at_ravaged_s25():
    gs = S.load_scenario("emperor_and_the_lion")
    ch = gs.lords["chatatourios"]; ch.cylinder = "larisa"; ch.assets.provender = 3
    gs.locales["larisa"].ravaged_side = "seljuk"
    _q(gs, "S25", "seljuk")
    r = engine.apply_action(gs, {"type": "resolve_event", "card": "S25", "args": {}})
    assert r["roman_wastage"] >= 1


def test_peace_offering_adds_gifts_exchanged_s13():
    gs = S.load_scenario("emperor_and_the_lion")
    _q(gs, "S13", "seljuk")
    engine.apply_action(gs, {"type": "resolve_event", "card": "S13", "args": {}})
    assert "S13" in gs.seljuk.capabilities_in_play
