"""Regression tests for the bug-review fixes (June 2026).

Each test pins a previously-latent bug that the existing suite did not cover.
"""
import pytest

from seljuk import scenarios as S
from seljuk import events as E
from seljuk import campaign
from seljuk import battle
from seljuk import actions as A
from seljuk import engine
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _r():
    return DiceRoller(seed=1)


# --- Fix 1: event-driven Wastage returns the Capability to the deck ----------

def test_event_wastage_returns_capability_to_deck():
    gs = _gs()
    aa = gs.lords["alp_arslan"]
    # Force the Capability branch: no excess Assets (all <= 1), two Capabilities.
    aa.assets.carts = aa.assets.provender = aa.assets.coin = aa.assets.loot = 0
    aa.capabilities = ["S4", "S6"]
    deck = gs.side_decks(aa.side).draw_deck
    deck_before = len(deck)
    assert E._wastage_once(gs, aa) is True
    assert len(aa.capabilities) == 1
    # The discarded Capability is back in the side's Arts of War deck (not lost).
    assert len(gs.side_decks(aa.side).draw_deck) == deck_before + 1
    assert gs.side_decks(aa.side).draw_deck[-1] in ("S4", "S6")


# --- Fix 2: Storm garrison missiles vs defending-Lord missiles resolve apart --

def test_storm_garrison_and_lord_missiles_resolved_separately():
    gs = _gs()
    att = battle._Side(gs, [], "attacker")
    deff = battle._Side(gs, [], "defender")
    # Attacker Lord present (a target for defending Hits) with an armored unit.
    aid = "alp_arslan"
    gs.lords[aid].mustered = True
    gs.lords[aid].forces = {"ghulam_cavalry": 4}
    att.front["center"] = aid
    # Defending Lord with his OWN Missile-capable unit (Tagmata x1/2 missile).
    did = next(lid for lid, l in gs.lords.items() if l.side == "roman")
    gs.lords[did].mustered = True
    gs.lords[did].forces = {"tagmata": 2}
    deff.front["center"] = did
    garrison = {"militia": 2}              # Garrison Missiles (x1/2 each)
    garrison_routed: dict[str, int] = {}
    log: list = []
    ctx = battle.DecisionContext()
    battle._storm_strike(gs, att, deff, garrison, garrison_routed,
                         walls=(1, 0), siege=0, round_no=1, ctx=ctx,
                         roller=_r(), log=log)
    steps = [e.get("step") for e in log]
    # The two defending-missile batches are emitted separately (garrison gets the
    # -1 Armor; the Lord's own missiles do not).
    assert "def_missile_garrison" in steps
    assert "def_missile_lord" in steps


# --- Fix 3: Strategic Objective only on a currently Seljuk-controlled hold ----

def _set_cta_roman(gs):
    gs.meta.phase = "levy"; gs.meta.subphase = "levy.call_to_arms"
    gs.meta.active_player = "roman"
    rom = gs.lords["romanos_diogenes"]
    rom.mustered = True
    rom.cylinder = "to_constantinople"
    gs.holding_boxes.constantinople_strategic_objectives_available = 1


def _a_seljuk_stronghold(gs):
    for lid in S.sd.all_locale_ids():
        loc = S.sd.locale(lid)
        if loc["allegiance"] == "seljuk" and loc.get("is_stronghold"):
            return lid
    raise AssertionError("no Seljuk stronghold in scenario")


def test_so_rejected_on_roman_conquered_seljuk_stronghold():
    gs = _gs()
    _set_cta_roman(gs)
    hold = _a_seljuk_stronghold(gs)
    gs.locales[hold].conquered_side = "roman"      # no longer Seljuk-controlled
    with pytest.raises(IllegalAction):
        A.h_cta_strategic_objective(
            gs, {"type": "cta_strategic_objective", "mode": "place", "target": hold}, _r())


def test_so_allowed_on_controlled_seljuk_stronghold():
    gs = _gs()
    _set_cta_roman(gs)
    hold = _a_seljuk_stronghold(gs)
    gs.locales[hold].conquered_side = None
    out = A.h_cta_strategic_objective(
        gs, {"type": "cta_strategic_objective", "mode": "place", "target": hold}, _r())
    assert out["ok"] is True
    assert gs.locales[hold].strategic_objective is True


# --- Fix R20: Armenian Resistance only if the Locale is Seljuk friendly -------

def test_r20_no_op_when_not_seljuk_friendly():
    gs = _gs()
    gs.locales["khliat"].conquered_side = "roman"   # already Roman -> not Seljuk friendly
    out = E._ev_armenian_resistance(gs, {"locale": "khliat"}, _r())
    assert out.get("no_op") is True


# --- Fix R22: no phantom disband when Ibn Khan is not Mustered ----------------

def test_r22_no_op_when_ibn_khan_not_mustered():
    gs = _gs()
    gs.lords["ibn_khan"].mustered = False
    out = E._ev_assassination(gs, {}, _r())
    assert out.get("no_op") is True
    assert "disbanded" not in out


# --- Fix S5: "if already marked" grants +1 Lordship instead of removing more --

def test_s5_already_marked_grants_lordship_not_themata():
    gs = _gs()
    gs.meta.asterisks_used.append("S5")
    seljuk_lord = next(lid for lid, l in gs.lords.items() if l.side == "seljuk")
    out = E._ev_siege_of_bari(gs, {"lord": seljuk_lord}, _r())
    assert out.get("already_marked") is True
    assert gs.lords[seljuk_lord].flags.get("lordship_persist") == 1
    # Survives the muster-segment reset and raises remaining Lordship.
    base = A.capabilities.lordship_rating(gs, seljuk_lord)
    A.reset_muster_segment(gs)
    assert A.lordship_remaining(gs, gs.lords[seljuk_lord]) == base + 1


# --- Fix Unity: Bounty VPs first remove Constantinople Roman markers ----------

def test_bounty_removes_roman_conquered_markers_first():
    gs = _gs()
    aa = gs.lords["alp_arslan"]   # at a Seat (Ani)
    aa.assets.loot = 3
    aa.assets.carts = 3
    gs.holding_boxes.constantinople_roman_vp_markers = 2
    gs.holding_boxes.mosul_baghdad_loot = 0
    campaign._bounty(gs)
    # 3 loot scored: first cancels the 2 Roman markers, remaining 1 banked.
    assert gs.holding_boxes.constantinople_roman_vp_markers == 0
    assert gs.holding_boxes.mosul_baghdad_loot == 1


def test_bounty_unchanged_when_no_roman_markers():
    gs = _gs()
    aa = gs.lords["alp_arslan"]
    aa.assets.loot = 3
    aa.assets.carts = 2
    campaign._bounty(gs)
    assert gs.holding_boxes.mosul_baghdad_loot == 2  # min(loot, carts), unchanged behavior
