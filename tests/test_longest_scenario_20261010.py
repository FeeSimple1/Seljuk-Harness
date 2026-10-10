"""Four longest-scenario findings: real game checkpoints and neighboring controls.

The compact fixture is from f1cd077 (only history was removed). It deliberately
retains bad/stale positions where needed to test direct handler validation.
"""
from collections import Counter
import json
from pathlib import Path

import pytest

from seljuk import actions, campaign, engine, events, scenarios, static_data as sd
from seljuk.invariants import check_invariants
from seljuk.state import GameState, IllegalAction, ThemataMarker

FIXTURE = Path(__file__).parent / "fixtures" / "longest_scenario_20261010.json"


def checkpoint(name):
    record = json.loads(FIXTURE.read_text())["positions"][name]
    return GameState.model_validate(record["state"]), record["action"]


def physical_cards(gs):
    cards = Counter()
    for side in ("roman", "seljuk"):
        d = gs.side_decks(side)
        cards.update(d.draw_deck + d.capabilities_in_play + d.held_events + d.this_campaign_events)
    for lord in gs.lords.values():
        cards.update(lord.capabilities)
    for p in gs.meta.pending:
        if p.get("type") in ("deploy_capability", "event_pending_resolution"):
            cards.update([p["card"]])
    return cards


def test_el01_real_battle_requires_investment_before_recovery():
    gs, action = checkpoint("hama")
    result = engine.apply_action(gs, action)
    assert result["battle"]["winner"] == "attacker"
    assert gs.lords["ibn_khan"].besieged
    assert result["pending"] == "besiege_or_bypass"
    assert gs.meta.active_lord == "chatatourios" and gs.meta.actions_remaining == 0
    assert gs.meta.subphase == "campaign.command"  # not already feeding/paying
    assert {m["choice"] for m in engine.legal_moves(gs)} == {"besiege", "bypass"}
    assert not check_invariants(gs)


@pytest.mark.parametrize("choice", ["besiege", "bypass"])
def test_el01_either_choice_survives_reload_and_finishes_card(choice):
    gs, action = checkpoint("hama")
    engine.apply_action(gs, action)
    gs = GameState.from_json(gs.to_json())
    result = engine.apply_action(gs, {"type": "besiege_bypass", "choice": choice})
    assert result["action"] == choice
    assert gs.locales["hama"].siege_markers == (1 if choice == "besiege" else 0)
    assert gs.locales["hama"].bypass == (choice == "bypass")
    assert gs.lords["chatatourios"].bypassed == (choice == "bypass")
    assert gs.meta.subphase == "campaign.fpd_pay" and gs.meta.active_lord is None
    assert not any(p["type"] == "besiege_or_bypass" for p in gs.meta.pending)
    assert not check_invariants(gs)


@pytest.mark.parametrize("action", [
    {"type": "end_activation"}, {"type": "cmd_pass"},
    {"type": "fpd_done"}, {"type": "cmd_storm", "lord": "chatatourios"},
])
def test_el01_mandatory_aftermath_cannot_be_skipped(action):
    gs, opening = checkpoint("hama")
    engine.apply_action(gs, opening)
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="pending_decision"):
        engine.apply_action(gs, action)
    assert gs.to_json() == before


def test_el01_invalid_choice_does_not_delete_pending_or_mutate_state():
    gs, action = checkpoint("hama")
    engine.apply_action(gs, action)
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="bad_choice"):
        engine.apply_action(gs, {"type": "besiege_bypass", "choice": "skip"})
    assert gs.to_json() == before


@pytest.mark.parametrize("choice", ["besiege", "bypass"])
def test_el01_winter_aftermath_uses_pending_menu_and_completes_activation(choice):
    gs, action = checkpoint("hama")
    gs.meta.phase = "winter"
    gs.meta.subphase = "winter.activation"
    gs.meta.notes["winter_holders"] = ["seljuk"]  # next holder, don't finalize Winter here
    engine.apply_action(gs, action)
    assert {m["choice"] for m in engine.legal_moves(gs)} == {"besiege", "bypass"}
    engine.apply_action(gs, {"type": "besiege_bypass", "choice": choice})
    assert gs.meta.active_lord is None and gs.meta.active_player == "seljuk"
    assert not any(p["type"] == "besiege_or_bypass" for p in gs.meta.pending)


def test_el01_new_roman_investment_offers_themata_before_recovery():
    gs, action = checkpoint("hama")
    # Same real battle with allegiances mirrored: a Roman Hama needs Themata.
    for lord in gs.lords.values():
        if lord.cylinder == "hama":
            lord.side = "roman" if lord.side == "seljuk" else "seljuk"
    gs.locales["hama"].conquered_side = "roman"
    gs.meta.active_player = "seljuk"
    # Hama is outside the printed Themata regions. Use a genuine Roman locale
    # for this neighboring control while retaining the real battle forces/RNG.
    for lord in gs.lords.values():
        if lord.cylinder == "hama":
            lord.cylinder = "theodosiopolis"
    gs.locales["theodosiopolis"].siege_markers = 0
    gs.locales["theodosiopolis"].bypass = False
    gs.locales["theodosiopolis"].themata_defending.clear()
    gs.meta.pending[0]["locale"] = "theodosiopolis"
    gs.themata["Iberia"] = [ThemataMarker(unit="tagmata", symbols=1)]
    engine.apply_action(gs, action)
    engine.apply_action(gs, {"type": "besiege_bypass", "choice": "besiege"})
    assert [m["type"] for m in engine.legal_moves(gs)] == ["assign_themata_defenders"]
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="pending_decision"):
        engine.apply_action(gs, {"type": "end_activation"})
    assert gs.to_json() == before
    engine.apply_action(gs, {"type": "assign_themata_defenders", "markers": [0]})
    assert len(gs.locales["theodosiopolis"].themata_defending) == 1
    assert gs.meta.subphase == "campaign.fpd_pay"


def test_el02_real_treachery_menu_discloses_required_no_command():
    gs, _ = checkpoint("treachery")
    menu = next(m for m in engine.legal_moves(gs) if m["type"] == "build_plan")
    assert menu["_plan_size"] == 8
    assert menu["_no_command_required"] is True
    assert "No Command" in menu["_desc"]


def test_el02_real_invalid_plan_rejected_before_mutation():
    gs, _ = checkpoint("treachery")
    action = json.loads(FIXTURE.read_text())["positions"]["treachery"]["illegal_action"]
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="treachery_no_command"):
        engine.apply_action(gs, action)
    assert gs.to_json() == before


def test_el02_recorded_compliant_plan_still_accepted():
    gs, action = checkpoint("treachery")
    assert engine.apply_action(gs, action)["ok"]
    assert gs.roman.command_plan.count("no_command") == 1


@pytest.mark.parametrize("side", ["seljuk", "roman"])
@pytest.mark.parametrize("source", ["treachery", "weather", "none"])
def test_el02_both_sides_obligation_matches_menu_and_validator(side, source):
    gs = scenarios.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.pending.clear()
    campaign.start_campaign(gs)
    gs.meta.active_player = side
    if source != "none":
        gs.meta.notes[source + "_no_command_side"] = side
    menu = engine.legal_moves(gs)[0]
    assert menu["_no_command_required"] == (source != "none")
    lords = sd.command_decks()[side]["lords_with_cards"]
    n = campaign.plan_size(gs, side)
    cards = [lords[0]] * 4 + [lords[1]] * (n-4)
    action = {"type": "build_plan", "side": side, "cards": cards}
    if source == "none":
        assert engine.apply_action(gs, action)["ok"]
    else:
        before = gs.to_json()
        with pytest.raises(IllegalAction, match=source + "_no_command"):
            engine.apply_action(gs, action)
        assert gs.to_json() == before
        action["cards"][-1] = "no_command"
        assert engine.apply_action(gs, action)["ok"]


@pytest.mark.parametrize("card", ["R8", "S16", "S19"])
def test_el02_all_treachery_events_force_the_opponents_no_command(card):
    gs = scenarios.load_scenario("emperor_and_the_lion")
    events._RESOLVERS[card](gs, {}, engine.roller_for(gs))
    enemy = "seljuk" if card == "R8" else "roman"
    gs.meta.pending.clear()
    campaign.start_campaign(gs)
    gs.meta.active_player = enemy
    assert engine.legal_moves(gs)[0]["_no_command_required"]
    assert not campaign.no_command_required(gs, "roman" if enemy == "seljuk" else "seljuk")


@pytest.mark.parametrize("card", ["S9", "R17"])
def test_el03_saved_reset_preserves_this_campaign_cards(card):
    gs, action = checkpoint("cards")
    assert physical_cards(gs)[card] == 1
    engine.apply_action(gs, action)
    assert physical_cards(gs)[card] == 1
    assert not check_invariants(gs)


def test_el03_reset_conserves_complete_decks_and_is_idempotent():
    gs = scenarios.load_scenario("emperor_and_the_lion", seed=1)
    baseline = physical_cards(gs)
    for side, cards in (("seljuk", ["S9", "S13", "S17"]), ("roman", ["R17"])):
        for card in cards:
            gs.side_decks(side).draw_deck.remove(card)
            actions._classify_drawn_event(gs, side, card, engine.roller_for(gs))
    assert physical_cards(gs) == baseline
    campaign._reset(gs)
    assert physical_cards(gs) == baseline
    assert not gs.seljuk.this_campaign_events and not gs.roman.this_campaign_events
    assert not any(k in gs.meta.notes for k in ("weather_pass_block", "moustache_campaign", "peace_offering_season"))
    decks = (list(gs.seljuk.draw_deck), list(gs.roman.draw_deck))
    campaign._reset(gs)
    assert decks == (gs.seljuk.draw_deck, gs.roman.draw_deck)
    assert physical_cards(gs) == baseline
    # The same physical card can be drawn/used and returned again next season.
    gs.seljuk.draw_deck.remove("S9")
    actions._classify_drawn_event(gs, "seljuk", "S9", engine.roller_for(gs))
    assert gs.meta.notes["moustache_campaign"]
    campaign._reset(gs)
    assert physical_cards(gs) == baseline


def test_el04_real_avoid_clears_siege_and_returns_exact_themata_immediately():
    gs, action = checkpoint("relief")
    site = gs.locales["theodosiopolis"]
    old_markers = list(site.themata_defending)
    before = {k: len(v) for k,v in gs.themata.items()}
    homes = Counter(m.home_thema for m in old_markers)
    engine.apply_action(gs, action)
    assert actions.current_allegiance(gs, "theodosiopolis") == "roman"
    assert site.siege_markers == 0 and not site.bypass and not site.themata_defending
    for home, count in homes.items():
        assert len(gs.themata[home]) == before[home] + count
    assert all(m.home_thema is None for m in old_markers)
    assert gs.lords["alp_arslan"].cylinder == "mempet"
    assert not check_invariants(gs)


@pytest.mark.parametrize("command", ["cmd_storm", "cmd_siege"])
def test_el04_raw_and_validated_menus_do_not_offer_friendly_attack(command):
    gs, _ = checkpoint("stale_relief")
    assert not any(m["type"] == command for m in engine.legal_moves(gs))
    kept, dropped = engine.validated_legal_moves(gs)
    assert not any(m["type"] == command for m in kept)
    assert not any(d["action"]["type"] == command for d in dropped)


@pytest.mark.parametrize("command", ["cmd_storm", "cmd_siege"])
def test_el04_direct_friendly_attack_rejected_without_any_damage(command):
    gs, _ = checkpoint("stale_relief")
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="not_besieging"):
        engine.apply_action(gs, {"type": command, "lord": "romanos_diogenes"})
    assert gs.to_json() == before


@pytest.mark.parametrize("side,loc", [("seljuk", "theodosiopolis"), ("roman", "ani")])
def test_el04_enemy_siege_still_legal_and_uses_current_allegiance(side, loc):
    gs = scenarios.load_scenario("emperor_and_the_lion")
    lid = "alp_arslan" if side == "seljuk" else "romanos_diogenes"
    lord = gs.lords[lid]
    lord.mustered = True; lord.cylinder = loc; lord.besieged = False
    gs.locales[loc].siege_markers = 1
    assert campaign._besieging(gs, lord)
    gs.locales[loc].conquered_side = side
    assert not campaign._besieging(gs, lord)


def test_el04_remaining_besieger_preserves_investment():
    gs, action = checkpoint("relief")
    # Another enemy remains at the stronghold; relief is not complete yet.
    lord = gs.lords["sanduq_al_turki"]
    lord.mustered = True; lord.cylinder = "theodosiopolis"; lord.side = "seljuk"
    gs.lords["alp_arslan"].cylinder = "mempet"
    original = gs.locales["theodosiopolis"].model_dump()
    campaign._refresh_invest(gs, "theodosiopolis")
    assert gs.locales["theodosiopolis"].model_dump() == original


def test_el04_relief_clears_bypass_and_frees_inside_lords():
    gs, _ = checkpoint("stale_relief")
    site = gs.locales["theodosiopolis"]
    site.siege_markers = 0; site.bypass = True
    gs.lords["romanos_diogenes"].besieged = True
    campaign._refresh_invest(gs, "theodosiopolis")
    assert not site.bypass and not site.themata_defending
    assert not gs.lords["romanos_diogenes"].besieged


def test_el04_fort_marker_investment_also_clears_on_relief():
    gs = scenarios.load_scenario("emperor_and_the_lion")
    loc = next(k for k in gs.locales if not sd.locale(k).get("is_stronghold")
               and not any(l.cylinder == k for l in gs.lords.values()))
    gs.locales[loc].fort_marker = True
    gs.locales[loc].siege_markers = 2
    campaign._refresh_invest(gs, loc)
    assert gs.locales[loc].siege_markers == 0
    assert gs.locales[loc].fort_marker


def test_control_bad_avoid_is_rejected_without_mutation():
    gs, _ = checkpoint("relief")
    before = gs.to_json()
    with pytest.raises(IllegalAction):
        engine.apply_action(gs, {"type": "respond_approach",
            "choices": {"alp_arslan": {"action": "avoid", "to": "ani"}}})
    assert gs.to_json() == before
