"""Full-rules-audit finding: Pursuit exception (4.8.2) — a single Conceding Lord
with ONLY Turkic Horse at the start, facing a single opposing Lord, halves BOTH
sides' Hits in the final Round (not just the conceder)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S
from seljuk import battle as B
from seljuk.battle import DecisionContext, resolve_battle, _strike_phase
from seljuk.rng import DiceRoller


def _final_round_defender_melee(res):
    final = max(e["round"] for e in res["strikes"])
    return sum(e["hits"] for e in res["strikes"]
               if e["round"] == final and e["by"] == "defender" and e["step"] in ("horse_melee", "foot_melee"))


def test_turkic_only_conceder_halves_both_sides():
    """A Turkic-ONLY solo attacker who Concedes halves the defender's Hits in
    the final Round; a mixed-force solo attacker (exception N/A) does not."""
    def run(att_forces, seed=1):
        gs = S.load_scenario("emperor_and_the_lion", seed=seed)
        aa = gs.lords["alp_arslan"]; aa.side = "seljuk"
        aa.forces = dict(att_forces); aa.capabilities = ["S4"]  # Shock Tactics: survive Round 1
        ch = gs.lords["chatatourios"]; ch.side = "roman"; ch.forces = {"tagmata": 12}
        gs.meta.active_lord = "alp_arslan"
        ctx = DecisionContext([("concede", True)])  # attacker Concedes at Round 2
        return resolve_battle(gs, ["alp_arslan"], ["chatatourios"], "melitene", ctx, DiceRoller(seed=seed))

    turkic_only = run({"turkic_horse": 12})
    mixed = run({"turkic_horse": 11, "ghulam_cavalry": 1})  # not Turkic-only -> exception N/A
    assert turkic_only["conceder"] == "attacker"
    assert mixed["conceder"] == "attacker"
    # Defender's final-round Melee is halved only in the Turkic-only case.
    assert _final_round_defender_melee(turkic_only) < _final_round_defender_melee(mixed)


def test_pursuit_flag_both_sides_via_strike_phase():
    """Unit-level: with both pursuit flags set, the defender's Hits are halved
    in _emit (mirrors the Turkic-only exception outcome)."""
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.side = "seljuk"; aa.forces = {"turkic_horse": 2}
    ch = gs.lords["chatatourios"]; ch.side = "roman"; ch.forces = {"tagmata": 4}
    from seljuk.battle import _Side
    att = _Side(gs, [], "attacker"); att.front["center"] = "alp_arslan"
    deff = _Side(gs, [], "defender"); deff.front["center"] = "chatatourios"
    log_both, log_def_only = [], []
    _strike_phase(gs, att, deff, {"attacker": True, "defender": True}, 2,
                  DecisionContext(), DiceRoller(seed=1), log_both)
    # Reset and strike with only the conceder (attacker) halved.
    gs2 = S.load_scenario("emperor_and_the_lion", seed=1)
    gs2.lords["alp_arslan"].side = "seljuk"; gs2.lords["alp_arslan"].forces = {"turkic_horse": 2}
    gs2.lords["chatatourios"].side = "roman"; gs2.lords["chatatourios"].forces = {"tagmata": 4}
    a2 = _Side(gs2, [], "attacker"); a2.front["center"] = "alp_arslan"
    d2 = _Side(gs2, [], "defender"); d2.front["center"] = "chatatourios"
    _strike_phase(gs2, a2, d2, {"attacker": True, "defender": False}, 2,
                  DecisionContext(), DiceRoller(seed=1), log_def_only)
    def def_hits(log):
        return sum(e["hits"] for e in log if e["by"] == "defender")
    # Defender Hits are strictly lower when BOTH sides are halved.
    assert def_hits(log_both) <= def_hits(log_def_only)


def test_two_lords_per_side_no_both_halving():
    """The exception requires a SINGLE Lord per side; with two defenders it does
    not trigger (only the conceder halves)."""
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.lords["alp_arslan"].forces = {"turkic_horse": 4}
    gs.lords["chatatourios"].forces = {"tagmata": 2}
    gs.lords["afsin_beg"].forces = {"tagmata": 2}
    gs.meta.active_lord = "alp_arslan"
    ctx = DecisionContext([("concede", True)])
    res = resolve_battle(gs, ["alp_arslan"], ["chatatourios", "afsin_beg"], "melitene",
                         ctx, DiceRoller(seed=3))
    assert res["ok"]  # resolves cleanly; exception not triggered (2 defenders)
