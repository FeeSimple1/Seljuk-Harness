"""Traceability tests pinning the Seljuk Errata & Clarifications (Jan 31 2026).

Each test corresponds to one erratum/clarification; see ERRATA_AUDIT.md for the
full mapping. Items already covered elsewhere (Varangian Round-1, Shock Tactics
ceil(n/2), Lamellar/Evade) are noted there and not duplicated here.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, static_data as sd, map as gmap
from seljuk import actions, campaign, engine
from seljuk.battle import DecisionContext, _lord_fate
from seljuk.state import IllegalAction


# --- Errata: Strategic Objective requires the Roman Commander in Constantinople
def _drive_to_cta(scenario="emperor_and_the_lion", seed=1):
    gs = S.load_scenario(scenario, seed=seed)
    gs.meta.notes["first_aow_done"] = True
    engine.start_levy(gs)
    for _ in range(4):
        engine.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.subphase == "levy.call_to_arms"
    return gs


def test_strategic_objective_unavailable_when_commander_not_in_constantinople():
    gs = _drive_to_cta()
    engine.apply_action(gs, {"type": "pass_step"})  # Seljuk declines -> Roman CtA
    # Move both potential commanders out of Constantinople.
    for cid in ("romanos_diogenes", "manuel_komnenos"):
        if cid in gs.lords:
            gs.lords[cid].cylinder = "ankyra"
    moves = actions.enumerate_call_to_arms(gs)
    assert not any(m["type"] == "cta_strategic_objective" for m in moves)
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "cta_strategic_objective", "mode": "take"})


# --- Errata: Winter Bounty path blocked by enemy Lords (4.7.6)
def test_winter_bounty_path_blocked_by_enemy_lord():
    gs = S.load_scenario("emperor_and_the_lion")
    # Pick a wilderness/friendly locale that is normally traversable.
    loc = next(l for l in sd.all_locale_ids()
               if sd.locale(l)["type"] in ("wilderness", "unfortified_settlement"))
    assert campaign._bounty_traversable(gs, loc) is True
    # Park a Roman (enemy) Lord there: the Seljuk Bounty path may no longer pass.
    rom = gs.lords["romanos_diogenes"]
    rom.side = "roman"; rom.mustered = True; rom.cylinder = loc
    assert campaign._bounty_traversable(gs, loc) is False


# --- Errata: 1071 (Manzikert) PSILOI is an ALL Capability under the board edge
def test_manzikert_psiloi_under_board_edge_not_on_andronikos():
    gs = S.load_scenario("manzikert")
    assert "R25" in gs.roman.capabilities_in_play          # R25 = Psiloi (ALL), board edge
    assert "R25" not in gs.lords["andronikos_doukas"].capabilities
    assert "R13" in gs.lords["andronikos_doukas"].capabilities  # R13 = Syndosis (this-Lord)
    assert sd.card("R25")["capability"]["name"] == "Psiloi"
    assert sd.card("R25")["capability"]["heraldry"] == "ALL"


# --- Errata: Attacker cannot Withdraw into the battle site (only Defender/Sallying)
def test_attacker_cannot_withdraw_into_battle_site_defender_can():
    locale = "ankyra"  # Roman-friendly Town with a free neighbor
    # Defender at a friendly Stronghold WITHDRAWS (default ctx picks "withdraw").
    gs = S.load_scenario("emperor_and_the_lion")
    d = gs.lords["chatatourios"]; d.side = "roman"; d.mustered = True; d.cylinder = locale
    fate_def = _lord_fate(gs, d, "defender", locale, conceded=False, ctx=DecisionContext())
    assert fate_def == "withdraw" and d.besieged is True

    # Attacker at the SAME friendly Stronghold may NOT withdraw -> Retreats instead.
    gs2 = S.load_scenario("emperor_and_the_lion")
    a = gs2.lords["chatatourios"]; a.side = "roman"; a.mustered = True; a.cylinder = locale
    fate_att = _lord_fate(gs2, a, "attacker", locale, conceded=False, ctx=DecisionContext())
    assert fate_att != "withdraw"
    assert a.besieged is False
    assert a.cylinder != locale  # left the battle site


# --- Clarification: Themata on the Roman Commander's mat return to their Thema box on disband
def test_themata_return_to_box_when_commander_disbands():
    gs = S.load_scenario("emperor_and_the_lion")
    man = gs.lords["manuel_komnenos"]
    # Put a Themata marker on the Commander's mat, taken from Charsianon.
    thema = "Charsianon"
    before = len(gs.themata[thema])
    marker = gs.themata[thema].pop()
    marker.home_thema = thema           # recorded when Levied onto the mat (3.4.5)
    man.themata_on_mat.append(marker)
    assert len(gs.themata[thema]) == before - 1
    actions._return_themata_home(gs, man)
    assert man.themata_on_mat == []
    assert len(gs.themata[thema]) == before  # returned home
