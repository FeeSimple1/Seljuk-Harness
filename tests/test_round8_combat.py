"""Round 8 combat regressions with printed complements and seeded dispatch."""

import pytest

from seljuk import actions, battle, capabilities, scenarios, static_data as sd
from seljuk.invariants import check_invariants
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface
from seljuk.rng import DiceRoller
from seljuk.state import Assets
from tests.test_chat_audit_regressions import ConstantDice
from tests.test_round7_combat import _dispatch as _replay_dispatch
from tests.test_round7_combat import _place as _place_lord
from tests.test_round7_combat import _storm_move


def _position(seed=1, active="alp_arslan"):
    state = scenarios.load_scenario("emperor_and_the_lion", seed=seed)
    for lord in state.lords.values():
        lord.mustered = False
        lord.cylinder = "offboard"
        lord.besieged = lord.bypassed = False
        lord.forces, lord.routed, lord.flags = {}, {}, {}
        lord.themata_on_mat = []
        lord.assets = Assets()
        lord.capabilities = []
        lord.moved_fought = False
    for locale in state.locales.values():
        locale.themata_defending = []
        locale.siege_markers = 0
    state.meta.themata_removed = [m for markers in state.themata.values() for m in markers]
    state.themata = {key: [] for key in state.themata}
    state.meta.calendar_box = 9
    state.meta.pending = []
    state.meta.phase, state.meta.subphase = "campaign", "campaign.command"
    state.meta.active_player = state.lords[active].side
    state.meta.active_lord = state.meta.active_card = active
    state.meta.actions_remaining = 2
    for side in ("roman", "seljuk"):
        deck = state.side_decks(side)
        deck.command_plan = [active] if side == state.meta.active_player else []
        deck.plan_pointer = len(deck.command_plan)
    return state


def _place(state, lid, forces, locale="melitene", *, inside=False):
    data = sd.lord(lid)
    maximum = dict(data["starting_forces"])
    for vassal in data["vassals"]:
        for unit, count in vassal["forces"].items():
            maximum[unit] = maximum.get(unit, 0) + count
    assert all(0 <= n <= maximum.get(unit, 0) for unit, n in forces.items())
    return _place_lord(state, lid, dict(forces), locale, inside=inside)


def _capability(state, side, card, lid=None):
    deck = state.side_decks(side)
    deck.draw_deck.remove(card)
    (state.lords[lid].capabilities if lid else deck.capabilities_in_play).append(card)


def _dispatch(state, action):
    assert not check_invariants(state)
    assert all(actions._pool_remaining(state, unit) >= 0 for unit in actions._UNIT_POOL)
    for side in ("roman", "seljuk"):
        deck = state.side_decks(side)
        cards = deck.draw_deck + deck.held_events + deck.capabilities_in_play
        cards += deck.this_campaign_events
        cards += [card for lord in state.lords.values() if lord.side == side
                  for card in lord.capabilities]
        assert len(cards) == len(set(cards)) == 25
        assert set(cards) == set(sd.card_ids_for_side(side))
    return _replay_dispatch(state, action)


@pytest.mark.parametrize("psiloi", [False, True])
def test_roman_militia_only_fire_with_psiloi_in_a_public_field_battle(psiloi):
    state = _position(seed=1)
    _place(state, "alp_arslan", {"turkic_horse": 2, "ghulam_cavalry": 1}, "laodikeia")
    _place(state, "andronikos_doukas", {"militia": 2}, "antioch")
    origin = state.locales["laodikeia"]
    origin.conquered_side, origin.conquered_count = "seljuk", 1
    if psiloi:
        _capability(state, "roman", "R25")
    _dispatch(state, {"type": "cmd_march", "lord": "alp_arslan", "to": "antioch"})
    result = _dispatch(state, {
        "type": "respond_approach", "choices": {"andronikos_doukas": {"action": "stand"}},
        "battle_decisions": {"seljuk": [["concede", True]], "roman": []},
    })["battle"]
    defending = [s for s in result["strikes"] if s["by"] == "defender" and s["step"] == "missile"]
    if psiloi:
        assert defending[0]["hits"] == 1
        assert defending[0]["routed_units"] == ["turkic_horse"]
        assert result["strikes"][0] == defending[0]
    else:
        assert defending == []
        assert result["strikes"][0]["by"] == "attacker"
        assert result["strikes"][0]["routed_units"] == ["militia", "militia"]


@pytest.mark.parametrize("psiloi", [False, True])
@pytest.mark.parametrize("cat", [None, "horse", "foot"])
def test_psiloi_applies_to_storm_and_the_foot_portion_of_battle_missiles(psiloi, cat):
    state = _position(active="andronikos_doukas")
    _place(state, "andronikos_doukas", {"militia": 3, "tagmata": 1})
    if psiloi:
        _capability(state, "roman", "R25")
    side = battle._Side(state, ["andronikos_doukas"], "attacker")
    side.front["center"], side.reserve = "andronikos_doukas", []
    normal, anti, select = battle._lord_step_hits_caps(
        state, "andronikos_doukas", "missile", 1, cat=cat)
    expected = (0.5 if cat in (None, "horse") else 0)
    expected += 1.5 if psiloi and cat in (None, "foot") else 0
    assert (normal, anti, select) == (expected, 0, 0)
    assert battle._lord_step_hits(state, side, "missile", 1) == (2 if psiloi else 0.5)
    # Garrisons gain their own Missiles regardless of Psiloi.
    assert battle._garrison_missile_hits({"militia": 2, "infantry": 1}) == 1.5


def _storm_position():
    state = _position(seed=8, active="romanos_diogenes")
    _place(state, "romanos_diogenes", {"tagmata": 4, "infantry": 3, "turkic_horse": 2})
    locale = state.locales["melitene"]
    locale.conquered_side, locale.conquered_count = "seljuk", 2
    locale.siege_markers = 1
    return state


@pytest.mark.parametrize("roman,seljuk,chosen", [
    ([], [], "infantry"),
    ([], [["hit_absorption", "militia"]], "militia"),
    ([["hit_absorption", "militia"]], [], "infantry"),
])
def test_the_garrison_owner_controls_its_first_live_absorption_choice(roman, seljuk, chosen):
    state = _storm_position()
    move = {**_storm_move(state), "storm_decisions": {"roman": roman, "seljuk": seljuk}}
    result = _dispatch(state, move)["storm"]
    first = next(d for d in result["decisions"] if d["type"] == "hit_absorption")
    assert first["options"] == ["infantry", "militia"]
    assert first["choice"] == chosen


@pytest.mark.parametrize("owner", ["roman", "seljuk"])
def test_garrison_choices_follow_live_units_and_ignore_the_other_players_queue(owner):
    state = _position()
    defender = battle._Side(state, [], "defender")
    defender.faction, defender.locale = owner, "melitene"
    other = "seljuk" if owner == "roman" else "roman"
    ctx = battle.DecisionContext({
        owner: [["hit_absorption", "militia"], ["hit_absorption", "infantry"]],
        other: [["hit_absorption", "militia"]],
    })
    garrison, routed = {"infantry": 1, "militia": 1}, {}
    battle._hit_defender(state, defender, garrison, routed, 2, "missile", (1, 0),
                         ConstantDice(2), ctx, [], "att_missile", 1)
    assert routed == {"militia": 1}
    assert garrison == {"infantry": 1, "militia": 0}
    assert [d["options"] for d in ctx.trace] == [["infantry", "militia"], ["infantry"]]
    assert ctx.by_side[owner].scripted == []
    assert ctx.by_side[other].scripted == [["hit_absorption", "militia"]]


def test_new_garrison_choice_preserves_a_bare_script_for_the_defending_lord():
    state = _position()
    defender = battle._Side(state, [], "defender")
    defender.faction = "roman"
    ctx = battle.DecisionContext(["militia"])
    battle._hit_defender(state, defender, {"infantry": 1}, {}, 1, "missile", (1, 0),
                         ConstantDice(6), ctx, [], "att_missile", 1)
    assert ctx.scripted == ["militia"]
    assert ctx.decide("hit_absorption", ["infantry", "militia"]) == "militia"


def test_compact_interface_hands_the_garrison_election_to_its_owner():
    state = _storm_position()
    ui = CompactInterface(LLMSession(state))
    before = ui.gs.to_json()
    ui.apply(_storm_move(state), version=ui.version)
    assert ui.owed == "seljuk" and ui.gs.to_json() == before
    assert "Garrison" in ui._input_contract()["hit_absorption"]
    ui.apply({"type": "supply_inputs", "inputs": {
        "storm_decisions": [["hit_absorption", "militia"]],
    }}, version=ui.version)
    result = ui._receipts[-1]["roman"]["combat_detail"]["storm"]
    first = next(d for d in result["decisions"] if d["type"] == "hit_absorption")
    assert first["choice"] == "militia" and first["options"] == ["infantry", "militia"]
    assert not check_invariants(ui.gs)


@pytest.mark.parametrize("lamellar,alakatia", [(True, True), (False, True), (True, False)])
def test_alakatia_penalizes_active_lamellar_in_a_public_missile_step(lamellar, alakatia):
    state = _position(seed=9, active="chatatourios")
    _place(state, "chatatourios", {"infantry": 4}, "laodikeia")
    _place(state, "alp_arslan", {"turkic_horse": 2}, "antioch")
    locale = state.locales["antioch"]
    locale.conquered_side, locale.conquered_count = "seljuk", 3
    if lamellar:
        _capability(state, "seljuk", "S1", "alp_arslan")
    if alakatia:
        _capability(state, "roman", "R23", "chatatourios")
    _dispatch(state, {"type": "cmd_march", "lord": "chatatourios", "to": "antioch"})
    result = _dispatch(state, {
        "type": "respond_approach", "choices": {"alp_arslan": {"action": "stand"}},
        "battle_decisions": {"roman": [["concede", True]], "seljuk": []},
    })["battle"]
    hits = [s for s in result["strikes"] if s["step"] == "missile" and s["by"] == "attacker"]
    if alakatia:
        assert hits[0]["hits"] == 1 and hits[0]["routed_units"] == ["turkic_horse"]
    else:
        assert hits == []


@pytest.mark.parametrize("choice,routed", [(None, []), ("evade", []), ("armor", ["turkic_horse"])])
def test_melee_penalty_does_not_reduce_evade_and_the_owner_can_choose_lamellar(choice, routed):
    state = _position()
    lord = _place(state, "alp_arslan", {"turkic_horse": 2})
    _capability(state, "seljuk", "S1", lord.id)
    selected = [["protection_type", choice]] if choice else []
    ctx = battle.DecisionContext({"roman": [["protection_type", "armor"]], "seljuk": selected})
    roller = DiceRoller(seed=7)  # first die 3: Evade 1-3 saves; penalized Armor 1-2 does not.
    assert battle._apply_hits(state, lord.id, 1, "melee", ctx, roller, anti_armor=True) == routed
    assert ctx.by_side["roman"].scripted == [["protection_type", "armor"]]


def test_field_lamellar_choice_ends_immediately_at_the_third_rout():
    state = _position()
    lord = _place(state, "alp_arslan", {"turkic_horse": 4})
    _capability(state, "seljuk", "S1", lord.id)
    ctx = battle.DecisionContext({
        "seljuk": [["protection_type", "armor"]] * 3, "roman": [],
    })
    routed = battle._apply_hits(state, lord.id, 4, "melee", ctx, ConstantDice(3), anti_armor=True)
    assert routed == ["turkic_horse"] * 3
    assert lord.forces["turkic_horse"] == 1 and not capabilities.lamellar_active(state, lord.id)
    assert len([d for d in ctx.trace if d["type"] == "protection_type"]) == 3


def test_a_missile_hit_cannot_use_the_melee_evade_election():
    state = _position()
    lord = _place(state, "alp_arslan", {"turkic_horse": 2})
    _capability(state, "seljuk", "S1", lord.id)
    ctx = battle.DecisionContext({"seljuk": [["protection_type", "evade"]], "roman": []})
    routed = battle._apply_hits(state, lord.id, 1, "missile", ctx, DiceRoller(seed=7),
                               anti_armor=True)
    assert routed == ["turkic_horse"]
    assert ctx.by_side["seljuk"].scripted == [["protection_type", "evade"]]
