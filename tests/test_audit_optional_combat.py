"""Optional Rules 6.3 (Simultaneous Horse Combat) and 6.4 (Deadlier Seljuk
Missiles). Both apply in Battle only (Storm uses its own strike path)."""
from seljuk import scenarios as S, battle
from seljuk.rng import DiceRoller


def _arena(opts):
    gs = S.load_scenario("emperor_and_the_lion", options=opts)
    att = battle._Side(gs, [], "attacker")
    deff = battle._Side(gs, [], "defender")
    A = "alp_arslan"
    gs.lords[A].mustered = True; gs.lords[A].side = "seljuk"
    att.front["center"] = A
    D = next(l for l, x in gs.lords.items() if x.side == "roman")
    gs.lords[D].mustered = True
    deff.front["center"] = D
    return gs, att, deff, A, D


def _strike(gs, att, deff, seed=3):
    log = []
    battle._strike_phase(gs, att, deff, {"attacker": False, "defender": False},
                         1, battle.DecisionContext(), DiceRoller(seed), log)
    return log


# --- 6.4 Deadlier Seljuk Missiles: Seljuk Missiles Strike first --------------

def test_64_seljuk_attacker_missiles_strike_first():
    gs, att, deff, A, D = _arena({"deadlier_seljuk_missiles": True})
    gs.lords[A].forces = {"turkic_horse": 4}     # Seljuk attacker, Missiles
    gs.lords[D].forces = {"tagmata": 4}          # Roman defender, Missiles
    order = [(e["step"], e["by"]) for e in _strike(gs, att, deff)]
    assert order[0] == ("missile", "attacker")   # Seljuk (attacker) first despite role


def test_64_off_defender_missiles_strike_first():
    gs, att, deff, A, D = _arena({})             # standard rules
    gs.lords[A].forces = {"turkic_horse": 4}
    gs.lords[D].forces = {"tagmata": 4}
    order = [(e["step"], e["by"]) for e in _strike(gs, att, deff)]
    assert order[0] == ("missile", "defender")   # normal: Defender fires first


# --- 6.3 Simultaneous Horse Melee -------------------------------------------

def test_63_melee_attacker_still_strikes_after_being_outpointed():
    gs, att, deff, A, D = _arena({"simultaneous_horse": "melee"})
    gs.lords[A].forces = {"norman_knights": 2}   # melee-only horse (no Missiles)
    gs.lords[D].forces = {"norman_knights": 6}   # heavy: would rout A if it fired first
    log = _strike(gs, att, deff, seed=2)
    # Simultaneous: the Attacker's Horse Melee is computed from the pre-Strike
    # state, so it Strikes even though the Defender's Hits would have routed it.
    assert any(e["step"] == "horse_melee" and e["by"] == "attacker" for e in log)
    assert sum(gs.lords[D].routed.values()) > 0


def test_63_off_defender_routs_attacker_before_it_strikes():
    gs, att, deff, A, D = _arena({})             # standard rules
    gs.lords[A].forces = {"norman_knights": 2}
    gs.lords[D].forces = {"norman_knights": 6}
    log = _strike(gs, att, deff, seed=2)
    # Defending Horse fires first and routs the Attacker's Horse; the Attacker
    # then has no Horse to Strike back -> Defender takes no routs.
    assert not any(e["step"] == "horse_melee" and e["by"] == "attacker" for e in log)
    assert sum(gs.lords[D].routed.values()) == 0


def test_63_missiles_choice_resolves_horse_missiles_simultaneously():
    # With "missiles", horse Missile pools of both sides are computed pre-strike;
    # the Attacker's Missiles appear even when out-pointed.
    gs, att, deff, A, D = _arena({"simultaneous_horse": "missiles"})
    gs.lords[A].forces = {"turkic_horse": 2}
    gs.lords[D].forces = {"tagmata": 8}
    log = _strike(gs, att, deff, seed=2)
    assert any(e["step"] == "missile" and e["by"] == "attacker" for e in log)
