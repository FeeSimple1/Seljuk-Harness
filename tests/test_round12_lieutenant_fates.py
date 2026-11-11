"""SEL12-01-F. An intact stack responds and moves together through Battle."""

import pytest

from seljuk import engine, scenarios
from seljuk.invariants import check_invariants
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface
from seljuk.state import GameState, IllegalAction

UPPER, LOWER, ATTACKER = "chatatourios", "nikephoros_bryennios", "alp_arslan"


def act(state, kind, **args):
    return engine.apply_action(state, {"type": kind, **args})


def reject(state, code, kind, **args):
    before = state.to_json()
    with pytest.raises(IllegalAction) as exc:
        act(state, kind, **args)
    assert exc.value.code == code
    assert state.to_json() == before


def plan_position():
    state = scenarios.load_scenario("emperor_and_the_lion", seed=7)
    state.meta.phase, state.meta.subphase = "campaign", "campaign.plan"
    state.meta.active_player = "seljuk"
    return state


def approach(*, paired=True, fort=False, third_defender=False):
    """Native Emperor and Lion mats staged at a legal Approach."""
    state = plan_position()
    locale, origin = ("tephrike", "keltzene") if fort else ("melitene", "lykandos")
    for lid in (UPPER, LOWER):
        state.lords[lid].cylinder = locale
    if third_defender:
        # The script must retain the existing Lord order even when an
        # independent defender chooses a fate between the pair's two choices.
        third = "romanos_diogenes"
        state.lords[third].cylinder = locale
        state.lords = {LOWER: state.lords[LOWER], **state.lords}
    state.lords[ATTACKER].cylinder = origin
    if fort:
        state.locales[origin].conquered_side = "seljuk"
        state.locales[origin].conquered_count = 1
        state.meta.vp = scenarios.score(state)
    act(state, "build_plan", side="seljuk", cards=[ATTACKER] * 2 + ["no_command"] * 5)
    stacks = [{"lieutenant": UPPER, "lower_lord": LOWER}] if paired else []
    act(state, "build_plan", side="roman", cards=[UPPER, LOWER] + ["no_command"] * 5,
        lieutenants=stacks)
    act(state, "cmd_march", lord=ATTACKER, to=locale)
    return state


def responses(action, dest=None):
    choice = {"action": action}
    if dest is not None:
        choice["to"] = dest
    return {lid: dict(choice) for lid in (UPPER, LOWER)}


def next_roman_card(state):
    act(state, "besiege_bypass", choice="bypass")
    if state.meta.subphase == "campaign.command" and state.meta.active_lord == ATTACKER:
        act(state, "end_activation")
    while state.meta.subphase == "campaign.fpd_pay":
        act(state, "fpd_done")
    assert state.meta.active_lord == UPPER


def test_pair_avoids_together_and_can_march_on_its_next_card():
    state = approach()
    choices = responses("avoid", "larisa")
    reject(state, "split_stack", "respond_approach",
           choices={**choices, UPPER: {"action": "avoid", "to": "germanikeia"}})
    reject(state, "split_stack", "respond_approach", choices={LOWER: choices[LOWER]})
    restored = GameState.from_json(state.to_json())
    assert act(state, "respond_approach", choices=choices) == act(restored, "respond_approach", choices=choices)
    assert state.to_json() == restored.to_json()
    next_roman_card(state)
    move = next(m for m in engine.legal_moves(state) if m["type"] == "cmd_march" and m["to"] == "sebasteia")
    assert act(state, "cmd_march", lord=move["lord"], to=move["to"])["group"] == [UPPER, LOWER]
    assert not check_invariants(state)


def test_fort_cannot_hold_one_half_of_pair_in_approach():
    state = approach(fort=True)
    ui = CompactInterface(LLMSession(state), player="roman")
    [entry] = ui.actions(type="respond_approach")["entries"]
    help_ = ui.details(entry["id"])["help"]
    assert help_["lieutenant_pairs"] == [(UPPER, LOWER)]
    assert all({"action": "withdraw"} not in choices for choices in help_["choices"].values())
    reject(state, "stronghold_full", "respond_approach", choices=responses("withdraw"))
    mixed = {UPPER: {"action": "withdraw"}, LOWER: {"action": "avoid", "to": "koloneia"}}
    reject(state, "split_stack", "respond_approach", choices=mixed)
    control = approach(paired=False, fort=True)
    act(control, "respond_approach", choices=mixed)
    assert control.lords[UPPER].besieged and control.lords[LOWER].cylinder == "koloneia"


def test_town_holds_whole_withdrawing_pair():
    state = approach()
    act(state, "respond_approach", choices=responses("withdraw"))
    assert all(state.lords[lid].besieged for lid in (UPPER, LOWER))
    assert state.lords[UPPER].lower_lord == LOWER
    assert not check_invariants(state)


def battle_inputs(*fates):
    return {"choices": responses("stand"),
            "battle_decisions": {"seljuk": [["concede", False]],
                                 "roman": [["concede", True], *[["retreat", fate] for fate in fates]]}}


@pytest.mark.parametrize("second_fate", ["withdraw", ["retreat", "germanikeia"]])
def test_battle_rejects_fates_that_split_pair(second_fate):
    state = approach()
    reject(state, "split_stack", "respond_approach", **battle_inputs(["retreat", "larisa"], second_fate))
    restored = GameState.from_json(state.to_json())
    choice = battle_inputs(["retreat", "larisa"])
    result = act(state, "respond_approach", **choice)
    assert result == act(restored, "respond_approach", **choice)
    assert state.to_json() == restored.to_json()
    assert result["battle"]["ending"]["removed"] == []
    assert {state.lords[lid].cylinder for lid in (UPPER, LOWER)} == {"larisa"}
    assert not check_invariants(state)


def test_independent_battle_fates_can_mix_retreat_and_withdraw():
    state = approach(paired=False)
    result = act(state, "respond_approach", **battle_inputs(["retreat", "larisa"], "withdraw"))
    assert result["battle"]["ending"]["removed"] == []
    assert state.lords[LOWER].cylinder == "larisa"
    assert state.lords[UPPER].cylinder == "melitene" and state.lords[UPPER].besieged


def test_battle_reserves_space_for_partner_during_an_interleaved_fate_choice():
    state = approach(third_defender=True)
    result = act(state, "respond_approach", **battle_inputs("withdraw"))
    assert result["battle"]["ending"]["retreat"] == [
        {"lord": LOWER, "fate": "withdraw"},
        {"lord": "romanos_diogenes", "fate": "retreat"},
        {"lord": UPPER, "fate": "withdraw"},
    ]
    assert all(state.lords[lid].besieged for lid in (UPPER, LOWER))
    assert not check_invariants(state)


def test_battle_single_fort_slot_requires_an_explicit_removal():
    state = approach(fort=True)
    reject(state, "split_stack", "respond_approach", **battle_inputs("withdraw"))
    reject(state, "split_stack", "respond_approach", **battle_inputs("withdraw", "withdraw"))
    result = act(state, "respond_approach", **battle_inputs("withdraw", "removed"))
    assert result["battle"]["ending"]["removed"] == [UPPER]
    assert state.lords[LOWER].mustered and state.lords[LOWER].besieged
    assert state.lords[LOWER].lieutenant_of is None
    assert not check_invariants(state)


def test_legacy_split_save_recovers_next_command_menu():
    state = approach()
    act(state, "respond_approach", choices=responses("avoid", "larisa"))
    next_roman_card(state)
    state.lords[LOWER].cylinder = "germanikeia"  # Old split-response state.
    restored = GameState.from_json(state.to_json())
    assert restored.lords[LOWER].cylinder == "germanikeia"
    assert restored.lords[UPPER].cylinder == "larisa"
    assert restored.lords[UPPER].lower_lord is None and restored.lords[LOWER].lieutenant_of is None
    assert not check_invariants(restored)
    assert any(m["type"] == "cmd_march" for m in engine.legal_moves(restored))


def test_local_scouts_redirects_only_the_selected_member_of_a_pair():
    state = plan_position()
    upper, lower, roman = "arisighi", "ibn_khan", "romanos_diogenes"
    for lid in (upper, lower):
        state.lords[lid].cylinder = "antioch"
    state.lords[roman].cylinder = "laodikeia"
    state.locales["antioch"].conquered_side = "seljuk"
    state.locales["antioch"].conquered_count = 3
    state.meta.vp = scenarios.score(state)
    state.roman.draw_deck.remove("R18")
    state.roman.held_events.append("R18")
    act(state, "build_plan", side="seljuk", cards=["no_command", upper, lower] + ["no_command"] * 4,
        lieutenants=[{"lieutenant": upper, "lower_lord": lower}])
    act(state, "build_plan", side="roman", cards=[roman] * 2 + ["no_command"] * 5)
    while state.meta.subphase == "campaign.fpd_pay":
        act(state, "fpd_done")
    act(state, "cmd_march", lord=roman, to="antioch")
    act(state, "respond_approach", choices={lid: {"action": "avoid", "to": "artah"}
                                           for lid in (upper, lower)},
        local_scouts={"lord": upper, "action": "withdraw"})
    assert state.lords[upper].cylinder == "antioch" and state.lords[upper].besieged
    assert state.lords[lower].cylinder == "artah"
    assert state.lords[upper].lower_lord is None and state.lords[lower].lieutenant_of is None
    assert "R18" not in state.roman.held_events
    assert not check_invariants(state)
