"""Optional Rule 6.1 Hidden Mats: a side cannot see the enemy's Mustered Lord
mats (Forces, Assets, Vassals, This-Lord Capabilities); board-visible state
(Locale, Service, Besieged) stays public. Off by default."""
from seljuk import scenarios as S
from seljuk.llm import view


def _mustered_enemy(gs, side):
    enemy = "roman" if side == "seljuk" else "seljuk"
    lid = next(l for l, x in gs.lords.items() if x.side == enemy)
    gs.lords[lid].mustered = True
    gs.lords[lid].forces = {"turkic_horse": 3}
    return lid


def test_hidden_mats_redacts_enemy_mustered_mats():
    gs = S.load_scenario("emperor_and_the_lion", options={"hidden_mats": True})
    lid = _mustered_enemy(gs, "seljuk")
    d = view.filtered_state(gs, "seljuk")
    e = d["lords"][lid]
    assert e["forces"] == "<hidden>" and e["assets"] == "<hidden>"
    assert e["vassals"] == "<hidden>" and e["capabilities"] == "<hidden>"
    assert e["cylinder"] == gs.lords[lid].cylinder          # Locale stays public
    assert e["mustered"] is True


def test_hidden_mats_keeps_own_mats_visible():
    gs = S.load_scenario("emperor_and_the_lion", options={"hidden_mats": True})
    own = next(l for l, x in gs.lords.items() if x.side == "seljuk")
    gs.lords[own].mustered = True; gs.lords[own].forces = {"ghulam_cavalry": 2}
    d = view.filtered_state(gs, "seljuk")
    assert d["lords"][own]["forces"] == {"ghulam_cavalry": 2}   # own Forces visible


def test_hidden_mats_off_by_default_shows_enemy_forces():
    gs = S.load_scenario("emperor_and_the_lion")
    lid = _mustered_enemy(gs, "seljuk")
    d = view.filtered_state(gs, "seljuk")
    assert d["lords"][lid]["forces"] == {"turkic_horse": 3}     # standard rules: visible
