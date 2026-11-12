"""End-of-card Feed resource elections through the versioned interface."""

import pytest

from seljuk import engine, scenarios
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface
from seljuk.llm.session import LLMSession
from seljuk.state import GameState, IllegalAction

ALP = "alp_arslan"
FEED = "feed_resource_choice"


def _play(ui, kind, *, parameters=None, **match):
    entry = next(row for row in ui.actions(type=kind)["entries"]
                 if all(row["action"].get(k) == v for k, v in match.items())
                 and not row["action"].get("discard_to_unladen"))
    return ui.apply(entry["id"], parameters=parameters)


def _native_card():
    state = scenarios.load_scenario("showdown_in_anatolia", seed=7)
    state.meta.phase, state.meta.subphase = "campaign", "campaign.plan"
    state.meta.active_player = "seljuk"
    state.meta.pending = []
    for side, lord in (("seljuk", ALP), ("roman", "manuel_komnenos")):
        engine.apply_action(state, {"type": "build_plan", "side": side,
                                    "cards": [lord] * 2 + ["no_command"] * 5})
    state.lords[ALP].assets.loot = 1
    return state


@pytest.mark.parametrize("loot", [False, True])
def test_feed_split_changes_next_march_after_reload(loot):
    ui = CompactInterface(LLMSession(_native_card()))
    _play(ui, "cmd_march", lord=ALP, to="mempet", way_type="road")
    _play(ui, "end_activation", interactive_feed=True)
    assert ui.gs.meta.subphase == "campaign.fpd_feed"
    saved = ui.gs.to_json()
    ui = CompactInterface(LLMSession(GameState.from_json(saved)))
    for invalid in ({"type": FEED, "side": "roman"},
                    {"type": FEED, "feed_loot": {ALP: 2}},
                    {"type": "fpd_done"}):
        with pytest.raises(IllegalAction):
            engine.apply_action(ui.gs, invalid)
        assert ui.gs.to_json() == saved
    _play(ui, FEED, feed_loot={ALP: 1} if loot else None)
    alp = ui.gs.lords[ALP]
    assert (alp.assets.provender, alp.assets.loot) == (int(loot), int(not loot))
    assert ui.gs.meta.subphase == "campaign.fpd_pay"
    while ui.gs.meta.subphase == "campaign.fpd_pay":
        _play(ui, "fpd_done")
    assert ui.gs.meta.active_lord == "manuel_komnenos"
    _play(ui, "end_activation")
    while ui.gs.meta.subphase == "campaign.fpd_pay":
        _play(ui, "fpd_done")
    assert ui.gs.meta.active_lord == ALP
    before = ui.gs.meta.actions_remaining
    _play(ui, "cmd_march", lord=ALP, to="ani", way_type="road")
    assert before - ui.gs.meta.actions_remaining == (1 if loot else 2)
    assert not check_invariants(ui.gs)


def test_card_exhaustion_prompts_each_owner_before_pay():
    state = _native_card()
    state.meta.actions_remaining = 2
    roman = state.lords["manuel_komnenos"]
    roman.assets.provender = roman.assets.loot = 2
    roman.moved_fought = True
    ui = CompactInterface(LLMSession(state))
    _play(ui, "cmd_march", parameters={"interactive_feed": True},
          lord=ALP, to="mempet", way_type="road")
    assert ui.gs.meta.subphase == "campaign.fpd_feed"
    assert ui.gs.meta.active_lord is None
    _play(ui, FEED, feed_loot={ALP: 1})
    assert ui.owed == "roman"
    assert ui.gs.meta.subphase == "campaign.fpd_feed"
    assert all(ALP not in (row.get("action", {}).get("feed_loot") or {})
               for row in ui.actions(type=FEED)["entries"])
    _play(ui, FEED, feed_loot={"manuel_komnenos": 1})
    assert ui.gs.meta.subphase == "campaign.fpd_pay"
