"""Phase 4: R22 Cavalry Supply Line Raiders / S22 Turkmen Skirmishers --
during Wastage, 1 adjacent enemy Lord undergoes Wastage twice (4.7.4)."""
from seljuk import scenarios as S, campaign


def test_r22_raiders_cause_adjacent_double_wastage():
    gs = S.load_scenario("emperor_and_the_lion")
    rom = gs.lords["chatatourios"]
    rom.mustered = True; rom.cylinder = "artah"; rom.capabilities = ["R22"]
    afsin = gs.lords["afsin_beg"]            # at manbij, adjacent to artah
    afsin.mustered = True; afsin.cylinder = "manbij"; afsin.assets.carts = 5
    sav = gs.lords["sav_tekin"]              # at ani, not adjacent to a raider
    sav.mustered = True; sav.cylinder = "ani"; sav.assets.carts = 5
    campaign._wastage(gs)
    assert gs.lords["afsin_beg"].assets.carts == 3   # normal + R22 extra Wastage
    assert gs.lords["sav_tekin"].assets.carts == 4   # one Wastage only


def test_s22_skirmishers_same_effect():
    gs = S.load_scenario("emperor_and_the_lion")
    sav = gs.lords["sav_tekin"]              # Seljuk raider at manbij
    sav.mustered = True; sav.cylinder = "manbij"; sav.capabilities = ["S22"]
    rom = gs.lords["chatatourios"]           # Roman at artah (adjacent)
    rom.mustered = True; rom.cylinder = "artah"; rom.assets.coin = 5
    campaign._wastage(gs)
    assert gs.lords["chatatourios"].assets.coin == 3   # wasted twice
