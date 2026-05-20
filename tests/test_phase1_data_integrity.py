"""Phase 1 static-data integrity (Rules 1.3.1, 1.5.x, 1.6, 1.9, 4.1).

Each test asserts a count or invariant that must hold for the encoded
reference data to match the rulebook/references.
"""
from seljuk import static_data as sd


def test_map_locale_and_way_counts():
    """Map Reference: 44 Locales (42 + 2 Holding Boxes), 15 Pass + 47 Road Ways, 4 whole-Command routes."""
    locs = sd.all_locale_ids()
    assert len(locs) == 44
    ways = sd.ways()
    assert sum(1 for w in ways if w["type"] == "pass") == 15
    assert sum(1 for w in ways if w["type"] == "road") == 47
    assert sum(1 for w in ways if w["whole_command_card"]) == 4


def test_khliat_anzitene_is_pass_d001():
    """D-001: the Khliat<->Anzitene Way is a Pass (user-adjudicated)."""
    ways = sd.ways()
    edge = [w for w in ways if {w["a"], w["b"]} == {"khliat", "anzitene"}]
    assert len(edge) == 1 and edge[0]["type"] == "pass"


def test_no_duplicate_ways_and_all_locales_connected():
    seen = set()
    touched = set()
    for w in sd.ways():
        key = frozenset((w["a"], w["b"]))
        assert key not in seen, w
        seen.add(key)
        touched.update((w["a"], w["b"]))
    assert touched == set(sd.all_locale_ids())


def test_holding_boxes_and_allegiances():
    locs = sd.game_map()["locales"]
    hb = [lid for lid, v in locs.items() if v["type"] == "holding_box"]
    assert set(hb) == {"to_constantinople", "to_mosul_and_baghdad"}
    fatimid = [lid for lid, v in locs.items() if v["allegiance"] == "fatimid"]
    assert set(fatimid) == {"hama", "aleppo", "syria"}


def test_lord_roster_counts():
    """1.5.1: eight Lords on each side (dual-allegiance Lords counted on their primary side)."""
    assert len(sd.lord_ids_for_side("roman")) == 8
    assert len(sd.lord_ids_for_side("seljuk")) == 8
    assert len(sd.all_lord_ids()) == 16


def test_commanders_flagged():
    assert sd.lord("romanos_diogenes")["commander"] == "always"
    assert sd.lord("alp_arslan")["commander"] == "always"
    assert sd.lord("manuel_komnenos")["commander"] == "conditional"


def test_force_types():
    """1.6 / Forces sheet: five Horse and three Foot types."""
    u = sd.forces()["units"]
    horse = [k for k, v in u.items() if v["category"] == "horse"]
    foot = [k for k, v in u.items() if v["category"] == "foot"]
    assert len(horse) == 5 and len(foot) == 3


def test_stronghold_profiles_and_aleppo_override():
    """1.3.1 / 4.5.1: Fort/Town/City values 1/2/3; Aleppo rolls 4 Surrender dice."""
    assert sd.stronghold_profile("herakleia_kybistra")["value"] == 1   # fort
    assert sd.stronghold_profile("ankyra")["value"] == 2               # town
    assert sd.stronghold_profile("antioch")["value"] == 3              # city
    assert sd.stronghold_profile("aleppo")["surrender_dice"] == 4
    assert sd.stronghold_profile("aleppo")["garrison_column_forced"] == "seljuk"
    assert sd.stronghold_profile("western_anatolia") is None           # wilderness


def test_card_counts_and_scopes():
    """1.9.1 / Arts of War: 25 cards per side; ALL Capabilities are side-wide."""
    cards = sd.cards()["cards"]
    assert sum(1 for c in cards if c.startswith("R")) == 25
    assert sum(1 for c in cards if c.startswith("S")) == 25
    sidewide = [cid for cid, c in cards.items() if c["capability"]["scope"] == "side_wide"]
    assert len(sidewide) == 10
    for cid in sidewide:
        assert cards[cid]["capability"]["heraldry"] == "ALL"


def test_lamellar_armor_two_copies_and_mules_two_copies():
    cards = sd.cards()["cards"]
    lamellar = [cid for cid, c in cards.items() if c["capability"]["name"] == "Lamellar Armor"]
    mules = [cid for cid, c in cards.items() if c["capability"]["name"] == "Mules"]
    shock = [cid for cid, c in cards.items() if c["capability"]["name"] == "Shock Tactics"]
    assert set(lamellar) == {"S1", "S2"}
    assert set(mules) == {"R24", "S25"}
    assert set(shock) == {"S4", "S6"}


def test_command_deck_totals():
    """1.2 component counts: 42 Roman / 46 Seljuk Command cards."""
    cd = sd.command_decks()
    assert cd["roman"]["total"] == 42
    assert cd["seljuk"]["total"] == 46


def test_themata_baseline_and_removals_applicable():
    """1.5.1 / scenario 'Remove from Play' lists are all applicable to the 1068 baseline."""
    data = sd.themata()
    baseline = data["baseline_1068"]
    assert sum(len(v) for v in baseline.values()) == 31
    for sc, rem in data["scenario_removals"].items():
        for thema, marks in rem.items():
            pool = [tuple(m.values()) for m in baseline[thema]]
            for m in marks:
                t = (m["unit"], m["symbols"])
                assert t in pool, (sc, thema, m)
                pool.remove(t)
