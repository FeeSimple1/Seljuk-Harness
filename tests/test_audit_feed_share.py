"""Audit tidy: Feed Sharing covers the smallest shortfalls first, minimising the
number of Unfed Lords (B.3.1)."""
from seljuk import scenarios as S, campaign


def test_share_feeds_small_need_lords_first():
    gs = S.load_scenario("emperor_and_the_lion")
    # Three co-located movers: A needs 2, B & C need 1 each. A non-mover provider
    # at the same Locale has exactly 2 Provender.
    A, B, C = "alp_arslan", "afsin_beg", "sav_tekin"
    for lid, units in ((A, 9), (B, 1), (C, 1)):   # 9 units -> need 2; 1 unit -> need 1
        l = gs.lords[lid]; l.side = "seljuk"; l.mustered = True; l.moved_fought = True
        l.cylinder = "ani"; l.forces = {"turkic_horse": units}
        l.assets.provender = 0; l.assets.loot = 0; l.service_box = 6
    prov = gs.lords["artuk_beg"]; prov.side = "seljuk"; prov.mustered = True
    prov.cylinder = "ani"; prov.moved_fought = False; prov.assets.provender = 2; prov.assets.loot = 0
    result = {"feed": [], "disband": []}
    campaign._feed_side(gs, "seljuk", result)
    unfed = {e["lord"] for e in result["feed"] if e["unfed"]}
    # Optimal: feed B and C (1 each) -> only A is Unfed (1 Unfed, not 2).
    assert unfed == {"alp_arslan"}
