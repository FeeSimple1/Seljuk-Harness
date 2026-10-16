"""Complete menu coverage, privacy, version safety and explicit input contracts.

Synthetic fixtures isolate real engine windows without changing rule logic.
The full replay test exercises unmodified rules state across an actual game.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from seljuk import engine, campaign, scenarios, static_data as sd, battle
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError, _strip
from seljuk.llm.routing import current_pending, decision_side
from seljuk.llm import reference
from seljuk.state import GameState, IllegalAction


def ui(scenario="emperor_and_the_lion", seed=1, **kwargs):
    return CompactInterface(LLMSession.start_new(scenario, seed, **kwargs))


def get_all(interface, **filters):
    page = interface.actions(**filters)
    rows = list(page["entries"])
    while page["next_cursor"]:
        page = interface.actions(cursor=page["next_cursor"])
        rows.extend(page["entries"])
    return rows


def snapshot(interface):
    return (interface.gs.to_json(), deepcopy(interface._joint), deepcopy(interface._receipts),
            deepcopy(interface.findings))


def reach_muster(interface):
    for _ in range(20):
        if interface.gs.meta.subphase == "levy.muster":
            return
        raw = interface._menu()
        pick = next((m for m in raw if m["type"] == "pass_step"), raw[0])
        assert not pick.get("_unvalidated")
        interface.apply(_strip(pick), version=interface.version)
    raise AssertionError("did not reach Muster")


@pytest.mark.parametrize("scenario", scenarios.SCENARIOS)
@pytest.mark.parametrize("seed", [1, 2, 165])
def test_entire_validated_menu_is_retrievable_and_identical(scenario, seed):
    interface = ui(scenario, seed)
    for _ in range(3):
        expected, _ = engine.validated_legal_moves(interface.gs)
        before = interface.gs.to_json()
        rows = get_all(interface, limit=2)
        assert [_strip(m) for m in expected] == [m["action"] for m in rows]
        assert [bool(m.get("_unvalidated")) for m in expected] == [m["kind"] == "template" for m in rows]
        assert len({m["id"] for m in rows}) == len(rows)
        assert interface._menu() == expected  # includes EVERY original hint internally
        for kind in ("action", "template"):
            assert get_all(interface, kind=kind, limit=1) == [m for m in rows if m["kind"] == kind]
        for action_type in {m["type"] for m in expected}:
            assert get_all(interface, type=action_type, limit=1) == [m for m in rows if m["action"]["type"] == action_type]
        assert interface.gs.to_json() == before
        if rows and rows[0]["kind"] == "action":
            interface.apply(rows[0]["id"])
        else:
            break


@pytest.mark.parametrize("side", ["roman", "seljuk"])
def test_large_muster_filters_pages_stable_ids_and_no_preference_pruning(side):
    interface = ui()
    reach_muster(interface)
    if side == "roman":
        interface.apply({"type": "pass_step"}, version=interface.version)
    all_rows = get_all(interface, limit=3)
    assert len(all_rows) > 20
    for key in ("lord", "card", "target", "to"):
        for value in {r["action"][key] for r in all_rows if key in r["action"]}:
            assert get_all(interface, **{key: value}, limit=2) == [r for r in all_rows if r["action"].get(key) == value]
    counts = Counter(r["action"]["type"] for r in all_rows)
    over = interface.overview()
    assert {k: v["actions"]+v["templates"] for k, v in over["categories"].items()} == dict(counts)
    assert "entries" not in over and "LEGAL ACTIONS" not in over["briefing"]
    assert get_all(interface, q="no-such-description") == []


@pytest.mark.parametrize("which", ["id", "cursor", "raw", "plan", "detail", "reference", "inspect"])
def test_outdated_selections_rejected_without_any_state_or_log_mutation(which):
    interface = ui("manzikert")
    old = interface.version
    action_id = interface.actions()["entries"][0]["id"]
    cursor = interface.inspect("state", limit=1)["next_cursor"]
    refcursor = interface.reference("cards", limit=1)["next_cursor"]
    interface.gs.meta.actions_remaining += 1  # external edit also expires every token
    before = snapshot(interface)
    calls = {
        "id": lambda: interface.apply(action_id, parameters={"cards": []}),
        "detail": lambda: interface.details(action_id),
        "raw": lambda: interface.apply({"type": "build_plan"}, version=old),
        "plan": lambda: interface.plan([], version=old),
        "cursor": lambda: interface.actions(cursor=cursor),
        "inspect": lambda: interface.inspect("state", cursor=cursor),
        "reference": lambda: interface.reference("cards", cursor=refcursor, full=True),
    }
    with pytest.raises(InterfaceError, match="State changed"):
        calls[which]()
    assert snapshot(interface) == before


def test_no_unversioned_indices_or_direct_actions():
    interface = ui()
    before = snapshot(interface)
    for bad in (0, True, -1):
        with pytest.raises(InterfaceError):
            interface.apply(bad)
    with pytest.raises(InterfaceError, match="Supply the displayed version"):
        interface.apply({"type": "pass_step"})
    assert snapshot(interface) == before


def test_tokens_survive_unchanged_save_resume_and_then_expire(tmp_path):
    interface = ui()
    reach_muster(interface)
    page = interface.actions(limit=2)
    st_page = interface.inspect("state", limit=1)
    path = tmp_path/"resume.json"
    interface.save(path)
    loaded = CompactInterface.load(path)
    assert interface.version == loaded.version
    assert interface.actions(cursor=page["next_cursor"]) == loaded.actions(cursor=page["next_cursor"])
    assert interface.inspect("state", cursor=st_page["next_cursor"]) == loaded.inspect("state", cursor=st_page["next_cursor"])
    loaded.apply(page["entries"][0]["id"])
    with pytest.raises(InterfaceError):
        loaded.actions(cursor=page["next_cursor"])


@pytest.mark.parametrize("bad", [0, -1, 101, True, "6", 1.5])
def test_bad_page_sizes_do_not_mutate(bad):
    interface = ui()
    before = snapshot(interface)
    with pytest.raises(InterfaceError):
        interface.actions(limit=bad)
    assert snapshot(interface) == before


def test_cursor_cannot_change_query_endpoint_or_player():
    interface = ui()
    reach_muster(interface)
    first = interface.actions(type="levy_capability", limit=1)
    with pytest.raises(InterfaceError):
        interface.actions(type="pay", cursor=first["next_cursor"])
    with pytest.raises(InterfaceError):
        interface.actions(limit=2, cursor=first["next_cursor"])
    with pytest.raises(InterfaceError):
        interface.inspect("state", cursor=first["next_cursor"])
    interface.player = "roman"
    with pytest.raises(InterfaceError):
        interface.actions(cursor=first["next_cursor"])
    assert interface.actions()["entries"] == []
    with pytest.raises(InterfaceError):
        interface.apply(first["entries"][0]["id"])


@pytest.mark.parametrize("side", ["roman", "seljuk"])
@pytest.mark.parametrize("requirement", [None, "treachery_side", "treachery_no_command_side", "weather_no_command_side"])
def test_explicit_plan_contract_and_all_constraints(side, requirement):
    interface = ui("manzikert")
    gs = interface.gs
    gs.meta.active_player = side
    if requirement:
        gs.meta.notes[requirement] = side
    help_ = interface.plan_help()
    assert help_["kind"] == "template"
    assert help_["help"]["constraints"] == campaign.plan_constraints(gs, side)
    before = snapshot(interface)
    with pytest.raises(InterfaceError):
        interface.apply(help_["id"])
    assert snapshot(interface) == before
    c = help_["help"]["constraints"]
    cards = (["treachery"] if c["treachery_count"] else [])
    if c["no_command_min"]:
        cards += ["no_command"]
    # Use even an off-map Lord's physically existing command card. The menu's
    # on-map hint must not become a restrictive helper-only legality rule.
    for lid in c["command_lords"]:
        cards.extend([lid] * min(4, c["size"]-len(cards)))
    assert len(cards) == c["size"]
    interface.plan(cards, version=interface.version, lieutenants=[])
    assert interface.gs.side_decks(side).command_plan == cards


@pytest.mark.parametrize("side", ["roman", "seljuk"])
def test_treachery_forced_no_command_has_six_card_cap_not_five(side):
    interface = ui("manzikert")
    gs = interface.gs
    gs.meta.active_player = side
    gs.meta.calendar_box = 11  # summer eight plus forced opponent No Command
    gs.meta.notes["treachery_no_command_side"] = side
    gs.meta.notes["first_plan_done"] = True
    gs.meta.notes["first_turn_plan_size"] = None
    c = interface.plan_help()["help"]["constraints"]
    assert c["no_command_max"] == 6 and c["no_command_min"] == 1
    cards = ["no_command"]*6 + [c["command_lords"][0]]*(c["size"]-6)
    interface.plan(cards, version=interface.version)
    assert interface.gs.side_decks(side).command_plan == cards


def test_invalid_plan_and_lieutenant_submission_are_atomic():
    interface = ui("manzikert")
    c = interface.plan_help()["help"]["constraints"]
    cards = [c["command_lords"][0]] * c["size"]
    before = snapshot(interface)
    with pytest.raises(IllegalAction):
        interface.plan(cards, version=interface.version,
                       lieutenants=[{"lieutenant": "alp_arslan", "lower_lord": "alp_arslan"}])
    assert snapshot(interface) == before


@pytest.mark.parametrize("kind,owner", [
    ("summer_heat", "roman"), ("kleisourai", "roman"), ("basil_response", "roman"),
    ("ravage_defence", "roman"), ("assign_themata_defenders", "roman"),
    ("retain_themata", "roman"), ("winter_quarters", "roman"),
    ("approach_response", "roman"), ("loyalty_check", "seljuk"),
])
def test_decision_owner_does_not_default_to_active_attacker(kind, owner):
    gs = scenarios.load_scenario("emperor_and_the_lion")
    gs.meta.phase = "campaign"
    gs.meta.active_player = "seljuk"
    p = {"type": kind, "lord": "romanos_diogenes", "defenders": ["romanos_diogenes"],
         "locale": "melitene", "thema": "Melitene", "options": [],
         "dests": ["to_constantinople"], "attackers": ["alp_arslan"],
         "targets": ["robert_crepin"], "card": "R3"}
    if kind in ("summer_heat", "kleisourai"):
        p["reactor"] = owner
    if kind == "loyalty_check":
        p["side"] = owner
    gs.meta.pending = [p]
    assert decision_side(gs) == owner
    assert LLMSession(gs).state()["_viewing_side"] == owner
    assert f"Viewing: {owner}" in LLMSession(gs).briefing()


@pytest.mark.parametrize("card", ["R1", "R10"])
def test_repeated_roman_event_routes_seljuk_lordship_choice(card):
    gs = scenarios.load_scenario("emperor_and_the_lion")
    gs.meta.pending = [{"type": "event_pending_resolution", "card": card, "side": "roman"}]
    gs.meta.asterisks_used.append(card)
    assert decision_side(gs) == "seljuk"


def test_pending_priority_matches_engine_not_append_order():
    gs = scenarios.load_scenario("emperor_and_the_lion")
    gs.meta.pending = [{"type": "imperial_coffers", "side": "roman"},
                       {"type": "deploy_capability", "card": "S4", "side": "seljuk", "eligible": ["alp_arslan"]}]
    gs.meta.subphase = "levy.pay"
    assert current_pending(gs)["type"] == "deploy_capability"
    interface = CompactInterface(LLMSession(gs))
    assert interface.overview()["viewer"] == "seljuk"
    assert set(interface.overview()["categories"]) == {"deploy_capability"}


def approach_interface(hidden=False, attacker="seljuk"):
    gs = scenarios.load_scenario("emperor_and_the_lion", seed=27, options={"hidden_mats": hidden})
    gs.meta.phase, gs.meta.subphase = "campaign", "campaign.command"
    gs.meta.active_player = attacker
    lid = "alp_arslan" if attacker == "seljuk" else "romanos_diogenes"
    did = "romanos_diogenes" if attacker == "seljuk" else "alp_arslan"
    for name in (lid, did):
        gs.lords[name].cylinder = "melitene"
        gs.lords[name].mustered = True
    gs.meta.active_lord = lid
    gs.meta.actions_remaining = 2
    gs.meta.pending = [{"type": "approach_response", "attackers": [lid], "defenders": [did],
                        "locale": "melitene", "from": "arqa", "_owed_by": gs.lords[did].side}]
    return CompactInterface(LLMSession(gs)), did


@pytest.mark.parametrize("attacker", ["roman", "seljuk"])
def test_approach_choices_intact_and_inactive_defender_can_submit(attacker):
    interface, did = approach_interface(attacker=attacker)
    owner = interface.gs.lords[did].side
    row = interface.actions()["entries"][0]
    assert row["kind"] == "template"
    detail = interface.details(row["id"])
    assert detail["viewer"] == owner
    assert {d["action"] for d in detail["help"]["choices"][did]} >= {"stand", "avoid"}
    before = interface.gs.to_json()
    response = interface.apply(row["id"], parameters={"choices": {did: {"action": "stand"}}})
    assert response["decision_owner"] == attacker
    assert interface.gs.to_json() == before  # no speculative rolls committed
    final = interface.apply({"type": "decline_inputs"}, version=interface.version)
    assert final["applied"] == "respond_approach"
    assert not any(p["type"] == "approach_response" for p in interface.gs.meta.pending)
    assert interface.inspect("result", full=True)["data"]["combat_detail"]["battle"]["decisions"]


def test_no_default_stand_for_an_omitted_defender():
    interface, _ = approach_interface()
    before = snapshot(interface)
    with pytest.raises(InterfaceError, match="each defending Lord"):
        interface.apply(interface.actions()["entries"][0]["id"], parameters={"choices": {}})
    assert snapshot(interface) == before


def test_themata_template_retains_double_markers_and_size():
    interface = ui()
    gs = interface.gs
    gs.meta.phase, gs.meta.subphase = "campaign", "campaign.command"
    gs.meta.pending = [{"type": "assign_themata_defenders", "locale": "melitene", "_owed_by": "roman"}]
    row = interface.actions()["entries"][0]
    help_ = interface.details(row["id"])["help"]
    assert help_["max_markers"] == battle._value("melitene")
    assert [v["symbols"] for v in help_["available"]] == [v.symbols for v in gs.themata["Melitene"]]
    before = snapshot(interface)
    with pytest.raises(InterfaceError):
        interface.apply(row["id"])
    assert snapshot(interface) == before


def test_hidden_mats_hands_future_plans_history_and_pending_scripts_never_leak():
    interface, did = approach_interface(hidden=True)
    gs = interface.gs
    assert interface.viewer == "roman"
    gs.lords["alp_arslan"].forces = {"SECRET_FORCE": 991}
    gs.lords["alp_arslan"].assets.coin = 987
    gs.lords["alp_arslan"].flags["secret"] = "SECRET_FLAG"
    gs.seljuk.held_events = ["S2", "S21"]
    gs.seljuk.command_plan = ["SECRET_UNREVEALED"]
    gs.seljuk.plan_pointer = 0
    gs.history = [{"action": {"type": "build_plan", "cards": ["SECRET_HISTORY"]}, "result": {"plan": ["SECRET_HISTORY"]}}]
    gs.meta.notes["_private_script"] = "SECRET_NOTE"
    gs.meta.pending[0]["_surprise_storm"] = {"decisions": ["SECRET_SCRIPT"]}
    all_outputs = [interface.overview(), interface.actions(), interface.details(interface.actions()["entries"][0]["id"]),
                   interface.inspect("state", full=True), interface.inspect("pending", full=True),
                   interface.inspect("lord", "alp_arslan", full=True), interface.session.legal_actions()]
    encoded = json.dumps(all_outputs)
    for forbidden in ("SECRET_FORCE", "991", "987", "SECRET_FLAG", "SECRET_UNREVEALED", "SECRET_HISTORY", "SECRET_NOTE", "SECRET_SCRIPT"):
        assert forbidden not in encoded
    assert "rng_state" not in json.dumps(interface.inspect("state", full=True))
    assert "seed" not in interface.inspect("state", full=True)["data"]["meta"]
    hints = interface.actions()["entries"][0]["hints"]
    assert "_battle_holds_available" not in hints
    assert hints["_combat_inputs"]["your_role"] == "defender"
    assert gs.seljuk.held_events == ["S2", "S21"]


def test_repeated_briefing_keeps_only_three_public_action_types():
    interface = ui()
    interface.gs.history = [{"action": {"type": f"old_{i}", "secret": "SECRET"}} for i in range(20)]
    text = interface.overview()["briefing"]
    assert "old_16" not in text and "old_17; old_18; old_19" in text and "SECRET" not in text


def test_private_handoff_no_mutation_before_opponent_and_save_resume(tmp_path):
    interface, did = approach_interface()
    interface.gs.roman.held_events.append("R21")
    before = interface.gs.to_json()
    interface.apply(interface.actions()["entries"][0]["id"], parameters={
        "choices": {did: {"action": "stand"}}, "battle_events": {"roman": ["R21"]},
        "battle_decisions": [["concede", False]]})
    assert interface.viewer == "seljuk"
    assert interface.gs.to_json() == before
    assert "R21" not in json.dumps(interface.actions())
    assert "proposed_scripts" not in json.dumps(interface.details(interface.actions()["entries"][0]["id"]))
    f = tmp_path/"handoff.json"
    interface.save(f)
    restored = CompactInterface.load(f)
    assert restored.version == interface.version
    oldid = restored.actions()["entries"][1]["id"]
    result = restored.apply(oldid)
    assert result["applied"] == "respond_approach"
    with pytest.raises(InterfaceError):
        restored.apply(oldid)


def test_per_player_combat_scripts_do_not_answer_other_players_concession():
    ctx = battle.DecisionContext({"roman": [["concede", True]], "seljuk": [["concede", False]]})
    assert ctx.decide("concede", [False, True], {"side": "seljuk"}) is False
    assert ctx.decide("concede", [False, True], {"side": "roman"}) is True
    with pytest.raises(IllegalAction, match="decision_owner_missing"):
        battle.DecisionContext({"roman": []}).decide("concede", [False, True])


def test_auto_never_consumes_plan_template_or_optional_combat_inputs():
    interface = ui("manzikert")
    before = snapshot(interface)
    assert interface.auto()["auto_advanced"] == 0
    assert snapshot(interface) == before
    interface, did = approach_interface()
    interface.apply(interface.actions()["entries"][0]["id"], parameters={"choices": {did: {"action": "stand"}}})
    before = snapshot(interface)
    assert interface.auto()["auto_advanced"] == 0
    assert snapshot(interface) == before


def test_card_lord_state_and_map_have_complete_structured_access(monkeypatch):
    interface = ui()
    long_text = "Whole rule paragraph. "*700 + "MECHANICS_END"
    original = sd.card
    monkeypatch.setattr(sd, "card", lambda cid: {**original(cid), "long_rule": long_text})
    card = interface.inspect("card", "S4", full=True)["data"]
    assert card["long_rule"] == long_text and card["reference_text"] == reference.card_text("S4")
    lord = interface.inspect("lord", "alp_arslan", full=True)["data"]
    assert lord["reference"]["ratings"] == sd.lord("alp_arslan")["ratings"]
    pages = interface.inspect("map", limit=2)
    rows = list(pages["entries"])
    while pages["next_cursor"]:
        pages = interface.inspect("map", cursor=pages["next_cursor"])
        rows += pages["entries"]
    assert {r["key"] for r in rows} == set(sd.all_locale_ids())
    assert all(isinstance(r["value"], list) for r in rows)
    # Reconstruct every nested node using only the public path/page protocol.
    def reconstruct(path=""):
        page = interface.inspect("state", path=path, limit=3)
        if "data" in page:
            return page["data"]
        entries = list(page["entries"])
        while page["next_cursor"]:
            page = interface.inspect("state", cursor=page["next_cursor"])
            entries += page["entries"]
        pairs = [(e["key"], e["value"] if "value" in e else reconstruct(e["path"])) for e in entries]
        return dict(pairs) if page["node_type"] == "object" else [v for _, v in pairs]
    assert reconstruct() == interface.inspect("state", full=True)["data"]


def test_all_packaged_references_page_back_to_exact_sources():
    interface = ui()
    for name, source in reference.sources().items():
        page = interface.reference(name, limit=100)
        text = "".join(e["text"] for e in page["entries"])
        while page["next_cursor"]:
            page = interface.reference(name, cursor=page["next_cursor"])
            text += "".join(e["text"] for e in page["entries"])
        assert text == source["text"]
        raw = (Path(__file__).resolve().parents[1]/source["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == source["sha256"]
    for card in sd.cards()["cards"]:
        assert reference.card_text(card).startswith(card+".")


def test_menu_validation_runs_once_per_version_and_records_drops_once(monkeypatch):
    interface = ui()
    calls = []
    real = engine.validated_legal_moves
    def wrapped(gs):
        calls.append(1)
        kept, drops = real(gs)
        return kept, drops + [{"action": {"type": "bad"}, "code": "bad", "reason": "test"}]
    monkeypatch.setattr(engine, "validated_legal_moves", wrapped)
    interface.overview(); interface.actions(); interface.overview(); get_all(interface, limit=1)
    assert len(calls) == 1 and len(interface.findings) == 1
    assert "bad" not in interface.overview()["categories"]


@pytest.mark.parametrize('name', ['manzikert', 'showdown'])
def test_full_recorded_games_preserve_all_decisions_results_and_position(name, tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
    from llm_interface_replay import records, prepare, finish, canonical, position
    record = records()[name]
    interface = ui(record['scenario'], record['seed'])
    sides = set()
    count = 0
    for action in record['actions']:
        actor = interface.owed
        sides.add(actor)
        primary, extra, expected, control = prepare(interface.gs, action, actor)
        response, result = finish(interface, primary, extra)
        assert canonical(result) == canonical(expected), (count, action)
        assert position(interface.gs) == position(control), (count, action)
        # Every accepted step survives a state JSON round trip; full UI state,
        # receipts and identifiers are also restored repeatedly across phases.
        interface.session.gs = GameState.from_json(interface.gs.to_json())
        count += 1
        if count % 17 == 0:
            interface.save(tmp_path/'game.json')
            interface = CompactInterface.load(tmp_path/'game.json')
    assert sides == {'roman', 'seljuk'}
    assert interface.session.is_over()
    assert interface.session.winner() == record['expected_winner']
    assert scenarios.score(interface.gs) == record['expected_score']
    assert count in (132, 338)


@pytest.mark.parametrize('order', ['keep', 'swap'])
def test_bad_omens_private_inspection_precedes_explicit_order_and_survives_resume(order, tmp_path):
    interface = ui('manzikert')
    gs = interface.gs
    gs.meta.subphase = 'campaign.command'
    gs.meta.active_player = 'seljuk'
    gs.meta.active_lord = 'alp_arslan'
    gs.meta.actions_remaining = 4
    gs.meta.notes['card_full_actions'] = 4
    gs.meta.pending = []
    gs.roman.command_plan = ['romanos_diogenes', 'roussel_de_bailleul', 'no_command']
    gs.roman.plan_pointer = 0
    gs.seljuk.held_events = ['S24']
    gs.seljuk.draw_deck = [c for c in gs.seljuk.draw_deck if c != 'S24']
    page = interface.actions(type='play_hold_event')
    row = next(r for r in page['entries'] if r['action'].get('card') == 'S24')
    assert 'inspected_roman_plan_cards' not in json.dumps(interface.overview())
    before = gs.to_json()
    declared = interface.apply(row['id'])
    assert declared['pending']['inspected_roman_plan_cards'] == gs.roman.command_plan[:2]
    assert interface.gs.to_json() == before
    version = interface.version
    with pytest.raises(InterfaceError):
        interface.cancel_inputs(version=version)
    with pytest.raises(InterfaceError):
        interface.apply({'type':'decline_inputs'}, version=version)
    interface.save(tmp_path/'omens.json')
    interface = CompactInterface.load(tmp_path/'omens.json')
    assert interface.version == version
    interface.apply({'type':'supply_inputs','inputs':{'order':order}}, version=version)
    intended = ['romanos_diogenes', 'roussel_de_bailleul']
    if order == 'swap':
        intended.reverse()
    assert interface.gs.roman.command_plan[:2] == intended
    assert 'S24' not in interface.gs.seljuk.held_events
    private = interface.inspect('result', full=True)['data']['decision_result']
    assert private['kept' if order == 'keep' else 'reordered'] == intended
    interface.player = 'roman'
    assert interface.inspect('result', full=True)['data']['decision_result'] == {'private_to':'seljuk'}


def test_local_scouts_routes_enemy_selection_and_cannot_cancel():
    interface, did = approach_interface(attacker='roman')
    gs = interface.gs
    gs.roman.held_events = ['R18']
    gs.roman.draw_deck = [c for c in gs.roman.draw_deck if c != 'R18']
    row = interface.actions()['entries'][0]
    choices = interface.details(row['id'])['help']['choices'][did]
    avoid = next(ch for ch in choices if ch['action'] == 'avoid')
    before = gs.to_json()
    interface.apply(row['id'], parameters={'choices': {did: avoid}})
    assert interface.owed == 'roman'
    interface.apply({'type':'supply_inputs','inputs':{'play_local_scouts':True}}, version=interface.version)
    assert interface.owed == 'seljuk'
    assert interface.gs.to_json() == before
    assert interface.details(interface.actions()['entries'][0]['id'])['help']['avoiding_lords'] == [did]
    with pytest.raises(InterfaceError):
        interface.cancel_inputs(version=interface.version)
    with pytest.raises(InterfaceError):
        interface.apply({'type':'decline_inputs'}, version=interface.version)
    interface.apply({'type':'supply_inputs','inputs':{'local_scouts':{'lord':did,'action':'stand'}}}, version=interface.version)
    assert 'R18' not in interface.gs.roman.held_events
    assert interface.gs.roman.draw_deck.count('R18') == 1


@pytest.mark.parametrize('revealing', ['roman', 'seljuk'])
def test_loyalty_counterpayment_comes_from_owed_player_and_invalid_input_is_atomic(revealing, tmp_path):
    from tests.test_new_seed_20261012_fixes import funded_loyalty
    gs, target = funded_loyalty(revealing)
    interface = CompactInterface(LLMSession(gs))
    row = interface.actions()['entries'][0]
    assert row['action']['target'] == target
    before = interface.gs.to_json()
    interface.apply(row['id'], parameters={'coins_for':1})
    assert interface.owed != revealing
    assert interface.gs.to_json() == before
    detail = interface.details(interface.actions()['entries'][0]['id'])
    assert detail['help']['max_coins_against'] in (2,3)
    snapshot_ = snapshot(interface)
    with pytest.raises(IllegalAction):
        interface.apply({'type':'supply_inputs','inputs':{'coins_against':999}}, version=interface.version)
    assert snapshot(interface) == snapshot_
    interface.save(tmp_path/'loyalty.json')
    interface = CompactInterface.load(tmp_path/'loyalty.json')
    interface.apply({'type':'supply_inputs','inputs':{'coins_against':1}}, version=interface.version)
    check = interface.inspect('result', full=True)['data']['outcome']['loyalty']
    assert check['modified'] == check['natural']


def test_helper_public_output_is_complete_json_not_duplicate_raw_return(capsys):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
    import chatgpt_play_helper as nv
    returned = nv.start('manzikert', seed=1)
    text = capsys.readouterr().out
    assert json.loads(text) == returned
    assert 'entries' not in returned
    assert 'already printed' in repr(returned)
    row = nv.actions()['entries'][0]
    capsys.readouterr()
    rejected = nv.apply(row['id'])  # Plan template requires explicit cards
    assert rejected['error'] == 'template_parameters_required'
    assert json.loads(capsys.readouterr().out) == rejected


def test_nested_event_argument_names_remain_discoverable():
    from seljuk.llm.contracts import contract
    gs = scenarios.load_scenario('emperor_and_the_lion')
    move = {'type':'resolve_event','card':'R1','_unvalidated':True}
    detail = contract(gs, move, 'seljuk')
    assert 'lord' in detail['argument_names']
    gs.meta.phase, gs.meta.subphase = 'campaign', 'campaign.command'
    detail = contract(gs, {'type':'play_hold_event','card':'S24'}, 'seljuk')
    assert 'order' in detail['argument_names']


def test_cli_default_json_human_views_and_history_honor_decision_owner(tmp_path, capsys):
    from seljuk.cli import main
    interface, _ = approach_interface(hidden=True)
    interface.gs.lords['alp_arslan'].forces = {'SECRET_FORCE':321}
    interface.gs.history = [{'action':{'type':'build_plan','cards':['SECRET_PLAN']}}]
    path=tmp_path/'cli.json'; path.write_text(interface.gs.to_json())
    for options in (['--json'], ['--mode','verbose'], ['--lord','alp_arslan'], []):
        assert main(['state','--file',str(path),*options]) == 0
        text=capsys.readouterr().out
        assert 'SECRET_FORCE' not in text and 'SECRET_PLAN' not in text
        if options == ['--json']:
            assert json.loads(text)['_viewing_side'] == 'roman'
    assert main(['history','--file',str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == {'type':'build_plan'}
    assert main(['history','--file',str(path),'--raw']) == 0
    assert 'SECRET_PLAN' in capsys.readouterr().out
