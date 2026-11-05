"""Cross-game audit R3: compound responses must not partially execute."""
import pytest

from seljuk import engine, map as gmap, scenarios
from seljuk.llm import LLMSession
from seljuk.state import IllegalAction


def approach_state():
    state = scenarios.load_scenario("manzikert", seed=1)
    state.meta.phase = "campaign"
    state.meta.subphase = "campaign.command"
    state.meta.active_player = "seljuk"
    state.meta.actions_remaining = 1
    attackers = ["alp_arslan"]
    defenders = ["romanos_diogenes", "joseph_tarchaneiotes"]
    locale = "theodosiopolis"
    for lid, lord in state.lords.items():
        lord.mustered = lid in attackers + defenders
        lord.cylinder = locale if lord.mustered else "calendar"
        lord.besieged = False
        lord.bypassed = False
        lord.assets.loot = lord.assets.provender = lord.assets.carts = 0
    destinations = sorted(gmap.neighbors(locale))
    state.meta.pending = [{"type": "approach_response", "locale": locale,
        "attackers": attackers, "defenders": defenders, "_owed_by": "roman",
        "from": destinations[1]}]
    state.meta.active_lord = attackers[0]
    state.lords[defenders[0]].assets.loot = 2
    return state, destinations[0]


def test_rejected_response_restores_board_assets_and_corrected_retry():
    state, destination = approach_state()
    pristine = state.model_copy(deep=True)
    lord = state.lords["romanos_diogenes"]
    assets, history, pending = lord.assets, state.history, state.meta.pending
    before = state.to_json()
    choices = {lord.id: {"action": "avoid", "to": destination},
               "joseph_tarchaneiotes": {"action": "avoid", "to": "not_a_locale"}}
    with pytest.raises(IllegalAction, match="bad_avoid"):
        LLMSession(state).apply({"type": "respond_approach", "choices": choices})
    assert state.to_json() == before
    assert state.lords[lord.id] is lord
    assert lord.assets is assets
    assert state.history is history
    assert state.meta.pending is pending
    choices["joseph_tarchaneiotes"]["to"] = destination
    action = {"type": "respond_approach", "choices": choices}
    assert LLMSession(state).apply(action) == LLMSession(pristine).apply(action)
    assert state.to_json() == pristine.to_json()
    assert state.lords["alp_arslan"].assets.loot == 2


def test_failure_after_dice_commit_restores_rng_and_existing_references(monkeypatch):
    state, _ = approach_state()
    state.meta.pending.clear()
    before = state.to_json()
    history, lord = state.history, state.lords["alp_arslan"]
    def fail(state, action, roller):
        roller.d6()
        lord.assets.coin = 99
        state.history.append({"action": "partial"})
        raise RuntimeError("failure after dice")
    monkeypatch.setitem(engine._CAMPAIGN_HANDLERS, "audit_failure", fail)
    with pytest.raises(RuntimeError, match="failure after dice"):
        engine.apply_action(state, {"type": "audit_failure"})
    assert state.to_json() == before
    assert state.history is history
    assert state.lords[lord.id] is lord
