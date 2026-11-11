"""Relief Sally and Rearguard Event timing through public March and Stand."""

import pytest

from tests.test_round8_combat import _dispatch, _place, _position


def _hold(state, side, card):
    deck = state.side_decks(side)
    deck.draw_deck.remove(card)
    deck.held_events.append(card)


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
