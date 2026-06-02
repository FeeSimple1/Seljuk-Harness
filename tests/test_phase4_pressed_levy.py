"""Phase 4: R4 Pressed Levy Service -- Romans keep 1 Unpaid Thema's Levied
Themata at Reset (4.7.5) instead of returning all of them."""
from seljuk import scenarios as S, campaign
from seljuk.state import ThemataMarker


def _commander(gs):
    return gs.lords["romanos_diogenes"]


def test_pressed_levy_keeps_one_thema():
    gs = S.load_scenario("emperor_and_the_lion")
    cmd = _commander(gs)
    cmd.themata_on_mat = [ThemataMarker(unit="infantry", home_thema="Anatolikon"),
                          ThemataMarker(unit="militia", home_thema="Anatolikon"),
                          ThemataMarker(unit="tagmata", home_thema="Charsianon")]
    gs.roman.capabilities_in_play = ["R4"]   # Pressed Levy Service
    campaign._reset(gs)
    kept = {m.home_thema for m in cmd.themata_on_mat}
    assert kept == {"Anatolikon"}            # the larger Thema retained (2 markers)
    assert len(cmd.themata_on_mat) == 2


def test_without_pressed_levy_all_returned():
    gs = S.load_scenario("emperor_and_the_lion")
    cmd = _commander(gs)
    cmd.themata_on_mat = [ThemataMarker(unit="infantry", home_thema="Anatolikon")]
    campaign._reset(gs)
    assert cmd.themata_on_mat == []
