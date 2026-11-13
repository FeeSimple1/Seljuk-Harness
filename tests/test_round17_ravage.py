"""Ravage attempts and Themata conservation under 4.5.5, S3, and R13."""

import pytest

from seljuk import campaign, engine, scenarios
from seljuk.llm.compact import CompactInterface
from seljuk.llm.session import LLMSession
from seljuk.state import GameState, IllegalAction

ALP = "alp_arslan"
ROMANOS = "romanos_diogenes"


def _activation(seed, *, lord=ALP, locale="larisa"):
    gs = scenarios.load_scenario("emperor_and_the_lion", seed=seed)
    # Stage earlier travel and, for Arisighi, a prior Capability Levy.
    gs.lords[lord].cylinder = locale
    if lord == "arisighi":
        gs.lords[lord].capabilities.append("S3")
        gs.seljuk.draw_deck.remove("S3")
    campaign.start_campaign(gs)
    passes = ["no_command"] * (campaign.plan_size(gs) - 2)
    for side, lid in (("seljuk", lord), ("roman", ROMANOS)):
        engine.apply_action(gs, {"type": "build_plan", "side": side, "cards": [lid] * 2 + passes})
    return CompactInterface(LLMSession(gs))


def _play(ui, kind, *, parameters=None, **match):
    row = next(entry for entry in ui.actions(type=kind, limit=20)["entries"]
               if all(entry["action"].get(key) == value for key, value in match.items()))
    ui.apply(row["id"], parameters=parameters)
    return ui.gs.history[-1]["result"]


def _reject_without_mutation(gs, action, code):
    before = gs.to_json()
    with pytest.raises(IllegalAction) as exc:
        engine.apply_action(gs, action)
    assert exc.value.code == code
    assert gs.to_json() == before


def test_protected_locale_cannot_be_ravaged_until_next_command_card(tmp_path):
    ui = _activation(14)
    starting_vp = ui.gs.meta.vp.copy()
    starting_food = ui.gs.lords[ALP].assets.provender
    starting_pile = ui.gs.meta.themata_removed.copy()
    _play(ui, "cmd_ravage", actions=1)
    assert ui.owed == "roman"

    path = tmp_path / "pending.json"
    ui.save(path)
    resumed = CompactInterface.load(path)
    result = _play(resumed, "resolve_ravage_defence", defend_with=0)
    assert result["roll"] == 1 and not result["success"]
    _play(ui, "resolve_ravage_defence", defend_with=0)
    assert ui.gs.to_json() == resumed.gs.to_json()
    assert ui.gs.meta.vp == starting_vp
    assert ui.gs.lords[ALP].assets.provender == starting_food
    assert ui.gs.locales["larisa"].ravaged_side is None
    assert len(ui.gs.themata["Lykandos"]) == 1
    assert ui.gs.meta.themata_removed == starting_pile

    failed = CompactInterface(LLMSession(GameState.from_json(ui.gs.to_json())))
    assert failed.gs.meta.actions_remaining == 3
    assert not failed.actions(type="cmd_ravage")["entries"]
    assert not any(a["type"] == "cmd_ravage" for a in engine.legal_moves(failed.gs))
    for cost in (1, 2):
        _reject_without_mutation(failed.gs, {"type": "cmd_ravage", "lord": ALP, "actions": cost},
                                 "ravage_already_attempted")

    for lid in (ALP, ROMANOS):
        assert failed.gs.meta.active_lord == lid
        _play(failed, "end_activation")
        while failed.gs.meta.subphase == "campaign.fpd_pay":
            _play(failed, "fpd_done")
    assert failed.gs.meta.active_lord == ALP
    _play(failed, "cmd_ravage", actions=1)
    assert _play(failed, "resolve_ravage_defence", defend_with=0)["roll"] == 5
    assert failed.gs.locales["larisa"].ravaged_side == "seljuk"


def test_pending_protection_blocks_other_commands_and_ending_card():
    ui = _activation(14)
    starting_pile = ui.gs.meta.themata_removed.copy()
    _play(ui, "cmd_ravage", actions=1)
    _reject_without_mutation(ui.gs, {"type": "cmd_ravage", "lord": ALP, "actions": 2},
                             "pending_decision")
    _reject_without_mutation(ui.gs, {"type": "end_activation"}, "pending_decision")
    _reject_without_mutation(ui.gs, {"type": "resolve_ravage_defence", "defend_with": 1},
                             "bad_themata")
    rng_before = ui.gs.meta.rng_state
    result = _play(ui, "resolve_ravage_defence", defend_with=None)
    assert result["success"] and not result["defended"]
    assert ui.gs.meta.rng_state == rng_before
    assert len(ui.gs.themata["Lykandos"]) == 1
    assert ui.gs.meta.themata_removed == starting_pile


@pytest.mark.parametrize("resolved", [False, True])
def test_older_ravage_save_restores_attempt_from_response(resolved):
    ui = _activation(14)
    _play(ui, "cmd_ravage", actions=1)
    if resolved:
        _play(ui, "resolve_ravage_defence", defend_with=0)
    ui.gs.meta.notes.pop("ravage_attempts")
    resumed = CompactInterface(LLMSession(GameState.from_json(ui.gs.to_json())))
    if not resolved:
        _play(resumed, "resolve_ravage_defence", defend_with=0)
    assert not resumed.actions(type="cmd_ravage")["entries"]
    _reject_without_mutation(resumed.gs, {"type": "cmd_ravage", "lord": ALP, "actions": 2},
                             "ravage_already_attempted")


def test_steppe_raiders_share_target_limit_with_ravage_after_marching():
    ui = _activation(14, lord="arisighi", locale="sebasteia")
    _play(ui, "cmd_ravage", target="larisa", actions=1)
    result = _play(ui, "resolve_ravage_defence", defend_with=0)
    assert result["roll"] == 1 and not result["success"]
    assert not ui.actions(type="cmd_ravage", target="larisa")["entries"]
    assert ui.actions(type="cmd_ravage", target="charsianon")["entries"]
    _play(ui, "cmd_march", to="larisa", way_type="road")
    assert ui.gs.meta.actions_remaining == 2
    assert ui.gs.lords["arisighi"].cylinder == "larisa"
    ravages = [a for a in engine.legal_moves(ui.gs) if a["type"] == "cmd_ravage"]
    assert ravages and all(a.get("target") not in (None, "larisa") for a in ravages)
    _reject_without_mutation(ui.gs, {"type": "cmd_ravage", "lord": "arisighi", "actions": 2},
                             "ravage_already_attempted")


@pytest.mark.parametrize("locale,home,index,unit,symbols,seed", [
    ("larisa", "Lykandos", 0, "militia", 1, 1),
    ("sebasteia", "Sebasteia", 1, "infantry", 2, 5),
])
def test_failed_protection_retains_exact_marker_for_thrakion(locale, home, index, unit, symbols, seed):
    ui = _activation(seed, locale=locale)
    box = ui.gs.themata[home]
    chosen = box[index]
    assert (chosen.unit, chosen.symbols) == (unit, symbols)
    others = box[:index] + box[index + 1:]
    removed = ui.gs.meta.themata_removed.copy()

    _play(ui, "cmd_ravage", actions=1)
    rng = engine.roller_for(ui.gs)
    expected_roll = rng.d6()
    result = _play(ui, "resolve_ravage_defence", defend_with=index)
    assert result["success"] and result["themata_lost"]
    assert result["roll"] == expected_roll
    assert engine.roller_for(ui.gs).get_state() == rng.get_state()
    assert ui.gs.themata[home] == others
    assert len(ui.gs.meta.themata_removed) == len(removed) + 1
    assert ui.gs.meta.themata_removed[:-1] == removed
    marker = ui.gs.meta.themata_removed[-1]
    assert (marker.home_thema, marker.unit, marker.symbols) == (home, unit, symbols)

    # Stage a later Arts of War draw with the real pile and resolve it publicly.
    gs = GameState.from_json(ui.gs.to_json())
    gs.meta.phase, gs.meta.subphase = "levy", "levy.arts_of_war"
    gs.meta.active_player = "roman"
    gs.meta.active_card = gs.meta.active_lord = None
    gs.meta.actions_remaining = 0
    gs.meta.pending = [{"type": "event_pending_resolution", "side": "roman",
                        "card": "R13", "tags": ["immediate"]}]
    gs.roman.draw_deck.remove("R13")
    resumed = CompactInterface(LLMSession(gs))
    returned = _play(resumed, "resolve_event", card="R13",
                     parameters={"args": {"thema": home, "unit": unit}})
    assert returned["returned"] == {"thema": home, "unit": unit}
    assert resumed.gs.themata[home] == others + [marker]
    assert resumed.gs.meta.themata_removed == removed
