"""Relief Sally and Rearguard Event timing through public March and Stand."""

import pytest

from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface
from seljuk.state import GameState
from tests.test_round8_combat import _dispatch, _place, _position


def _hold(state, side, card):
    deck = state.side_decks(side)
    deck.draw_deck.remove(card)
    deck.held_events.append(card)


@pytest.mark.parametrize("advance", [False, True])
def test_field_reserve_owner_can_decline_advancement(advance):
    state = _position(seed=2)
    _place(state, "alp_arslan", {"turkic_horse": 6, "ghulam_cavalry": 2, "infantry": 2}, "laodikeia")
    _place(state, "romanos_diogenes", {"tagmata": 2, "infantry": 3}, "antioch")
    _place(state, "chatatourios", {"infantry": 4}, "antioch")
    state.locales["laodikeia"].conquered_side = "seljuk"
    state.locales["laodikeia"].conquered_count = 1
    _dispatch(state, {"type": "cmd_march", "lord": "alp_arslan", "to": "antioch"})
    roman = [["initial_placement_defender", "romanos_diogenes"]]
    if not advance:
        roman.append(["reserve_advance", None])
    result = _dispatch(state, {
        "type": "respond_approach",
        "choices": {lid: {"action": "stand"} for lid in ("romanos_diogenes", "chatatourios")},
        "battle_decisions": {"roman": roman, "seljuk": [["concede", False], ["concede", True]]},
    })["battle"]
    choice, = [d for d in result["decisions"] if d["type"] == "reserve_advance"]
    assert choice["options"] == ["chatatourios", None]
    assert choice["choice"] == ("chatatourios" if advance else None)
    hits = [row for row in result["strikes"] if row["target"] == "chatatourios"]
    assert bool(hits) is advance
    if not advance:
        assert state.lords["chatatourios"].forces == {"infantry": 4}


def test_field_striking_player_can_order_the_same_groups_differently():
    state = _position(seed=3, active="romanos_diogenes")
    for lid in ("romanos_diogenes", "joseph_tarchaneiotes", "nikephoros_bryennios"):
        _place(state, lid, {"tagmata": 1}, "laodikeia")
    defenders = ("alp_arslan", "sav_tekin", "emir_of_arran")
    for lid in defenders:
        _place(state, lid, {"infantry": 2}, "antioch")
    state.locales["antioch"].conquered_side = "seljuk"
    state.locales["antioch"].conquered_count = 1
    _dispatch(state, {"type": "cmd_march", "lord": "romanos_diogenes", "to": "antioch",
                      "group": ["joseph_tarchaneiotes", "nikephoros_bryennios"]})
    checkpoint = state.to_json()

    def resolve(orders):
        ui = CompactInterface(LLMSession(GameState.from_json(checkpoint)))
        ui.apply({"type": "respond_approach", "choices": {lid: {"action": "stand"} for lid in defenders},
                  "battle_decisions": [["initial_placement_defender", "alp_arslan"],
                                       ["initial_placement_defender", "sav_tekin"], ["concede", True]]},
                 version=ui.version)
        assert ui.viewer == "roman"
        assert "strike_order" in ui._input_contract()
        ui.apply({"type": "supply_inputs", "inputs": {"battle_decisions": [
            ["initial_placement_attacker", "joseph_tarchaneiotes"],
            *[["strike_order", target] for target in orders],
        ]}}, version=ui.version)
        result = ui.gs.history[-1]["result"]["battle"]
        return result, ui.gs.to_json()

    ordinary, _ = resolve([])
    reverse, final = resolve(["emir_of_arran", "alp_arslan"])
    assert (reverse, final) == resolve(["emir_of_arran", "alp_arslan"])
    choices = [d for d in reverse["decisions"] if d["type"] == "strike_order"
               and d["info"]["step"] == "missile"]
    assert [(d["info"]["side"], d["choice"]) for d in choices] == [
        ("roman", "emir_of_arran"), ("roman", "alp_arslan")]
    for result, targets in ((ordinary, ["sav_tekin", "alp_arslan", "emir_of_arran"]),
                            (reverse, ["emir_of_arran", "alp_arslan", "sav_tekin"])):
        opening = [s for s in result["strikes"] if s["step"] == "missile" and s["by"] == "attacker"]
        assert [s["target"] for s in opening] == targets
        assert [s["routed_units"] for s in opening] == [[], ["infantry"], ["infantry"]]


@pytest.mark.parametrize("seed, survives_siegeworks", [(2, False), (5, True)])
def test_relief_sally_cavalry_charge_precedes_missiles(seed, survives_siegeworks):
    def fight(charge):
        state = _position(seed=seed, active="chatatourios")
        _place(state, "chatatourios", {"infantry": 4}, "laodikeia")
        _place(state, "romanos_diogenes", {"tagmata": 2}, "antioch", inside=True)
        _place(state, "alp_arslan", {"turkic_horse": 2, "ghulam_cavalry": 2}, "antioch")
        state.locales["antioch"].siege_markers = 2
        action = {
            "type": "respond_approach", "choices": {"alp_arslan": {"action": "stand"}},
            "sally_join": ["romanos_diogenes"],
            "battle_decisions": {"roman": [["concede", True]], "seljuk": []},
        }
        if charge:
            _hold(state, "roman", "R24")
            action["battle_events"] = {"roman": [{"card": "R24", "lord": "romanos_diogenes"}]}
        _dispatch(state, {"type": "cmd_march", "lord": "chatatourios", "to": "antioch"})
        result = _dispatch(state, action)["battle"]
        assert result["relief_sally"] == ["romanos_diogenes"]
        assert "R24" not in state.roman.held_events
        return result["strikes"]

    ordinary = fight(False)
    assert ordinary[0]["step"] == "missile"
    charged = fight(True)
    horse_strikes = [strike for strike in charged
                     if strike.get("sallying") and strike["step"] == "horse_melee"]
    if survives_siegeworks:
        assert horse_strikes == charged[:1]
        assert horse_strikes[0]["target"] == "alp_arslan"
        assert horse_strikes[0]["hits"] == 1  # Pursuit still halves the two Tagmata Hits.
    else:
        # Siegeworks cancels the early Strike, and the Horse cannot retry it.
        assert horse_strikes == []


def test_rearguard_command_confusion_delays_missiles_and_melee():
    def fight(confusion):
        state = _position(seed=2, active="alp_arslan")
        _place(state, "alp_arslan", {"turkic_horse": 2, "ghulam_cavalry": 2}, "laodikeia")
        _place(state, "artuk_beg", {"turkic_horse": 2}, "antioch", inside=True)
        _place(state, "romanos_diogenes", {"tagmata": 2}, "antioch")
        _place(state, "chatatourios", {"infantry": 4}, "antioch")
        for locale_id in ("laodikeia", "antioch"):
            locale = state.locales[locale_id]
            locale.conquered_side, locale.conquered_count = "seljuk", 1
        state.locales["antioch"].siege_markers = 2
        action = {
            "type": "respond_approach",
            "choices": {lord: {"action": "stand"} for lord in ("chatatourios", "romanos_diogenes")},
            "sally_join": ["artuk_beg"],
            "battle_decisions": {
                "roman": [["initial_placement_defender", "chatatourios"]],
                "seljuk": [["concede", True]],
            },
        }
        if confusion:
            _hold(state, "seljuk", "S6")
            action["battle_events"] = {"seljuk": [{"card": "S6", "lord": "romanos_diogenes"}]}
        _dispatch(state, {"type": "cmd_march", "lord": "alp_arslan", "to": "antioch"})
        result = _dispatch(state, action)["battle"]
        assert result["relief_sally"] == ["artuk_beg"]
        assert "S6" not in state.seljuk.held_events
        return result["strikes"]

    for confusion in (False, True):
        strikes = fight(confusion)
        for step in ("missile", "horse_melee"):
            rear, = [i for i, strike in enumerate(strikes)
                     if strike["step"] == step and strike["target"] == "artuk_beg"]
            front, = [i for i, strike in enumerate(strikes)
                      if strike["step"] == step and strike["target"] == "chatatourios"]
            assert (rear > front) == confusion
