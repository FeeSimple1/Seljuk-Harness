"""4.9.2 Sally follows Battle rules (4.8) -- Concede is not excepted. So a Sally
Concede resolves the final Round with the Conceding side's Hits halved (Pursuit,
4.8.3-.4), then ends with that side as the loser. Both the Sallying side
(Attacker) and the Besiegers (Defender) may Concede, in that order (4.8.3)."""
from seljuk import scenarios as S, battle
from seljuk.rng import DiceRoller


def _setup(sal_forces=None, bes_forces=None):
    gs = S.load_scenario("emperor_and_the_lion")
    loc = "melitene"
    gs.locales[loc].siege_markers = 2
    sal, bes = "alp_arslan", "chatatourios"
    s = gs.lords[sal]; s.mustered = True; s.cylinder = loc; s.besieged = True
    s.forces = sal_forces or {"ghulam_cavalry": 8}
    b = gs.lords[bes]; b.mustered = True; b.cylinder = loc; b.side = "roman"
    b.forces = bes_forces or {"tagmata": 8}
    return gs, loc, sal, bes


def test_sally_attacker_concede_resolves_final_halved_round():
    gs, loc, sal, bes = _setup()
    ctx = battle.DecisionContext(scripted=[("concede", True)])  # Sallying side concedes
    r = battle.resolve_sally(gs, [sal], [bes], loc, ctx, DiceRoller(1))
    assert r["conceder"] == "attacker"
    assert r["winner"] == "besiegers"          # the conceding Sallying side loses
    assert r["rounds"] == 2
    assert any(e.get("round") == 2 for e in r["strikes"]), r["strikes"]


def test_sally_defender_besiegers_concede_ends_siege():
    gs, loc, sal, bes = _setup()
    # Attacker declines, then the Besiegers (Defender) concede -> Besiegers lose.
    ctx = battle.DecisionContext(scripted=[("concede", False), ("concede", True)])
    r = battle.resolve_sally(gs, [sal], [bes], loc, ctx, DiceRoller(1))
    assert r["conceder"] == "defender"
    assert r["winner"] == "sally"              # besiegers conceded -> Sally succeeds
    assert gs.locales[loc].siege_markers == 0  # losing Besiegers Retreat; Siege ends
    assert any(e.get("round") == 2 for e in r["strikes"])


def test_sally_turkic_only_concede_halves_both_sides():
    # 4.8.2: a single Conceding Lord with ONLY Turkic Horse, facing a single
    # opposing Lord, halves BOTH sides' Hits in the final Round.
    gs, loc, sal, bes = _setup(sal_forces={"turkic_horse": 8}, bes_forces={"tagmata": 8})
    ctx = battle.DecisionContext(scripted=[("concede", True)])
    r = battle.resolve_sally(gs, [sal], [bes], loc, ctx, DiceRoller(1))
    assert r["conceder"] == "attacker"
    assert r["rounds"] == 2  # resolves the final (mutually-halved) Round, then ends


def test_sally_no_concede_runs_normally():
    gs, loc, sal, bes = _setup()
    ctx = battle.DecisionContext()  # default: neither side concedes
    r = battle.resolve_sally(gs, [sal], [bes], loc, ctx, DiceRoller(1))
    assert r["conceder"] is None
    assert r["winner"] in ("besiegers", "sally")


# --- Sally uses Battle strike order + Battle capabilities (4.9.2) ------------

def test_sally_horse_foot_split_and_capabilities():
    gs = S.load_scenario("emperor_and_the_lion")
    side = battle._Side(gs, [], "attacker")
    lid = "alp_arslan"
    L = gs.lords[lid]; L.mustered = True
    L.forces = {"ghulam_cavalry": 2, "infantry": 2}
    side.front["center"] = lid
    # Battle order splits melee: horse-melee step counts only Horse, foot only Foot.
    assert battle._side_step_caps(gs, side, "horse_melee", 1) == (2.0, 0.0)
    assert battle._side_step_caps(gs, side, "foot_melee", 1) == (2.0, 0.0)
    # Bardoukia (R21): Tagmata Melee becomes anti-armor -- a Battle Capability that
    # must apply in a Sally (a Sally is a Battle).
    L.forces = {"tagmata": 2}; L.capabilities = ["R21"]
    assert battle._side_step_caps(gs, side, "horse_melee", 1) == (0.0, 2.0)
    # Javelins (S11): Infantry gain x1 Missiles in a Battle (none without it).
    L.forces = {"infantry": 3}; L.capabilities = []
    assert battle._side_step_caps(gs, side, "missile", 1)[0] == 0.0
    L.capabilities = ["S11"]
    assert battle._side_step_caps(gs, side, "missile", 1)[0] == 3.0
