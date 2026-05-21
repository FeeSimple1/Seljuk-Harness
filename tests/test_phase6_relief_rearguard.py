"""Phase 6: full Relief Sally rearguard-row array (4.8.1, Reposition 1.2.2 B).

Sallying Attackers form a row behind the Defenders and Strike the Defender's
Rearguard row (Reserve Lords positioned opposite them); if no Rearguard, they
Flank the Front Defenders. Siegeworks reduce Sallying Strikes only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S
from seljuk import battle


def _setup(siegeworks=0, with_rearguard=True):
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    # Attackers (Seljuk): alp_arslan relieves at Front; afsin_beg Sallies.
    gs.lords["alp_arslan"].forces = {"turkic_horse": 3}
    gs.lords["afsin_beg"].forces = {"turkic_horse": 4}
    # Defenders (Roman): romanos at Front; chatatourios as Rearguard (Reserve).
    gs.lords["romanos_diogenes"].forces = {"infantry": 4}
    defenders = ["romanos_diogenes"]
    if with_rearguard:
        gs.lords["chatatourios"].forces = {"infantry": 4}
        defenders.append("chatatourios")
    gs.meta.active_lord = "alp_arslan"
    res = battle.begin_battle(
        gs, ["alp_arslan", "afsin_beg"], defenders, "antioch",
        sallying={"afsin_beg"}, siegeworks=siegeworks,
    )
    return gs, res


def test_sallying_lord_strikes_rearguard_not_front():
    gs, res = _setup(siegeworks=0, with_rearguard=True)
    sallying_strikes = [s for s in res["strikes"] if s["by"] == "attacker" and s.get("sallying")]
    # The Sallying Lord engages the Rearguard (chatatourios), not the Front Lord.
    assert any(s["target"] == "chatatourios" for s in sallying_strikes)
    assert all(s["target"] != "romanos_diogenes" for s in sallying_strikes
               if s["round"] == 1)
    # The Front (relieving) attacker engages the Front Defender.
    front_strikes = [s for s in res["strikes"]
                     if s["by"] == "attacker" and not s.get("sallying") and s["round"] == 1]
    assert any(s["target"] == "romanos_diogenes" for s in front_strikes)


def test_rearguard_strikes_back_at_sallying_lord():
    gs, res = _setup(siegeworks=0, with_rearguard=True)
    def_strikes = [s for s in res["strikes"] if s["by"] == "defender" and s["round"] == 1]
    # The Rearguard Defender (chatatourios) Strikes the Sallying Lord (afsin_beg).
    assert any(s["target"] == "afsin_beg" for s in def_strikes)


def test_no_rearguard_sallying_lord_flanks_front():
    gs, res = _setup(siegeworks=0, with_rearguard=False)
    sallying_strikes = [s for s in res["strikes"] if s["by"] == "attacker" and s.get("sallying")]
    # With no Rearguard, the Sallying Lord Flanks the Front Defender.
    assert any(s["target"] == "romanos_diogenes" for s in sallying_strikes)


def test_siegeworks_reduce_only_sallying_strikes():
    # High Siegeworks (Walls 1-6 always cancel) should spare the Rearguard from
    # the Sallying Lord's Round-1 Hits; zero Siegeworks should not.
    _, res0 = _setup(siegeworks=0, with_rearguard=True)
    _, res6 = _setup(siegeworks=6, with_rearguard=True)
    def round1_rear_hits(res):
        return sum(s["hits"] for s in res["strikes"]
                   if s.get("sallying") and s["target"] == "chatatourios" and s["round"] == 1)
    assert round1_rear_hits(res0) > 0
    assert round1_rear_hits(res6) == 0
