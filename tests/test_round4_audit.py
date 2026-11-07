"""Round 4 rules and player-facing combat regressions."""
import json

import pytest

from seljuk import battle, campaign, engine, map as gmap, render
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.state import IllegalAction
from tests.test_cross_game_avoid_wastage import avoid_action, avoid_position
from tests.test_cross_game_combat import place, position


def constructed_fort():
    gs = position()
    roman = place(gs, "romanos_diogenes", "to_constantinople")
    roman.capabilities = ["R1"]
    gs.meta.active_player = "roman"
    gs.meta.active_card = gs.meta.active_lord = roman.id
    engine.apply_action(gs, {"type": "cmd_fort", "lord": roman.id, "target": "larisa"})
    attacker = place(gs, "alp_arslan", "larisa")
    attacker.forces = {"ghulam_cavalry": 4, "infantry": 4}
    gs.meta.active_player = "seljuk"
    gs.meta.active_card = gs.meta.active_lord = attacker.id
    gs.meta.actions_remaining = gs.meta.notes["card_full_actions"] = 3
    gs.locales["larisa"].siege_markers = 3
    return gs, attacker


def test_constructed_fort_surrender_and_themata_use_fort_size():
    gs, attacker = constructed_fort()
    result = engine.apply_action(gs, {"type": "cmd_siege", "lord": attacker.id})
    assert len(result["surrender_roll"]) == 1
    assert result["threshold"] == 3

    gs, attacker = constructed_fort()
    gs.locales["larisa"].siege_markers = 0
    attacker.cylinder = "melitene"
    engine.apply_action(gs, {"type": "cmd_march", "lord": attacker.id, "to": "larisa"})
    engine.apply_action(gs, {"type": "besiege_bypass", "choice": "besiege"})
    ui = CompactInterface(LLMSession(gs))
    row = ui.actions(type="assign_themata_defenders")["entries"][0]
    assert ui.details(row["id"])["help"]["max_markers"] == 1
    ui.apply(row["id"], parameters={"markers": [0]})
    assert len(ui.gs.locales["larisa"].themata_defending) == 1


@pytest.mark.parametrize("sack", ["conquer", "ruin"])
def test_constructed_fort_sack_awards_spoils_and_removes_marker(sack):
    gs, attacker = constructed_fort()
    result = engine.apply_action(gs, {"type": "cmd_storm", "lord": attacker.id,
                                      "storm_decisions": [["sack_choice", sack]]})["storm"]
    assert result["winner"] == "attacker"
    assert result["sack"]["spoils"] == {"coin": 1, "loot": 0, "provender": 1}
    locale = gs.locales["larisa"]
    assert not locale.fort_marker
    assert locale.ruins == (sack == "ruin")
    assert not campaign._is_stronghold(gs, "larisa")


@pytest.mark.parametrize(("locale", "side"), [("hama", "roman"), ("aleppo", "roman"), ("aleppo", "seljuk")])
@pytest.mark.parametrize("approach", [True, False])
def test_fatimid_withdrawal_depends_on_side(locale, side, approach):
    gs = position()
    origin = gmap.ways_from(locale)[0]["to"]
    attacker, defender = "alp_arslan", "chatatourios"
    gs.locales[locale].conquered_side = None
    gs.locales[locale].conquered_count = 0
    if side == "seljuk":
        attacker, defender = defender, attacker
        gs.locales[locale].conquered_side = "seljuk"
        gs.locales[locale].conquered_count = 3
    placed = place(gs, attacker, origin)
    lord = place(gs, defender, locale)
    placed.forces = lord.forces = {"infantry": 4}
    gs.meta.active_player = placed.side
    gs.meta.active_lord = gs.meta.active_card = placed.id
    engine.apply_action(gs, {"type": "cmd_march", "lord": attacker, "to": locale})
    action = {"type": "respond_approach",
              "choices": {defender: {"action": "withdraw" if approach else "stand"}}}
    if not approach:
        action["battle_decisions"] = {placed.side: [["concede", False]],
                                      side: [["concede", True], ["retreat", "withdraw"]]}
    if approach and side == "roman":
        with pytest.raises(IllegalAction, match=f"no_withdraw_{locale}"):
            engine.apply_action(gs, action)
        ui = CompactInterface(LLMSession(gs))
        row = ui.actions(type="respond_approach")["entries"][0]
        assert {"action": "withdraw"} not in ui.details(row["id"])["help"]["choices"][defender]
    else:
        result = engine.apply_action(gs, action)
        assert lord.besieged == (side == "seljuk")
        if not approach:
            fates = result["battle"]["ending"]["retreat"]
            assert ({"lord": defender, "fate": "withdraw"} in fates) == (side == "seljuk")


def test_losing_owner_can_choose_removal_instead_of_withdrawal():
    gs, first, _, attacker = avoid_position(0, 0, 0, 0)
    gs.meta.pending[0]["defenders"] = [first.id]
    first.forces = attacker.forces = {"infantry": 4}
    first.assets.coin = 2
    action = {"type": "respond_approach", "choices": {first.id: {"action": "stand"}},
              "battle_decisions": {"seljuk": [["concede", False]],
                                   "roman": [["concede", True], ["retreat", "removed"]]}}
    result = engine.apply_action(gs, action)["battle"]
    assert result["ending"]["retreat"] == [{"lord": first.id, "fate": "removed"}]
    assert first.id in result["ending"]["removed"] and not first.mustered
    assert attacker.assets.coin == 2


@pytest.mark.parametrize("mode", ["avoid", "retreat"])
def test_shared_carts_owner_elects_which_lord_keeps_food(mode):
    gs, first, second, attacker = avoid_position(2, 2, 2, 0)
    before = gs.to_json()
    if mode == "avoid":
        action = avoid_action()
        invalid = {**action, "avoid_keep_provender": {first.id: 1, second.id: 2}}
        action["avoid_keep_provender"] = {first.id: 0, second.id: 2}
    else:
        for lord in (first, second, attacker):
            lord.forces = {"infantry": 4}
        before = gs.to_json()
        action = {"type": "respond_approach",
                  "choices": {lord.id: {"action": "stand"} for lord in (first, second)}}
        roman = [["concede", True], *([["retreat", ["retreat", "larisa"]]] * 2)]
        action["battle_decisions"] = {"seljuk": [["concede", False]],
                                      "roman": [*roman, ["retreat_keep_provender", 0]]}
        invalid = {**action, "battle_decisions": {"seljuk": [["concede", False]],
                                                 "roman": [*roman, ["retreat_keep_provender", True]]}}
    with pytest.raises(IllegalAction, match="bad_.*_provender"):
        engine.apply_action(gs, invalid)
    assert gs.to_json() == before
    engine.apply_action(gs, action)
    assert first.cylinder == second.cylinder == "larisa"
    assert (first.assets.provender, second.assets.provender, attacker.assets.provender) == (0, 2, 2)
    assert (first.assets.carts, second.assets.carts) == (2, 0)


def test_hidden_mats_reveal_only_committed_combatants_and_resume(tmp_path):
    gs, defender, avoider, attacker = avoid_position(2, 2, 2, 0)
    for lord in (defender, attacker):
        lord.forces = {"infantry": 4}
    defender.forces["tagmata"] = 2
    attacker.forces["ghulam_cavalry"] = 2
    gs.meta.options["hidden_mats"] = True
    gs.seljuk.draw_deck.remove("S6")
    gs.seljuk.held_events.append("S6")
    ui = CompactInterface(LLMSession(gs))

    def forces(lord):
        return ui.inspect("lord", lord.id, full=True)["data"]["current"]["forces"]

    assert ui.owed == "roman" and forces(attacker) == "<hidden>"
    action = avoid_action()
    action["choices"][defender.id] = {"action": "stand"}
    before = gs.to_json()
    ui.apply(action, version=ui.version)
    assert ui.owed == "seljuk" and forces(defender) == defender.forces
    assert forces(avoider) == "<hidden>"
    assert ui.session.state("seljuk")["lords"][defender.id]["assets"]["provender"] == 2
    assert json.loads(render.verbose(ui.gs, viewing_side="seljuk"))["lords"][defender.id]["forces"] == defender.forces
    assert "2 tagmata" in render.lord_view(ui.gs, defender.id, viewing_side="seljuk")
    assert "2 tagmata" in ui.session.briefing("seljuk")
    assert "2 tagmata" in ui.overview()["briefing"]
    ui.apply({"type": "supply_inputs", "inputs": {"battle_decisions": [["concede", False]]}}, version=ui.version)
    assert ui.owed == "roman" and forces(attacker) == attacker.forces
    assert ui.session.state("roman")["seljuk"]["held_events"] == ["<hidden>"]
    assert ui.gs.to_json() == before
    saved = tmp_path / "revealed-combat.json"
    version = ui.version
    ui.save(saved)
    ui = CompactInterface.load(saved)
    assert ui.version == version and forces(attacker) == attacker.forces
    with pytest.raises(InterfaceError, match="field not owned"):
        ui.apply({"type": "supply_inputs", "inputs": {"sally_join": []}}, version=ui.version)
    ui.apply({"type": "supply_inputs", "inputs": {"battle_decisions": [["concede", True]]}}, version=version)
    result = ui.inspect("result", full=True)["data"]["combat_detail"]["battle"]
    assert result["conceder"] == "defender"
    assert not ui.gs._revealed_combat_lords
    assert ui.session.state("roman")["lords"][attacker.id]["forces"] == "<hidden>"


@pytest.mark.parametrize("kind", ["cmd_storm", "cmd_sally"])
def test_hidden_mats_reveal_for_committed_combat_commands(kind):
    gs = position()
    gs.meta.options["hidden_mats"] = True
    attacker = place(gs, "alp_arslan")
    defender = place(gs, "chatatourios")
    outsider = place(gs, "romanos_diogenes", "larisa")
    gs.locales["melitene"].siege_markers = 2
    gs.lords[attacker.id if kind == "cmd_sally" else defender.id].besieged = True
    ui = CompactInterface(LLMSession(gs))
    assert ui.session.state("roman")["lords"][attacker.id]["forces"] == "<hidden>"
    ui.apply({"type": kind, "lord": attacker.id}, version=ui.version)
    assert ui.owed == "roman"
    assert ui.session.state("roman")["lords"][attacker.id]["forces"] == attacker.forces
    ui.apply({"type": "decline_inputs"}, version=ui.version)
    assert ui.owed == "seljuk"
    assert ui.session.state("seljuk")["lords"][defender.id]["forces"] == defender.forces
    assert ui.session.state("seljuk")["lords"][outsider.id]["forces"] == "<hidden>"
    result = ui.apply({"type": "decline_inputs"}, version=ui.version)
    assert result["applied"] == kind
    assert not ui.gs._revealed_combat_lords
