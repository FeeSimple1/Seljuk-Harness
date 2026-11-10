"""Round 7 combat regressions with seeded dispatch and per-faction scripts."""

import pytest

from seljuk import battle, capabilities, engine
from seljuk.invariants import check_invariants
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface
from seljuk.state import GameState
from tests.test_chat_audit_regressions import ConstantDice
from tests.test_cross_game_combat import place, position


def _position(seed, active="alp_arslan"):
    state = position(seed)
    state.meta.active_lord = state.meta.active_card = active
    state.meta.active_player = state.lords[active].side
    state.themata = {thema: [] for thema in state.themata}
    for locale in state.locales.values():
        locale.themata_defending.clear()
        locale.siege_markers = 0
    for lord in state.lords.values():
        lord.capabilities.clear()
        lord.flags.clear()
        lord.moved_fought = False
    for decks in (state.roman, state.seljuk):
        decks.command_plan = [active]
        decks.plan_pointer = 1
        decks.capabilities_in_play.clear()
        decks.held_events.clear()
        decks.this_campaign_events.clear()
    return state


def _place(state, lid, forces, locale="melitene", *, inside=False):
    lord = place(state, lid, locale, carts=8, provender=8)
    lord.forces = forces
    lord.besieged = inside
    for vassal in lord.vassals:
        if not vassal.special_name:
            vassal.levied = True
            vassal.service_box = 10
    return lord


def _capability(state, lid, card):
    lord = state.lords[lid]
    draw = state.side_decks(lord.side).draw_deck
    if card in draw:
        draw.remove(card)
    lord.capabilities.append(card)


def _dispatch(state, action):
    restored = GameState.from_json(state.to_json())
    result = engine.apply_action(state, action)
    assert engine.apply_action(restored, action) == result
    assert restored.to_json() == state.to_json()
    assert not check_invariants(state)
    return result


def _storm_move(state):
    return next(move for move in engine.legal_moves(state) if move["type"] == "cmd_storm")


def test_lamellar_turkic_horse_take_garrison_missile_armor_penalty():
    state = _position(seed=4)
    _place(state, "alp_arslan", {"turkic_horse": 2})
    _capability(state, "alp_arslan", "S1")
    state.locales["melitene"].siege_markers = 1
    result = _dispatch(state, _storm_move(state))["storm"]
    first = result["strikes"][0]
    # Seed 4 rolls 2 against Siegeworks and 3 against Lamellar's reduced 1-2.
    assert first["step"] == "def_missile_garrison" and first["hits"] == 1
    assert first["routed"] == ["turkic_horse"]


@pytest.mark.parametrize("lamellar", [False, True])
def test_storm_armor_first_uses_the_active_capability(lamellar):
    state = _position(seed=2)
    _place(state, "alp_arslan", {"turkic_horse": 2, "infantry": 1})
    if lamellar:
        _capability(state, "alp_arslan", "S1")
    state.locales["melitene"].siege_markers = 1
    result = _dispatch(state, _storm_move(state))["storm"]
    choice = next(d for d in result["decisions"] if d["type"] == "hit_absorption")
    assert set(choice["options"]) == (
        {"infantry", "turkic_horse"} if lamellar else {"infantry"}
    )


def test_lamellar_armor_first_expires_immediately_after_the_third_rout():
    state = _position(seed=1)
    unarmored = _place(state, "afsin_beg", {"turkic_horse": 1})
    armored = _place(state, "alp_arslan", {"turkic_horse": 4})
    _capability(state, armored.id, "S1")
    ctx = battle.DecisionContext()
    battle._absorb_storm(state, unarmored, 4, "missile", anti_armor=True,
                        armored_first=True, ctx=ctx, roller=ConstantDice(3),
                        select_target=True, targets=[unarmored, armored])
    lord_options = [d["options"] for d in ctx.trace if d["type"] == "storm_hit_lord"]
    assert lord_options == [[armored.id]] * 3 + [[unarmored.id, armored.id]]
    assert not capabilities.lamellar_active(state, armored.id)
    assert armored.routed == {"turkic_horse": 3}
    assert unarmored.routed == {"turkic_horse": 1}


def _field_battle(state, forces, roman_script, seljuk_script, *, capability):
    _place(state, "alp_arslan", forces, "laodikeia")
    _place(state, "robert_crepin", {"norman_knights": 2, "infantry": 1}, "antioch")
    _capability(state, "alp_arslan" if capability == "S16" else "robert_crepin", capability)
    origin = state.locales["laodikeia"]
    origin.conquered_side, origin.conquered_count = "seljuk", 1
    engine.apply_action(state, {"type": "cmd_march", "lord": "alp_arslan", "to": "antioch"})
    return _dispatch(state, {
        "type": "respond_approach",
        "choices": {"robert_crepin": {"action": "stand"}},
        "battle_decisions": {"seljuk": [["concede", True], *seljuk_script], "roman": roman_script},
    })["battle"]


def test_parthian_striker_selects_before_ordinary_hit_absorption():
    result = _field_battle(
        _position(seed=9), {"turkic_horse": 2, "ghulam_cavalry": 1},
        [["hit_absorption", "infantry"]], [["select_target_unit", "norman_knights"]],
        capability="S16",
    )
    choices = [d for d in result["decisions"]
               if d["type"] in ("select_target_unit", "hit_absorption")]
    assert [(d["type"], d["choice"]) for d in choices[:2]] == [
        ("select_target_unit", "norman_knights"), ("hit_absorption", "infantry"),
    ]
    assert set(choices[0]["options"]) == {"norman_knights", "infantry"}
    assert result["strikes"][0]["routed_units"] == ["infantry"]


def test_new_select_target_does_not_consume_an_existing_bare_absorption_choice():
    state = _position(seed=1)
    lord = _place(state, "robert_crepin", {"norman_knights": 2, "infantry": 1})
    ctx = battle.DecisionContext(["norman_knights"])
    available = ["norman_knights", "infantry"]
    chosen = battle._select_target_unit(
        ctx, lord, "missile", available,
        lambda u: capabilities.protection_range(state, lord.id, u, "missile")[1],
    )
    assert chosen == "infantry"
    assert ctx.decide("hit_absorption", available) == "norman_knights"


def test_garrison_striker_uses_its_own_compact_interface_queue():
    state = _position(seed=1)
    _place(state, "alp_arslan", {"ghulam_cavalry": 2, "infantry": 2})
    state.locales["melitene"].siege_markers = 1
    ui = CompactInterface(LLMSession(state))
    initial = ui.gs.to_json()
    ui.apply(_storm_move(state), version=ui.version)
    assert ui.owed == "roman"
    assert ui.gs.to_json() == initial
    assert "select_target_unit" in ui._input_contract()
    ui.apply({
        "type": "supply_inputs",
        "inputs": {"storm_decisions": [["select_target_unit", "ghulam_cavalry"]]},
    }, version=ui.version)
    result = ui._receipts[-1]["roman"]["combat_detail"]["storm"]
    assert result["decisions"][0]["type"] == "storm_hit_lord"
    assert result["decisions"][1]["type"] == "select_target_unit"
    assert result["decisions"][1]["choice"] == "ghulam_cavalry"
    assert result["strikes"][0]["routed"] == ["ghulam_cavalry"]
    assert not check_invariants(ui.gs)


@pytest.mark.parametrize("save_for_foot", [False, True])
def test_norman_cavalry_has_one_missile_and_one_shared_melee_reroll(save_for_foot):
    absorb = ["hit_absorption", "norman_knights"]
    roman = [absorb] * 12
    if save_for_foot:
        roman = [absorb, ["norman_reroll", True],
                 absorb, ["norman_reroll", False], absorb, ["norman_reroll", True]]
    result = _field_battle(_position(seed=17), {"ghulam_cavalry": 1, "infantry": 2},
                           roman, [], capability="R5")
    assert result["rounds"] == 1
    rerolls = [d["choice"] for d in result["decisions"] if d["type"] == "norman_reroll"]
    assert rerolls == ([True, False, True] if save_for_foot else [True, True])
    strikes = [s for s in result["strikes"] if s["target"] == "robert_crepin"]
    assert [(s["step"], s["routed_units"]) for s in strikes] == [
        ("missile", []), ("horse_melee", ["norman_knights"]), ("foot_melee", ["norman_knights"]),
    ]


def test_norman_cavalry_shares_storm_missile_reroll_across_garrison_and_lord():
    state = _position(seed=24, active="robert_crepin")
    _place(state, "robert_crepin", {"norman_knights": 2})
    _place(state, "alp_arslan", {"turkic_horse": 2, "ghulam_cavalry": 1}, inside=True)
    _capability(state, "robert_crepin", "R5")
    locale = state.locales["melitene"]
    locale.conquered_side, locale.conquered_count = "seljuk", 2
    locale.siege_markers = 1
    result = _dispatch(state, _storm_move(state))["storm"]
    assert [(s["step"], s["hits"], s["routed"]) for s in result["strikes"][:2]] == [
        ("def_missile_garrison", 2, []), ("def_missile_lord", 2, ["norman_knights"]),
    ]
