"""4.8.2 APPLY HITS TO LORDS: when the target Lord D is Struck only by the Lord
directly opposite him (no Enemy Flanks D) and the receiving side has a Flanking
Lord F whose Flank-Strike falls on that same opposing Lord, the receiving Player
may route the Hits onto F instead of D."""
from seljuk import scenarios as S, battle
from seljuk.rng import DiceRoller


def _arena():
    gs = S.load_scenario("emperor_and_the_lion")
    att = battle._Side(gs, [], "attacker")
    deff = battle._Side(gs, [], "defender")
    Z = "alp_arslan"          # attacker, center, Missiles
    gs.lords[Z].mustered = True; gs.lords[Z].forces = {"turkic_horse": 4}  # 4 Missile Hits
    att.front["center"] = Z
    # Defender: D directly opposite Z at center; F flanking at left (no enemy left).
    D = next(l for l, x in gs.lords.items() if x.side == "roman")
    F = next(l for l, x in gs.lords.items() if x.side == "roman" and l != D)
    for lid in (D, F):
        gs.lords[lid].mustered = True; gs.lords[lid].forces = {"infantry": 4}
    deff.front["center"] = D
    deff.front["left"] = F
    return gs, att, deff, Z, D, F


def _routed(gs, lid):
    return sum(gs.lords[lid].routed.values())


def test_receiver_may_route_hits_to_flanking_lord():
    gs, att, deff, Z, D, F = _arena()
    ctx = battle.DecisionContext(scripted=[("flank_absorb", F)])
    battle._resolve_step(gs, "missile", att, deff, "attacker", {}, 1, ctx, DiceRoller(1), [])
    assert any(t["type"] == "flank_absorb" for t in ctx.trace)   # the choice was offered
    assert _routed(gs, F) > 0 and _routed(gs, D) == 0            # F absorbed; D untouched


def test_default_keeps_hits_on_directly_opposed_lord():
    gs, att, deff, Z, D, F = _arena()
    ctx = battle.DecisionContext()    # no script -> first option (D) keeps the Hits
    battle._resolve_step(gs, "missile", att, deff, "attacker", {}, 1, ctx, DiceRoller(1), [])
    assert _routed(gs, D) > 0 and _routed(gs, F) == 0


def test_no_choice_when_an_enemy_also_flanks_the_target():
    gs, att, deff, Z, D, F = _arena()
    # Add a second attacker at right who Flanks D (D becomes Flanked by an enemy):
    Z2 = "afsin_beg"
    gs.lords[Z2].mustered = True; gs.lords[Z2].forces = {"turkic_horse": 2}
    att.front["right"] = Z2           # right has no opposite defender -> Z2 Flanks, hits D
    ctx = battle.DecisionContext(scripted=[("flank_absorb", F)])
    battle._resolve_step(gs, "missile", att, deff, "attacker", {}, 1, ctx, DiceRoller(1), [])
    # An Enemy Flanks the target -> no absorb choice is offered.
    assert not any(t["type"] == "flank_absorb" for t in ctx.trace)
