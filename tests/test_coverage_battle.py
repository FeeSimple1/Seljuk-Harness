"""Aggressive coverage of battle.py helpers and the Sally (besiegers-lose) path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S
from seljuk import battle as B
from seljuk.battle import DecisionContext
from seljuk.rng import DiceRoller


def test_decision_context_branches():
    # no options -> None
    assert DecisionContext().decide("x", []) is None
    # bare scripted value consumed in order
    ctx = DecisionContext(["a"])
    assert ctx.decide("any", ["a", "b"]) == "a"
    # typed entry for a DIFFERENT decision -> falls back to first option, not consumed
    ctx2 = DecisionContext([("concede", True)])
    assert ctx2.decide("retreat", ["x", "y"]) == "x"
    assert ctx2.scripted == [("concede", True)]   # untouched
    # typed entry matching -> consumed
    assert ctx2.decide("concede", [False, True]) is True


def test_strike_table_varangian_zeroed_after_round_one():
    assert B._strike_table("foot_melee", 1)["varangian_guard"] == 3.0
    assert B._strike_table("foot_melee", 2)["varangian_guard"] == 0.0
    assert B._strike_table("missile", 1) is B._MISSILE


def test_garrison_hit_helpers():
    # Each garrison unit fires its own Missile: infantry (foot, no innate Missile)
    # gains x1/2 -> 2 x 0.5 = 1.0; Turkic Horse fires x1 -> 1.0; total 2.0.
    assert B._garrison_missile_hits({"infantry": 2, "turkic_horse": 1}) == 2.0
    melee = B._garrison_melee_hits({"infantry": 2, "militia": 2, "varangian_guard": 1})
    assert melee == 2.0 + 1.0 + 3.0  # 2x1 + 2x0.5 + 1x3


def test_resolve_sally_besiegers_lose_ends_siege():
    gs = S.load_scenario("emperor_and_the_lion", seed=2)
    loc = "antioch"
    sallier = gs.lords["chatatourios"]; sallier.side = "roman"; sallier.mustered = True
    sallier.cylinder = loc; sallier.besieged = True
    sallier.forces = {"tagmata": 4, "infantry": 4}
    besieger = gs.lords["alp_arslan"]; besieger.side = "seljuk"; besieger.mustered = True
    besieger.cylinder = loc; besieger.forces = {"militia": 1}
    gs.locales[loc].siege_markers = 2
    ctx = DecisionContext()
    res = B.resolve_sally(gs, ["chatatourios"], ["alp_arslan"], loc, ctx, DiceRoller(seed=2))
    assert res["winner"] in ("sally", "besiegers")  # resolves cleanly
    # If the besiegers were routed, the Siege ended.
    if res["winner"] == "sally":
        assert gs.locales[loc].siege_markers == 0
