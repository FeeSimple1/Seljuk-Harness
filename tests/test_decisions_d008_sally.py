"""D-008 (from Q-004, adjudicated 2026-07-06): the Sally resolves on the
per-Lord Battle machinery. Pins the 4.9.2 exceptions and the newly-exact
behaviors: one-Front-Lord Array with Size-capped Reserve advances, S6/R24/S3
Hold Events playable in a Sally, Withdraw-inside for losing Attackers with no
Service shift, Retreat + Service shifts for losing Besiegers."""
import pytest

from seljuk import scenarios as S, engine, battle, campaign
from seljuk import static_data as sd
from seljuk.battle import DecisionContext
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface
from seljuk.rng import DiceRoller
from tests.test_cross_game_combat import place, position


def _cmd(gs, lord, side, actions_n=4):
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = side
    gs.meta.active_lord = lord; gs.meta.active_card = lord; gs.meta.actions_remaining = actions_n
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1


def _sally_setup(loc="melitene", siege=2, second_sallier=None):
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    gs.locales[loc].siege_markers = siege
    aa = gs.lords["alp_arslan"]
    aa.mustered = True; aa.cylinder = loc; aa.besieged = True
    aa.forces = {"turkic_horse": 4, "ghulam_cavalry": 2}
    rom = gs.lords["romanos_diogenes"]
    rom.mustered = True; rom.cylinder = loc; rom.besieged = False; rom.side = "roman"
    rom.forces = {"tagmata": 3, "infantry": 2}
    if second_sallier:
        s2 = gs.lords[second_sallier]
        s2.mustered = True; s2.cylinder = loc; s2.besieged = True
        s2.forces = {"turkic_horse": 3}
    return gs, loc


def _muster_siege_lord(gs, lid, forces=None, *, inside=False):
    lord = place(gs, lid, carts=8, provender=8)
    lord.besieged = inside
    printed = sd.lord(lid)
    full = dict(printed["starting_forces"])
    for vassal in printed["vassals"]:
        for unit, count in vassal["forces"].items():
            full[unit] = full.get(unit, 0) + count
    lord.forces = full if forces is None else forces
    for vassal in lord.vassals:
        if not vassal.special_name:
            vassal.levied = True
            vassal.service_box = 10
    return lord


def _front_choices(gs, *, sally=False):
    _cmd(gs, "alp_arslan", "seljuk")
    _muster_siege_lord(gs, "alp_arslan", inside=sally)
    _muster_siege_lord(gs, "romanos_diogenes", {"tagmata": 2}, inside=not sally)
    _muster_siege_lord(gs, "chatatourios", {"infantry": 2}, inside=not sally)
    gs.locales["melitene"].siege_markers = 2 if sally else 1
    if sally:
        gs.locales["melitene"].conquered_side = "seljuk"
    return gs


@pytest.mark.parametrize("reorder", [False, True])
def test_storm_defender_chooses_initial_front_in_the_private_handoff(reorder):
    gs = _front_choices(position())
    if reorder:
        gs.lords = dict(reversed(list(gs.lords.items())))
    ui = CompactInterface(LLMSession(gs))
    row, = ui.actions(type="cmd_storm")["entries"]
    assert ui.details(row["id"])["help"]["combat"]["formation"]["your_role"] == "attacker"
    before = gs.to_json()
    ui.apply(row["id"])
    assert ui.viewer == "roman" and gs.to_json() == before
    response, = ui.actions(type="supply_inputs")["entries"]
    help_ = ui.details(response["id"])["help"]["formation"]
    assert help_["your_role"] == "defender" and help_["script"] == "storm_decisions"
    assert set(help_["your_lords"]) == {"romanos_diogenes", "chatatourios"}
    ui.apply(response["id"], parameters={"inputs": {
        "storm_decisions": [["initial_placement_defender", "chatatourios"]],
    }})
    storm = ui.gs.history[-1]["result"]["storm"]
    first, = [row for row in storm["decisions"] if row["type"] == "initial_placement_defender"]
    assert first["choice"] == "chatatourios"
    assert set(first["options"]) == {"romanos_diogenes", "chatatourios"}
    assert all(row["step"] != "def_horse_melee" for row in storm["strikes"])


def test_sally_defender_chooses_initial_front():
    gs = _front_choices(position(), sally=True)
    result = engine.apply_action(gs, {"type": "cmd_sally", "lord": "alp_arslan",
                                      "battle_decisions": {
        "roman": [["initial_placement_defender", "chatatourios"]],
        "seljuk": [["concede", True]],
    }})["sally"]
    first, = [row for row in result["decisions"] if row["type"] == "initial_placement_defender"]
    assert first["choice"] == "chatatourios"
    assert any(row.get("target") == "chatatourios" for row in result["strikes"])
    assert all(row.get("target") != "romanos_diogenes" for row in result["strikes"])


def test_storm_can_decline_optional_reserve_advance():
    gs = position()
    _cmd(gs, "alp_arslan", "seljuk")
    _muster_siege_lord(gs, "alp_arslan")
    _muster_siege_lord(gs, "artuk_beg")
    _muster_siege_lord(gs, "romanos_diogenes", inside=True)
    gs.locales["melitene"].siege_markers = 2
    storm = engine.apply_action(gs, {"type": "cmd_storm", "lord": "alp_arslan",
                                     "storm_decisions": {"seljuk": [["reserve_advance", None]]}})["storm"]
    assert storm["rounds"] == 2
    advances = [row for row in storm["decisions"] if row["type"] == "reserve_advance"]
    assert advances == [{"type": "reserve_advance", "options": ["artuk_beg", None], "choice": None}]
    assert all(row.get("target") != "artuk_beg" for row in storm["strikes"])


@pytest.mark.parametrize("storm", [False, True])
def test_reposition_forces_opposing_match_only_in_storm(storm):
    gs = position()
    for lid in ("alp_arslan", "artuk_beg", "romanos_diogenes", "chatatourios"):
        _muster_siege_lord(gs, lid)
    att = battle._Side(gs, ["alp_arslan", "artuk_beg"], "attacker")
    deff = battle._Side(gs, ["romanos_diogenes", "chatatourios"], "defender")
    ctx = DecisionContext({"seljuk": [["reserve_advance", "artuk_beg"]], "roman": [None]})
    battle._siege_array(att, deff, ctx)
    assert ctx.by_side["roman"].scripted == [None]
    battle._storm_reposition(gs, att, deff, 2, ctx, match_enemy=storm)
    assert att.front["left"] == "artuk_beg"
    assert deff.front["left"] == ("chatatourios" if storm else None)
    assert ctx.trace[-1]["options"] == (["chatatourios"] if storm else ["chatatourios", None])


@pytest.mark.parametrize("storm", [False, True])
def test_reposition_requires_replacement_when_front_routs_even_at_size_one(storm):
    gs = position()
    for lid in ("alp_arslan", "artuk_beg", "romanos_diogenes"):
        _muster_siege_lord(gs, lid)
    att = battle._Side(gs, ["alp_arslan", "artuk_beg"], "attacker")
    deff = battle._Side(gs, ["romanos_diogenes"], "defender")
    ctx = DecisionContext([["reserve_advance", None]])
    battle._siege_array(att, deff, ctx)
    front = gs.lords["alp_arslan"]
    front.routed = dict(front.forces)
    front.forces.clear()
    battle._storm_reposition(gs, att, deff, 1, ctx, match_enemy=storm)
    assert att.front_lords() == ["artuk_beg"] and att.front["center"] == "artuk_beg"
    assert ctx.trace[-1]["options"] == ["artuk_beg"]


# --- 4.9.2 ARRAY: one Front Lord each; Reserve advances capped by Size -------

def test_sally_array_reserve_advance_capped_by_stronghold_size():
    # Melitene is a Town (Size 2): the second Sallying Lord may advance from
    # Round 2 -- the trace records a reserve_advance for him.
    gs, loc = _sally_setup(second_sallier="artuk_beg")
    ctx = DecisionContext()
    r = battle.resolve_sally(gs, ["alp_arslan", "artuk_beg"], ["romanos_diogenes"],
                             loc, ctx, DiceRoller(3))
    assert r["rounds"] > 1
    assert any(t["type"] == "reserve_advance" and t["choice"] == "artuk_beg"
               for t in r["decisions"]), r["decisions"]
    # At a Size-1 Fort the second Lord can never advance.
    gs2 = S.load_scenario("emperor_and_the_lion", seed=3)
    fort = "tephrike"
    gs2.locales[fort].conquered_side = "seljuk"   # Seljuk-held Fort under Roman siege
    gs2.locales[fort].siege_markers = 1
    aa = gs2.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = fort; aa.besieged = True
    aa.forces = {"ghulam_cavalry": 8}      # durable: the Front never empties, so the
    ab = gs2.lords["artuk_beg"]; ab.mustered = True; ab.cylinder = fort; ab.besieged = True
    ab.forces = {"turkic_horse": 3}        # Size-1 cap alone governs the advance
    rom = gs2.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = fort
    rom.besieged = False; rom.forces = {"tagmata": 3}
    ctx2 = DecisionContext()
    r2 = battle.resolve_sally(gs2, ["alp_arslan", "artuk_beg"], ["romanos_diogenes"],
                              fort, ctx2, DiceRoller(3))
    assert not any(t["type"] == "reserve_advance" and t["choice"] == "artuk_beg"
                   for t in r2["decisions"]), r2["decisions"]


# --- D-008: S6 / R24 Hold Events now play in a Sally -------------------------

def test_sally_consumes_command_confusion_s6():
    gs, loc = _sally_setup()
    gs.seljuk.held_events = ["S6"]
    _cmd(gs, "alp_arslan", "seljuk")
    r = engine.apply_action(gs, {"type": "cmd_sally", "lord": "alp_arslan",
                                 "battle_events": {"seljuk": [{"card": "S6", "lord": "romanos_diogenes"}]}})
    assert r["ok"]
    assert "S6" not in gs.seljuk.held_events and "S6" in gs.seljuk.draw_deck


def test_sally_consumes_cavalry_charge_r24():
    gs, loc = _sally_setup()
    gs.roman.held_events = ["R24"]
    _cmd(gs, "alp_arslan", "seljuk")
    r = engine.apply_action(gs, {"type": "cmd_sally", "lord": "alp_arslan",
                                 "battle_events": {"roman": [{"card": "R24", "lord": "romanos_diogenes"}]}})
    assert r["ok"]
    assert "R24" not in gs.roman.held_events and "R24" in gs.roman.draw_deck


def test_cmd_sally_menu_hints_full_battle_hold_set():
    gs, loc = _sally_setup()
    gs.roman.held_events = ["R24", "R21"]
    gs.seljuk.held_events = ["S6"]
    _cmd(gs, "alp_arslan", "seljuk")
    mv = next(m for m in campaign.command_menu(gs) if m["type"] == "cmd_sally")
    holds = mv["_battle_holds_available"]
    assert holds["defender"] == ["R21", "R24"]
    assert holds["attacker"] == ["S6"]


# --- 4.9.2 END: losing Attackers Withdraw inside; losing Besiegers Retreat ---

def test_sally_losing_attacker_withdraws_inside_no_service_shift():
    gs, loc = _sally_setup()
    aa = gs.lords["alp_arslan"]
    aa.assets.coin = 2; aa.assets.loot = 1; aa.assets.carts = 2; aa.assets.provender = 2
    sb_before = aa.service_box
    ctx = DecisionContext(scripted=[("concede", True)])   # Sallying side concedes
    r = battle.resolve_sally(gs, ["alp_arslan"], ["romanos_diogenes"], loc, ctx, DiceRoller(5))
    assert r["winner"] == "besiegers"
    fates = {e["lord"]: e["fate"] for e in r["ending"]["retreat"]}
    assert fates.get("alp_arslan") == "withdraw"          # back inside, NOT Retreat
    assert aa.besieged is True and aa.cylinder == loc
    assert aa.assets.coin == 2 and aa.assets.carts == 2   # Withdraw keeps Assets
    assert not any(e["lord"] == "alp_arslan" for e in r["ending"]["service"])
    assert aa.service_box == sb_before                    # no Service shift on Withdraw
    assert gs.locales[loc].siege_markers == 1             # RAID: all but one removed


def test_sally_losing_besiegers_retreat_with_service_shifts():
    gs, loc = _sally_setup()
    rom = gs.lords["romanos_diogenes"]
    sb_before = rom.service_box
    ctx = DecisionContext(scripted=[("concede", False), ("concede", True)])  # Besiegers concede
    r = battle.resolve_sally(gs, ["alp_arslan"], ["romanos_diogenes"], loc, ctx, DiceRoller(5))
    assert r["winner"] == "sally"
    assert gs.locales[loc].siege_markers == 0             # the Siege ends
    fates = {e["lord"]: e["fate"] for e in r["ending"]["retreat"]}
    if fates.get("romanos_diogenes") == "retreat":        # Retreat -> Service shift (4.8.3)
        sv = {e["lord"]: e for e in r["ending"]["service"]}
        assert "romanos_diogenes" in sv
        assert rom.service_box == max(0, sb_before - sv["romanos_diogenes"]["shift"])
        assert rom.cylinder != loc                        # actually left the Locale
    assert gs.lords["alp_arslan"].besieged is True        # victors return inside


# --- Relief Sally (4.8.1): losing Sallying Lords also Withdraw inside --------

def test_relief_sally_losing_salliers_withdraw_inside_481():
    # "If Attackers lose, Withdraw Sallying Lords back into the Stronghold
    #  (4.8.3)" -- Withdraw fate: Assets kept, no Service shift, back inside.
    gs = S.load_scenario("emperor_and_the_lion", seed=3)
    loc = "melitene"
    gs.locales[loc].siege_markers = 2
    # Besieged Seljuk Lord inside; Roman besieger outside; Seljuk relief force
    # approaches and stands -- the Besieged Lord joins the Attack (Relief Sally).
    inside = gs.lords["artuk_beg"]
    inside.mustered = True; inside.cylinder = loc; inside.besieged = True
    inside.forces = {"turkic_horse": 2}
    inside.assets.coin = 2; inside.assets.carts = 1; inside.assets.provender = 1
    sb_before = inside.service_box
    relief = gs.lords["alp_arslan"]
    relief.mustered = True; relief.cylinder = loc; relief.besieged = False
    relief.forces = {"turkic_horse": 3}
    rom = gs.lords["romanos_diogenes"]
    rom.mustered = True; rom.cylinder = loc; rom.besieged = False
    rom.forces = {"tagmata": 4, "infantry": 2}
    r = battle.begin_battle(gs, ["alp_arslan", "artuk_beg"], ["romanos_diogenes"], loc,
                            scripted=[("concede", True)],       # relieving side concedes
                            sallying={"artuk_beg"},
                            siegeworks=gs.locales[loc].siege_markers,
                            approach_origin="germanikeia")
    assert r["loser"] == "attacker"
    fates = {e["lord"]: e["fate"] for e in r["ending"]["retreat"]}
    assert fates.get("artuk_beg") == "withdraw", fates   # Sallier: back inside, not Retreat
    assert inside.besieged is True and inside.cylinder == loc
    assert inside.assets.coin == 2                       # Withdraw keeps Assets
    assert not any(e["lord"] == "artuk_beg" for e in r["ending"]["service"])
    assert inside.service_box == sb_before               # no Service shift on Withdraw
