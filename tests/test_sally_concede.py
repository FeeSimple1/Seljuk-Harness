"""4.9.2 Sally follows Battle rules (Concede not excepted): a Concede still
resolves the final Round with the Conceding (Sallying) side's Hits halved
(Pursuit), unlike a Storm Concede which ends immediately (4.9.1)."""
from seljuk import scenarios as S, battle
from seljuk.rng import DiceRoller


def _setup():
    gs = S.load_scenario("emperor_and_the_lion")
    loc = "melitene"
    gs.locales[loc].siege_markers = 2
    sal, bes = "alp_arslan", "chatatourios"
    s = gs.lords[sal]; s.mustered = True; s.cylinder = loc; s.besieged = True
    s.forces = {"ghulam_cavalry": 8}
    b = gs.lords[bes]; b.mustered = True; b.cylinder = loc; b.side = "roman"
    b.forces = {"tagmata": 8}
    return gs, loc, sal, bes


def test_sally_concede_resolves_final_halved_round():
    gs, loc, sal, bes = _setup()
    ctx = battle.DecisionContext(scripted=[("concede", True)])
    r = battle.resolve_sally(gs, [sal], [bes], loc, ctx, DiceRoller(1))
    # The Sallying side concedes in Round 2 -> it is the loser.
    assert r["winner"] == "besiegers"
    assert r["rounds"] == 2
    # The conceding Round's strikes WERE resolved (not skipped as in a Storm).
    assert any(e.get("round") == 2 for e in r["strikes"]), r["strikes"]
    assert any(d["type"] == "concede" and d["choice"] is True for d in r["decisions"])


def test_sally_no_concede_runs_normally():
    # With no concede scripted, the default (don't concede) path is unaffected.
    gs, loc, sal, bes = _setup()
    ctx = battle.DecisionContext()
    r = battle.resolve_sally(gs, [sal], [bes], loc, ctx, DiceRoller(1))
    assert r["winner"] in ("besiegers", "sally")
    assert not any(d["type"] == "concede" and d["choice"] is True for d in r["decisions"])
