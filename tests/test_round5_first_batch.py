"""Round 5 Local Scouts and Stronghold command regressions."""

import pytest

from seljuk import engine
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.state import IllegalAction
from tests.test_cross_game_combat import place, position


@pytest.mark.parametrize("legacy_owner", [None, "seljuk", "roman"])
def test_local_scouts_choice_is_final_during_hidden_combat_review(tmp_path, legacy_owner):
    gs = position()
    gs.meta.options["hidden_mats"] = True
    attacker = place(gs, "romanos_diogenes", "laodikeia")
    defender = place(gs, "alp_arslan", "antioch")
    attacker.forces = {"tagmata": 4}
    defender.forces = {"infantry": 8}
    gs.meta.active_player = "roman"
    gs.meta.active_card = gs.meta.active_lord = attacker.id
    gs.locales["antioch"].conquered_side = "seljuk"
    gs.locales["antioch"].conquered_count = 3
    gs.roman.draw_deck.remove("R18")
    gs.roman.held_events.append("R18")
    engine.apply_action(gs, {"type": "cmd_march", "lord": attacker.id, "to": "antioch"})

    ui = CompactInterface(LLMSession(gs))
    ui.apply({"type": "respond_approach",
              "choices": {defender.id: {"action": "avoid", "to": "artah"}}},
             version=ui.version)

    def supply(**inputs):
        return ui.apply({"type": "supply_inputs", "inputs": inputs}, version=ui.version)

    supply(play_local_scouts=True, battle_decisions=[["concede", True]])
    assert ui.owed == "seljuk"
    scouts = {"lord": defender.id, "action": "stand"}
    response = supply(local_scouts=scouts)
    assert response["accepted"] == "awaiting_revealed_combat_inputs"
    assert set(response["pending"]["combatants"]) == {attacker.id, defender.id}
    assert ui.owed == "seljuk"
    assert ui.actions(type="decline_inputs")["entries"]

    if legacy_owner:
        # Restore the joint shape emitted by the original Hidden Mats patch.
        ui._joint["scouts_requested"] = True
        if legacy_owner == "roman":
            ui._joint.update(owed_by="roman", combat_review=["roman"])
    saved = tmp_path / "combat-review.json"
    version = ui.version
    ui.save(saved)
    ui = CompactInterface.load(saved)
    assert (ui.version != version) == bool(legacy_owner)
    assert ui.owed == "seljuk"
    assert ui.actions(type="decline_inputs")["entries"]

    with pytest.raises(InterfaceError, match="field not owned"):
        supply(local_scouts=scouts)
    supply(battle_decisions=[["concede", False]])

    assert ui.owed == "roman"
    before, version = ui.gs.to_json(), ui.version
    with pytest.raises(InterfaceError, match="field not owned"):
        supply(local_scouts={**scouts, "action": "withdraw"})
    assert (ui.gs.to_json(), ui.version) == (before, version)
    assert ui.overview()["pending"]["committed_action"]["local_scouts"] == scouts
    result = ui.apply({"type": "decline_inputs"}, version=ui.version)
    assert "battle" in result["outcome"]
    assert "R18" not in ui.gs.roman.held_events
    assert not ui.gs._revealed_combat_lords


def _roman_command(locale):
    gs = position()
    lord = place(gs, "romanos_diogenes", locale)
    gs.meta.active_player = "roman"
    gs.meta.active_card = gs.meta.active_lord = lord.id
    gs.meta.actions_remaining = gs.meta.notes["card_full_actions"] = 3
    return gs, lord


def _built_fort():
    gs, lord = _roman_command("to_constantinople")
    lord.capabilities = ["R1"]
    engine.apply_action(gs, {"type": "cmd_fort", "lord": lord.id, "target": "larisa"})
    lord.cylinder = "larisa"
    gs.meta.actions_remaining = 3
    return gs, lord


def test_constructed_fort_forage_and_siege_block():
    gs, lord = _built_fort()
    forage = {"type": "cmd_forage", "lord": lord.id}
    assert any(move["type"] == "cmd_forage" for move in engine.legal_moves(gs))
    result = engine.apply_action(gs, forage)
    assert result["auto"] and result["roll"] is None
    assert lord.assets.provender == 1

    gs, lord = _built_fort()
    besieger = place(gs, "alp_arslan", "larisa")
    gs.locales["larisa"].siege_markers = 1
    lord.besieged = True
    before = gs.to_json()
    assert all(move["type"] != "cmd_forage" for move in engine.legal_moves(gs))
    with pytest.raises(IllegalAction, match="forage_besieged"):
        engine.apply_action(gs, forage)
    assert gs.to_json() == before

    gs.meta.active_player = "seljuk"
    gs.meta.active_card = gs.meta.active_lord = besieger.id
    assert any(move["type"] == "cmd_forage" for move in engine.legal_moves(gs))
    assert not engine.apply_action(gs, {"type": "cmd_forage", "lord": besieger.id})["auto"]


def test_constructed_fort_allows_roman_commander_tax():
    gs, lord = _built_fort()
    assert any(move["type"] == "cmd_tax" for move in engine.legal_moves(gs))
    result = engine.apply_action(gs, {"type": "cmd_tax", "lord": lord.id})
    assert result["coin"] == 1
    assert result["placed_ravaged"]
    assert gs.locales["larisa"].ravaged_side == "seljuk"


@pytest.mark.parametrize(("locale", "automatic"), [("hama", False), ("aleppo", False), ("melitene", True)])
def test_roman_forage_observes_fatimid_exception(locale, automatic):
    gs, lord = _roman_command(locale)
    gs.locales[locale].conquered_side = None
    gs.locales[locale].conquered_count = 0
    result = engine.apply_action(gs, {"type": "cmd_forage", "lord": lord.id})
    assert result["auto"] == automatic
    if automatic:
        assert result["roll"] is None
    else:
        assert result["roll"] in range(1, 7)
        assert result["provender_added"] == (result["roll"] <= 3)
