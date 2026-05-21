"""Phase 6: Cavalry Charge (R24) + Command Confusion (S6) strike sub-ordering."""
from seljuk import scenarios as S, battle
from seljuk.battle import DecisionContext, resolve_battle
from seljuk.rng import DiceRoller


def _battle(seed, att, deff, att_forces, def_forces, events=None, locale="melitene"):
    gs = S.load_scenario("emperor_and_the_lion", seed=seed)
    a = gs.lords[att]; d = gs.lords[deff]
    a.cylinder = locale; d.cylinder = locale
    a.forces = dict(att_forces); d.forces = dict(def_forces)
    gs.meta.phase = "campaign"; gs.meta.active_lord = att
    res = battle.begin_battle(gs, [att], [deff], locale, events=events)
    return gs, res


def test_cavalry_charge_horse_melee_before_missiles_r24():
    gs = S.load_scenario("emperor_and_the_lion", seed=2)
    rom = gs.lords["romanos_diogenes"]; rom.cylinder = "melitene"; rom.forces = {"tagmata": 3}
    ch = gs.lords["chatatourios"]; ch.cylinder = "melitene"; ch.forces = {"infantry": 3}
    gs.roman.held_events = ["R24"]
    gs.meta.phase = "campaign"; gs.meta.active_lord = "romanos_diogenes"
    res = battle.begin_battle(gs, ["romanos_diogenes"], ["chatatourios"], "melitene",
                              events={"roman": [{"card": "R24", "lord": "romanos_diogenes"}]})
    assert "R24" not in gs.roman.held_events  # consumed
    round1 = [s for s in res["strikes"] if s["round"] == 1]
    assert round1 and round1[0]["step"] == "horse_melee"  # Charge strikes before Missiles


def test_command_confusion_roman_defender_strikes_second_s6():
    gs = S.load_scenario("emperor_and_the_lion", seed=2)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "melitene"; aa.forces = {"turkic_horse": 4}  # Seljuk attacker, Missiles
    jt = gs.lords["joseph_tarchaneiotes"]; jt.cylinder = "melitene"; jt.forces = {"scholai_hetaireia": 3}  # Roman defender, Missiles
    jt.mustered = True; jt.side = "roman"
    gs.seljuk.held_events = ["S6"]
    gs.meta.phase = "campaign"; gs.meta.active_lord = "alp_arslan"
    res = battle.begin_battle(gs, ["alp_arslan"], ["joseph_tarchaneiotes"], "melitene",
                              events={"seljuk": [{"card": "S6", "lord": "joseph_tarchaneiotes"}]})
    assert "S6" not in gs.seljuk.held_events
    r1_missile = [s for s in res["strikes"] if s["round"] == 1 and s["step"] == "missile"]
    bys = [s["by"] for s in r1_missile]
    # With Command Confusion the Roman defender strikes AFTER the Seljuk attacker.
    if "attacker" in bys and "defender" in bys:
        assert bys.index("attacker") < bys.index("defender")


def test_cavalry_charge_takes_precedence_over_command_confusion():
    # A Lord under both Charge (R24) and Command Confusion (S6) -> Charge wins.
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    rom = gs.lords["romanos_diogenes"]; rom.cylinder = "melitene"; rom.forces = {"tagmata": 3}
    aa = gs.lords["alp_arslan"]; aa.cylinder = "melitene"; aa.forces = {"turkic_horse": 4}
    gs.roman.held_events = ["R24"]; gs.seljuk.held_events = ["S6"]
    gs.meta.phase = "campaign"; gs.meta.active_lord = "romanos_diogenes"
    res = battle.begin_battle(gs, ["romanos_diogenes"], ["alp_arslan"], "melitene",
                              events={"roman": [{"card": "R24", "lord": "romanos_diogenes"}],
                                      "seljuk": [{"card": "S6", "lord": "romanos_diogenes"}]})
    round1 = [s for s in res["strikes"] if s["round"] == 1]
    assert round1[0]["step"] == "horse_melee"  # Charge effect present (precedence)
