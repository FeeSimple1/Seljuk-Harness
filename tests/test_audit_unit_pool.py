"""1.6: the finite unit-component pool is a hard cap on Muster (3.4.1) and Levy
Vassal (3.4.2) -- "if too few unit pieces remain in the pool, the Lord does not
receive those units." Pool manifest (Rules 1.6): Ghulam 6, Scholai 2, Varangian
2, Norman Knights 5, Turkic Horse 47, Tagmata 25, Infantry 52, Militia 11."""
import pytest

from seljuk import actions, battle, engine, scenarios as S, static_data as sd
from seljuk.rng import DiceRoller
from seljuk.state import ThemataMarker
from tests.test_cross_game_combat import position
from tests.test_decisions_d008_sally import _cmd, _muster_siege_lord


def test_pool_manifest_totals():
    assert actions._UNIT_POOL["ghulam_cavalry"] == 6
    assert actions._UNIT_POOL["scholai_hetaireia"] == 2
    assert sum(v for k, v in actions._UNIT_POOL.items()
               if sd.forces()["units"][k]["category"] == "horse") == 85
    assert sum(v for k, v in actions._UNIT_POOL.items()
               if sd.forces()["units"][k]["category"] == "foot") == 65


def test_units_in_play_counts_forces_routed_and_themata():
    gs = S.load_scenario("emperor_and_the_lion")
    for l in gs.lords.values():
        l.forces = {}; l.routed = {}; l.themata_on_mat = []
    gs.themata = {}
    a = gs.lords["alp_arslan"]; a.forces = {"ghulam_cavalry": 2}; a.routed = {"ghulam_cavalry": 1}
    a.themata_on_mat = [ThemataMarker(unit="tagmata", symbols=2)]
    c = actions._units_in_play(gs)
    assert c["ghulam_cavalry"] == 3 and c["tagmata"] == 2


def test_alloc_clamps_to_remaining_pool():
    gs = S.load_scenario("emperor_and_the_lion")
    for l in gs.lords.values():
        l.forces = {}; l.routed = {}; l.themata_on_mat = []
    gs.themata = {}
    # 5 of 6 Ghulam already deployed -> only 1 left.
    gs.lords["alp_arslan"].forces = {"ghulam_cavalry": 5}
    out = actions._alloc_from_pool(gs, {"ghulam_cavalry": 2, "turkic_horse": 3})
    assert out["ghulam_cavalry"] == 1 and out["turkic_horse"] == 3


def test_muster_clamps_starting_forces_to_pool():
    gs = S.load_scenario("emperor_and_the_lion")
    for l in gs.lords.values():
        l.forces = {}; l.routed = {}; l.themata_on_mat = []
    gs.themata = {}
    # Park 5 Ghulam elsewhere; sav_tekin musters wanting 2 -> gets only 1.
    gs.lords["alp_arslan"].forces = {"ghulam_cavalry": 5}
    st = gs.lords["sav_tekin"]; st.mustered = False; st.cylinder = "off_map"; st.forces = {}
    actions._muster_lord_onto_map(gs, st, "amid")
    assert st.forces.get("ghulam_cavalry") == 1          # clamped from 2
    assert st.forces.get("infantry") == 2                # plentiful, unchanged


def test_muster_uncapped_when_pool_has_room():
    gs = S.load_scenario("emperor_and_the_lion")
    st = gs.lords["sav_tekin"]; st.mustered = False; st.forces = {}
    actions._muster_lord_onto_map(gs, st, "amid")
    assert st.forces == {"infantry": 2, "ghulam_cavalry": 2}   # full starting Forces


@pytest.mark.parametrize("remaining, foot_hits", [(3, 0), (4, 1)])
def test_storm_limits_armenian_garrisons_to_available_militia(remaining, foot_hits):
    gs = position()
    gs.meta.rng_state = DiceRoller(3).get_state()
    _cmd(gs, "alp_arslan", "seljuk")
    _muster_siege_lord(gs, "alp_arslan").cylinder = "ani"
    _muster_siege_lord(gs, "andronikos_doukas", {"militia": 3}).cylinder = "antioch"
    chatatourios = _muster_siege_lord(gs, "chatatourios", {"infantry": 2})
    chatatourios.cylinder = "antioch"
    if remaining == 3:
        chatatourios.forces["militia"] = 1
    romanos = _muster_siege_lord(gs, "romanos_diogenes", {"infantry": 1})
    romanos.cylinder = "antioch"
    for home in ("Anatolikon", "Charsianon", "Lykandos", "Melitene"):
        box = gs.themata[home]
        marker = next(marker for marker in box if marker.unit == "militia")
        box.remove(marker)
        romanos.themata_on_mat.append(marker.model_copy(update={"home_thema": home}))

    gs.roman.draw_deck.remove("R16")
    gs.roman.capabilities_in_play.append("R16")
    ani = gs.locales["ani"]
    ani.conquered_side = "roman"
    ani.conquered_count = 3
    ani.siege_markers = 2

    assert actions._pool_remaining(gs, "militia") == remaining
    assert battle._build_garrison(gs, "ani") == {"infantry": 2, "militia": remaining}
    result = engine.apply_action(gs, {"type": "cmd_storm", "lord": "alp_arslan"})
    assert result["ok"]
    strikes = result["storm"]["strikes"]
    assert [strike["hits"] for strike in strikes
            if strike["round"] == 1 and strike["step"] == "def_foot_melee"] == [foot_hits]


def test_storm_keeps_assigned_themata_when_no_fresh_militia_is_available(monkeypatch):
    gs = position()
    box = gs.themata["Melitene"]
    marker = next(marker for marker in box if marker.unit == "militia")
    box.remove(marker)
    gs.locales["melitene"].themata_defending.append(marker)
    monkeypatch.setitem(actions._UNIT_POOL, "militia", actions._units_in_play(gs)["militia"])

    assert actions._pool_remaining(gs, "militia") == 0
    assert battle._build_garrison(gs, "melitene") == {"militia": 1}
