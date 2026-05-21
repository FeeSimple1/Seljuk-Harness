"""Phase 4b: combat Capability modifiers (Protection, Strikes, Garrison)."""
from seljuk import scenarios as S, capabilities as C
from seljuk.battle import _lord_step_hits_caps, _build_garrison
from seljuk.state import ThemataMarker


def _setup(gs, lord_id, caps, forces, side_caps=None):
    l = gs.lords[lord_id]; l.mustered = True; l.capabilities = list(caps); l.forces = dict(forces)
    if side_caps:
        gs.side_decks(l.side).capabilities_in_play = list(side_caps)
    return l


# --- Protection ---
def test_klibanophoroi_tagmata_armor_1_4_r11():
    gs = S.load_scenario("emperor_and_the_lion")
    _setup(gs, "chatatourios", ["R11"], {"tagmata": 1})
    assert C.protection_range(gs, "chatatourios", "tagmata", "melee") == (1, 4)


def test_syndosis_militia_armor_1_2_r13():
    gs = S.load_scenario("emperor_and_the_lion")
    _setup(gs, "chatatourios", ["R13"], {"militia": 1})
    assert C.protection_range(gs, "chatatourios", "militia", "melee") == (1, 2)


def test_steeled_resolve_infantry_armor_1_4_r3():
    gs = S.load_scenario("emperor_and_the_lion")
    _setup(gs, "chatatourios", ["R3"], {"infantry": 1})
    assert C.protection_range(gs, "chatatourios", "infantry", "missile") == (1, 4)


def test_lamellar_armor_turkic_1_3_until_three_rout_s1():
    gs = S.load_scenario("emperor_and_the_lion")
    l = _setup(gs, "alp_arslan", ["S1"], {"turkic_horse": 6})
    assert C.protection_range(gs, "alp_arslan", "turkic_horse", "missile") == (1, 3)
    l.flags["turkic_routed_battle"] = 3  # after 3 rout -> Lamellar off
    assert C.protection_range(gs, "alp_arslan", "turkic_horse", "missile") == (1, 1)


def test_turkic_evade_vs_melee_unarmored_vs_missile_default():
    gs = S.load_scenario("emperor_and_the_lion")
    _setup(gs, "alp_arslan", [], {"turkic_horse": 6})
    assert C.protection_range(gs, "alp_arslan", "turkic_horse", "melee") == (1, 3)   # Evade
    assert C.protection_range(gs, "alp_arslan", "turkic_horse", "missile") == (1, 1)  # Unarmored
    assert C.protection_range(gs, "alp_arslan", "turkic_horse", "melee", storm=True) == (1, 1)  # no Evade in Storm


# --- Strikes ---
def test_javelins_adds_infantry_missiles_s11():
    gs = S.load_scenario("emperor_and_the_lion")
    _setup(gs, "sav_tekin", ["S11"], {"infantry": 2})
    normal, anti = _lord_step_hits_caps(gs, "sav_tekin", "missile", 1)
    assert normal == 2.0  # 2 Infantry x1 Missile


def test_shock_tactics_grants_turkic_melee_s4_q002():
    gs = S.load_scenario("emperor_and_the_lion")
    _setup(gs, "alp_arslan", ["S4"], {"turkic_horse": 3})
    normal, _ = _lord_step_hits_caps(gs, "alp_arslan", "horse_melee", 1)
    assert normal == 1.0  # ceil(3/2)=2 units x0.5 = 1 (errata example)
    # Without Shock Tactics, Turkic base Melee is 0 (Q-002).
    _setup(gs, "alp_arslan", [], {"turkic_horse": 3})
    n2, _ = _lord_step_hits_caps(gs, "alp_arslan", "horse_melee", 1)
    assert n2 == 0.0


def test_bardoukia_makes_tagmata_melee_anti_armor_r21():
    gs = S.load_scenario("emperor_and_the_lion")
    _setup(gs, "chatatourios", ["R21"], {"tagmata": 2})
    normal, anti = _lord_step_hits_caps(gs, "chatatourios", "horse_melee", 1)
    assert anti == 2.0 and normal == 0.0  # 2 Tagmata melee moved to anti-armor


def test_alakatia_extra_anti_armor_missile_with_two_infantry_r23():
    gs = S.load_scenario("emperor_and_the_lion")
    _setup(gs, "chatatourios", ["R23"], {"infantry": 2})
    normal, anti = _lord_step_hits_caps(gs, "chatatourios", "missile", 1)
    assert anti == 1.0  # +1 anti-armor Missile Hit (>=2 Infantry)


# --- Garrison ---
def test_fortified_garrisons_swaps_militia_for_infantry_on_roman_storm_s23():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.seljuk.capabilities_in_play = ["S23"]
    # Roman storms a Seljuk fort (garrison: 1 Infantry + 1 Militia) -> swap militia->infantry.
    g = _build_garrison(gs, "azaz", attacker_side="roman")
    assert g.get("infantry", 0) == 2 and g.get("militia", 0) == 0


def test_armenian_garrisons_uses_both_columns_r16():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.roman.capabilities_in_play = ["R16"]
    # A Roman-Conquered Stronghold outside the Roman Empire (e.g. a Seljuk fort).
    gs.locales["azaz"].conquered_side = "roman"; gs.locales["azaz"].conquered_count = 1
    g = _build_garrison(gs, "azaz", attacker_side="seljuk")
    # Roman fort garrison (1 Militia) + Seljuk fort garrison (1 Infantry + 1 Militia)
    assert g.get("militia", 0) == 2 and g.get("infantry", 0) == 1
