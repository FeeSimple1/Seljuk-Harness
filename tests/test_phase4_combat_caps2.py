"""Phase 4: R3 Steeled Resolve (Infantry 1-4 vs Horse, 1 Round) and
S16 Parthian Shot (Turkic Horse Missiles are striker-selected)."""
from seljuk import scenarios as S, battle, capabilities


def test_r3_steeled_resolve_only_vs_horse():
    gs = S.load_scenario("emperor_and_the_lion")
    lid = "chatatourios"
    gs.lords[lid].capabilities = ["R3"]   # Steeled Resolve
    pr = capabilities.protection_range
    assert pr(gs, lid, "infantry", "melee", vs_horse=True) == (1, 4)    # vs Horse -> 1-4
    assert pr(gs, lid, "infantry", "melee", vs_horse=False) == (1, 3)   # vs Foot -> base 1-3
    gs.lords[lid].capabilities = []
    assert pr(gs, lid, "infantry", "melee", vs_horse=True) == (1, 3)    # no Capability -> 1-3


def test_s16_parthian_shot_routes_turkic_missiles_to_select_bucket():
    gs = S.load_scenario("emperor_and_the_lion")
    side = battle._Side(gs, [], "attacker")
    lid = "sav_tekin"
    L = gs.lords[lid]; L.mustered = True
    L.forces = {"turkic_horse": 3, "tagmata": 2}   # 3x1 turkic + 2x0.5 tagmata missiles
    side.front["center"] = lid
    # Without Parthian Shot: all missiles are 'normal', select bucket empty.
    n, a, sel = battle._lord_step_hits_caps(gs, lid, "missile", 1)
    assert sel == 0.0 and n == 3.0 + 1.0
    # With Parthian Shot: the Turkic Horse missiles (3) move to the select bucket.
    L.capabilities = ["S16"]
    n2, a2, sel2 = battle._lord_step_hits_caps(gs, lid, "missile", 1)
    assert sel2 == 3.0 and n2 == 1.0   # tagmata (1.0) stays normal; turkic (3) selects
