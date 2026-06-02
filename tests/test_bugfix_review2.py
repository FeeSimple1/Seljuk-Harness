"""Regression tests for the second-pass bug-review fixes (June 2026)."""
import pytest

from seljuk import scenarios as S
from seljuk import campaign
from seljuk import battle
from seljuk import capabilities
from seljuk import static_data as sd
from seljuk.rng import DiceRoller


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


# --- Storm uses the reduced Storm strike for Norman Knights / Varangian -------

def test_storm_strike_norman_and_varangian_use_storm_value():
    gs = _gs()
    side = battle._Side(gs, [], "defender")
    lid = next(l for l, x in gs.lords.items() if x.side == "roman")
    gs.lords[lid].mustered = True
    gs.lords[lid].forces = {"norman_knights": 2, "varangian_guard": 2}
    side.front["center"] = lid
    storm = battle._lord_melee_capped(gs, side, round_no=1, storm=True)
    battle_val = battle._lord_melee_capped(gs, side, round_no=1, storm=False)
    # Storm: 2 norman x1 + 2 varangian x1 = 4. Battle: 2x2 + 2x3 = 10 (capped 6).
    assert storm == 4.0
    assert battle_val == 6.0  # Battle value is higher and hits the 6-Hit cap


def test_storm_strike_other_units_unchanged():
    gs = _gs()
    side = battle._Side(gs, [], "attacker")
    lid = "alp_arslan"
    gs.lords[lid].mustered = True
    gs.lords[lid].forces = {"ghulam_cavalry": 2}   # melee x1, no separate Storm value
    side.front["center"] = lid
    assert battle._lord_melee_capped(gs, side, 1, storm=True) == 2.0
    assert battle._lord_melee_capped(gs, side, 1, storm=False) == 2.0


# --- Feed: all Lords self-feed FIRST, then share (B.3.1) ----------------------

def test_feed_self_first_penalizes_the_lord_without_food():
    gs = _gs()
    # Two co-located Seljuk movers, each needing 1; the Lord WITH provender must
    # not be the one penalized.
    a, b = "alp_arslan", "afsin_beg"
    for lid in (a, b):
        l = gs.lords[lid]
        l.side = "seljuk"; l.mustered = True; l.moved_fought = True
        l.forces = {"turkic_horse": 1}            # needs 1
        l.assets.provender = 0; l.assets.loot = 0
        l.service_box = 6
    gs.lords[a].cylinder = gs.lords[b].cylinder = "ani"
    gs.lords[b].assets.provender = 1              # only b brought food
    result = {"feed": [], "disband": []}
    campaign._feed_side(gs, "seljuk", result)
    # b fed itself; a is the unfed one whose Service shifts left.
    assert gs.lords[b].service_box == 6           # not penalized
    assert gs.lords[a].service_box == 5           # penalized
    unfed = {e["lord"]: e["unfed"] for e in result["feed"]}
    assert unfed[a] is True and unfed[b] is False


# --- Winter Quarters: Unladen (Provender<=Carts) BEFORE halving Carts ---------

def test_winter_quarters_provender_capped_to_carts_before_halving():
    gs = _gs()
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "larisa"                          # away from Seat
    aa.assets.provender = 4
    aa.assets.carts = 4
    aa.assets.loot = 1
    campaign._winter_quarters(gs)
    assert aa.assets.loot == 0
    assert aa.assets.carts == 2                     # 4 halved
    # Provender was already <= original Carts (4), so it is retained, NOT
    # over-discarded down to the halved cart count (2).
    assert aa.assets.provender == 4


def test_winter_quarters_excess_provender_discarded_to_original_carts():
    gs = _gs()
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "larisa"
    aa.assets.provender = 5
    aa.assets.carts = 3
    campaign._winter_quarters(gs)
    assert aa.assets.carts == 2                     # 3 halved (round up)
    assert aa.assets.provender == 3                 # capped to original carts (3), then carts halved


# --- Hardening: stronghold_profile copy + protection_range no KeyError --------

def test_stronghold_profile_returns_isolated_copy():
    prof = sd.stronghold_profile("melitene")
    assert prof is not None
    prof["walls"] = "MUTATED"
    assert sd.stronghold_profile("melitene").get("walls") != "MUTATED"


def test_protection_range_unknown_unit_no_keyerror():
    gs = _gs()
    assert capabilities.protection_range(gs, "alp_arslan", "nonexistent_unit", "melee") == (1, 1)
