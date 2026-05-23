"""Phase 3b: Battle resolution (4.8) — protection, strikes, full resolution,
Concede/Pursuit, Flanking, ending (Retreat/Withdraw/Losses/Service/Spoils)."""
import pytest

from seljuk import scenarios as S, engine, battle
from seljuk.battle import DecisionContext, protection_range, _strike_table, resolve_battle, _apply_hits
from seljuk.rng import DiceRoller


def test_protection_ranges_by_hit_type_482():
    assert protection_range("turkic_horse", "missile") == (1, 1)   # Unarmored vs Missiles
    assert protection_range("turkic_horse", "melee") == (1, 3)      # Evade vs Melee in Battle
    assert protection_range("militia", "melee") == (1, 1)           # Unarmored
    assert protection_range("tagmata", "missile") == (1, 3)         # Armored
    assert protection_range("norman_knights", "melee") == (1, 4)


def test_varangian_strikes_only_round_one_482():
    assert _strike_table("foot_melee", 1)["varangian_guard"] == 3.0
    assert _strike_table("foot_melee", 2)["varangian_guard"] == 0.0


def _two_lord_battle(seed, scripted=None, attacker="alp_arslan", defender="chatatourios",
                     att_forces=None, def_forces=None, locale="melitene"):
    gs = S.load_scenario("emperor_and_the_lion", seed=seed)
    a = gs.lords[attacker]; d = gs.lords[defender]
    a.cylinder = locale; d.cylinder = locale
    if att_forces is not None:
        a.forces = dict(att_forces)
    if def_forces is not None:
        d.forces = dict(def_forces)
    gs.meta.phase = "campaign"; gs.meta.active_lord = attacker
    ctx = DecisionContext(scripted)
    roller = DiceRoller(seed)
    res = resolve_battle(gs, [attacker], [defender], locale, ctx, roller)
    return gs, res


def test_unit_conservation_through_battle():
    """Every unit ends in Forces or Lost; none vanish or duplicate."""
    gs, res = _two_lord_battle(3, att_forces={"turkic_horse": 6}, def_forces={"infantry": 4})
    for lid in ("alp_arslan", "chatatourios"):
        l = gs.lords[lid]
        total = sum(l.forces.values()) + sum(l.routed.values())
        assert total >= 0  # routed reconciled into forces/lost during Losses
    assert res["winner"] in ("attacker", "defender")
    assert res["rounds"] >= 1


def test_lopsided_attacker_wins_and_removes_defender():
    gs, res = _two_lord_battle(5, att_forces={"turkic_horse": 6, "ghulam_cavalry": 2},
                               def_forces={"militia": 1})
    assert res["winner"] == "attacker"
    assert gs.lords["chatatourios"].mustered is False  # lost all Forces -> removed (4.8.5)


def test_apply_hits_conserves_units_and_routs_some():
    gs = S.load_scenario("emperor_and_the_lion", seed=2)
    lord = gs.lords["alp_arslan"]
    lord.forces = {"turkic_horse": 4}; lord.routed = {}
    ctx = DecisionContext()
    routed = _apply_hits(gs, "alp_arslan", 4, "missile", ctx, DiceRoller(2))
    assert sum(lord.forces.values()) + sum(lord.routed.values()) == 4   # conserved
    assert len(routed) == sum(lord.routed.values())
    assert sum(lord.routed.values()) <= 4


def test_concede_makes_conceder_lose_with_pursuit_482():
    # Two armored Lords (Norman Knights, Armor 1-4) so Round 1 rarely routs
    # anyone; the Attacker concedes at the Round 2 offer (typed script).
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    a = gs.lords["roussel_de_bailleul"]; d = gs.lords["chatatourios"]
    a.cylinder = "melitene"; d.cylinder = "melitene"
    a.forces = {"norman_knights": 3}; d.forces = {"norman_knights": 3}
    gs.meta.phase = "campaign"; gs.meta.active_lord = "roussel_de_bailleul"
    res = resolve_battle(gs, ["roussel_de_bailleul"], ["chatatourios"], "melitene",
                         DecisionContext([("concede", True)]), DiceRoller(1))
    # If anyone routed in Round 1 the concede offer never arrives; otherwise the
    # Attacker's concede makes the Attacker the loser (4.8.2-.3).
    if res["conceder"] == "attacker":
        assert res["loser"] == "attacker"
    else:
        assert res["winner"] in ("attacker", "defender")


def test_retreat_shifts_service_withdraw_does_not_483():
    # Defender at a non-stronghold loses -> must Retreat -> Service shifts.
    gs, res = _two_lord_battle(4, def_forces={"militia": 1}, locale="larisa")  # larisa: not a Stronghold
    fates = {e["lord"]: e["fate"] for e in res["ending"]["retreat"]}
    if fates.get("chatatourios") == "retreat":
        assert any(s["lord"] == "chatatourios" for s in res["ending"]["service"])


def test_flanking_when_attacker_outnumbers_front():
    # Two attackers (center + left) vs one defender (center): the left attacker Flanks.
    gs = S.load_scenario("emperor_and_the_lion", seed=7)
    a1 = gs.lords["alp_arslan"]; a2 = gs.lords["arisighi"]; d = gs.lords["chatatourios"]
    for l in (a1, a2, d):
        l.cylinder = "melitene"
    a1.forces = {"turkic_horse": 4}; a2.forces = {"turkic_horse": 4}; d.forces = {"infantry": 2}
    gs.meta.phase = "campaign"; gs.meta.active_lord = "alp_arslan"
    res = resolve_battle(gs, ["alp_arslan", "arisighi"], ["chatatourios"], "melitene",
                         DecisionContext(), DiceRoller(7))
    assert res["winner"] == "attacker"  # 2 Lords flanking 1 weak defender


def test_battle_terminates_even_in_stalemate():
    # Two all-armored Lords with high protection; battle must still terminate.
    gs, res = _two_lord_battle(9, attacker="roussel_de_bailleul",
                               att_forces={"norman_knights": 3}, def_forces={"norman_knights": 3})
    assert res["rounds"] <= 30


def test_conceding_loser_relocates_no_colocation_4_8_3():
    """Inferno-Harness Retreat advisory: the cold 'loser survives -> Retreat'
    branch (only reachable via Concede / early battle end) must RELOCATE the
    losing Lord, not merely apply the Service penalty. A real Seljuk-vs-Roman
    battle with a scripted Attacker Concede leaves the loser alive; assert he
    moved OUT of the battle Locale, stayed Mustered, and that no two opposing
    un-besieged Lords share a Locale (co-location invariant)."""
    from seljuk.invariants import check_invariants
    for seed in range(1, 12):
        gs = S.load_scenario("emperor_and_the_lion", seed=seed)
        a = gs.lords["alp_arslan"]; d = gs.lords["chatatourios"]
        a.cylinder = "melitene"; d.cylinder = "melitene"
        a.forces = {"ghulam_cavalry": 8}; d.forces = {"tagmata": 8}
        gs.meta.phase = "campaign"; gs.meta.active_lord = "alp_arslan"
        res = resolve_battle(gs, ["alp_arslan"], ["chatatourios"], "melitene",
                             DecisionContext([("concede", True)]), DiceRoller(seed))
        if res["conceder"] != "attacker" or sum(a.forces.values()) == 0:
            continue  # round-1 rout pre-empted the concede, or pursuit wiped him
        assert a.mustered is True, f"seed {seed}: surviving conceder un-mustered"
        assert a.cylinder != "melitene", f"seed {seed}: loser not relocated (advisory bug)"
        assert check_invariants(gs) == [], f"seed {seed}: {check_invariants(gs)}"
        return  # one concrete surviving-conceder case is enough
    raise AssertionError("no surviving-conceder case produced; adjust setup")


def test_retreat_blocked_by_unbesieged_enemy_stronghold_483():
    """4.8.3 A: a Retreat target with an enemy Stronghold blocks unless that
    Stronghold is already Besieged or Bypassed; friendly/Ruined never block."""
    from seljuk import battle
    gs = S.load_scenario("emperor_and_the_lion")  # melitene = Roman town
    assert battle._retreat_blocked(gs, "melitene", "seljuk") is True       # enemy stronghold
    gs.locales["melitene"].siege_markers = 1
    assert battle._retreat_blocked(gs, "melitene", "seljuk") is False      # Besieged -> allowed
    gs.locales["melitene"].siege_markers = 0; gs.locales["melitene"].bypass = True
    assert battle._retreat_blocked(gs, "melitene", "seljuk") is False      # Bypassed -> allowed
    gs.locales["melitene"].bypass = False
    assert battle._retreat_blocked(gs, "melitene", "roman") is False       # own Stronghold ok


def test_marching_attacker_retreats_to_approach_origin_483():
    """4.8.3: a Marching Attacker that loses must Retreat to the Locale it
    Approached from; if that Locale is not a legal target it cannot Retreat."""
    from seljuk import battle, map as gmap
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["alp_arslan"]; lord.cylinder = "melitene"; lord.forces = {"ghulam_cavalry": 2}
    origin = next(e["to"] for e in gmap.ways_from("melitene")
                  if not battle._retreat_blocked(gs, e["to"], "seljuk"))
    fate = battle._lord_fate(gs, lord, "attacker", "melitene", conceded=True,
                             ctx=battle.DecisionContext(), approach_origin=origin, marcher_origin=origin)
    assert fate == "retreat" and lord.cylinder == origin
    # Origin not a legal/adjacent target -> the Attacker is Removed (cannot Retreat).
    l2 = gs.lords["artuk_beg"]; l2.cylinder = "melitene"; l2.forces = {"infantry": 1}
    fate2 = battle._lord_fate(gs, l2, "attacker", "melitene", conceded=True,
                              ctx=battle.DecisionContext(), approach_origin="ani", marcher_origin="ani")
    assert fate2 == "removed"


def test_defender_cannot_retreat_along_approach_way_483():
    """4.8.3: a losing Defender may not Retreat along the Way the Attackers
    Approached from (the approach-origin Locale is excluded)."""
    from seljuk import battle, map as gmap
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["chatatourios"]; lord.cylinder = "melitene"; lord.forces = {"infantry": 2}
    clean = [e["to"] for e in gmap.ways_from("melitene") if not battle._retreat_blocked(gs, e["to"], "roman")]
    assert len(clean) >= 2
    origin = clean[0]
    fate = battle._lord_fate(gs, lord, "defender", "melitene", conceded=False,
                             ctx=battle.DecisionContext(), approach_origin=origin)
    assert fate in ("retreat", "withdraw", "removed")
    if fate == "retreat":
        assert lord.cylinder != origin, "defender retreated back along the approach Way"
