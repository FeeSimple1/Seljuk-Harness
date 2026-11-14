"""Native Vassal and Weather sequences, and staged random discard coverage."""

from collections import Counter
from random import Random
from unittest.mock import Mock

import pytest

from seljuk import campaign, engine, scenarios
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface
from seljuk.llm.session import LLMSession
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction

CHATATOURIOS = "chatatourios"
LEVY_VASSAL = {"type": "levy_vassal", "lord": CHATATOURIOS, "vassal_index": 0}
PASS = {"type": "pass_step"}


def _advance_until(session, reached):
    """Keep cards at Reset and decline optional actions between decisions."""
    priority = ("pass_step", "cmd_pass", "fpd_done", "reset_done",
                "pass_imperial_coffers", "decline_summer_heat")
    for _ in range(160):
        if reached(session.gs.meta):
            return
        moves = engine.legal_moves(session.gs)
        move = next((m for kind in priority for m in moves if m["type"] == kind), moves[0])
        assert move["type"] not in {"build_plan", "resolve_event"}, move
        session.apply({key: value for key, value in move.items() if not key.startswith("_")})
    pytest.fail(f"Did not reach the decision at {session.gs.meta.subphase}")


def _plan(session, side, cards):
    session.apply({"type": "build_plan", "side": side, "cards": cards})


def _end_activation(session):
    session.apply({"type": "end_activation"})
    _advance_until(session, lambda meta: meta.subphase != "campaign.fpd_pay")


def _first_summer(seed, *, advanced=False, expiry=None):
    session = LLMSession.start_new("emperor_and_the_lion", seed=seed,
                                   options={"vassal_service": advanced})
    if expiry:
        _advance_until(session, lambda meta: meta.subphase == "levy.muster"
                        and meta.active_player == "roman")
        assert LEVY_VASSAL in [
            {k: v for k, v in move.items() if not k.startswith("_")}
            for move in engine.legal_moves(session.gs)
        ]
        session.apply(LEVY_VASSAL)
    _advance_until(session, lambda meta: meta.subphase == "campaign.plan")
    if expiry == "campaign":
        _plan(session, "seljuk", ["alp_arslan"] * 2 + ["ibn_khan"] + ["no_command"] * 4)
        _plan(session, "roman", [CHATATOURIOS] * 3 + ["no_command"] * 4)
        _end_activation(session)  # Alp Arslan
        # Save a Coin to Pay in Summer. The second March uses up Service
        # through unpaid Feed so the Vassal expires before the Campaign ends.
        session.apply({"type": "cmd_tax", "lord": CHATATOURIOS})
        _advance_until(session, lambda meta: meta.subphase != "campaign.fpd_pay")
        for destination in ("mopsuestia", "antioch"):
            _end_activation(session)  # Seljuk
            session.apply({"type": "cmd_march", "lord": CHATATOURIOS,
                           "to": destination, "way_type": "road"})
            _end_activation(session)  # Roman
        lord = session.gs.lords[CHATATOURIOS]
        assert session.gs.meta.phase == "campaign"
        assert lord.vassals[0].unready and not lord.vassals[0].levied
        assert lord.service_box == 2 and lord.forces["tagmata"] == 1
    else:
        _plan(session, "seljuk", ["no_command"] * 5 + ["alp_arslan"] * 2)
        _plan(session, "roman", ["no_command"] * 5 + ["romanos_diogenes"] * 2)
    _advance_until(session, lambda meta: meta.calendar_box == 2)
    assert not check_invariants(session.gs)
    return session


def _resolve(session, card, **args):
    return session.apply({"type": "resolve_event", "card": card, "args": args})


def _roundtrip(session, tmp_path):
    path = tmp_path / "checkpoint.json"
    session.save(path)
    restored = LLMSession.load(path)
    assert restored.gs.to_json() == session.gs.to_json()
    return restored


@pytest.mark.parametrize("expiry,advanced", [("levy", True), ("campaign", True), ("levy", False)])
def test_vassal_misses_the_ensuing_muster(tmp_path, expiry, advanced):
    session = _first_summer(1, advanced=advanced, expiry=expiry)
    lord = session.gs.lords[CHATATOURIOS]
    assert lord.vassals[0].unready == (expiry == "campaign")
    _resolve(session, "R14")
    session.apply(PASS)  # Seljuk Pay
    if expiry == "campaign":
        session.apply({"type": "pay", "payer": CHATATOURIOS, "target": CHATATOURIOS,
                       "asset": "coin", "amount": 1})
        assert lord.vassals[0].unready and lord.service_box == 3
    session.apply(PASS)  # Roman Pay, then automatic Disband
    assert session.gs.meta.subphase == "levy.muster"
    assert lord.vassals[0].unready == advanced
    session.apply(PASS)  # Finishing Seljuk Muster does not flip Roman markers.
    assert lord.vassals[0].unready == advanced

    ui = CompactInterface(_roundtrip(session, tmp_path))
    assert ui.gs.meta.active_player == "roman"
    assert not check_invariants(ui.gs)
    lord = ui.gs.lords[CHATATOURIOS]
    slot = lord.vassals[0]
    assert slot.levied == (not advanced)
    assert slot.service_box is None
    assert lord.forces["tagmata"] == (1 if advanced else 2)
    own_moves = ui.actions(type="levy_vassal", lord=CHATATOURIOS)["entries"]
    assert [entry["action"]["vassal_index"] for entry in own_moves] == [1, 2, 3]
    assert not any(m["type"] == "levy_vassal" and m["lord"] == CHATATOURIOS
                   and m["vassal_index"] == 0 for m in engine.legal_moves(ui.gs))
    before = ui.gs.to_json(), ui.version
    with pytest.raises(IllegalAction) as error:
        ui.apply(LEVY_VASSAL, version=ui.version)
    assert error.value.code == ("vassal_unready" if advanced else "vassal_unavailable")
    assert (ui.gs.to_json(), ui.version) == before
    ui.apply(own_moves[0]["id"])
    assert ui.gs.lords[CHATATOURIOS].vassals[1].levied
    ui.session.apply(PASS)  # The Roman markers flip at the end of Roman Muster.
    assert ui.gs.meta.subphase == "levy.call_to_arms"
    assert not ui.gs.lords[CHATATOURIOS].vassals[0].unready
    _roundtrip(ui.session, tmp_path)

    if advanced:
        # Chatatourios Taxes during Summer, then Pays in Autumn so his
        # original marker can Muster again on the same mat.
        ui.session.apply(PASS)
        ui.session.apply(PASS)
        for side, actor in (("seljuk", "alp_arslan"), ("roman", CHATATOURIOS)):
            size = campaign.plan_size(ui.gs, side)
            _plan(ui.session, side, [actor] * (size - 5) + ["no_command"] * 5)
        _end_activation(ui.session)
        ui.session.apply({"type": "cmd_tax", "lord": CHATATOURIOS})
        _advance_until(ui.session, lambda meta: meta.calendar_box == 3)
        _resolve(ui.session, "S5", markers=[
            {"thema": "Boukellarion", "marker_index": 0},
            {"thema": "Boukellarion", "marker_index": 1},
        ])
        _resolve(ui.session, "S15")  # No eligible Themata.
        _resolve(ui.session, "R16", lord="romanos_diogenes")
        ui.session.apply(PASS)
        ui.session.apply({"type": "pay", "payer": CHATATOURIOS, "target": CHATATOURIOS,
                          "asset": "coin", "amount": 1})
        ui.session.apply(PASS)
        ui.session.apply(PASS)
        entries = ui.actions(type="levy_vassal", lord=CHATATOURIOS)["entries"]
        remuster = next(entry for entry in entries if entry["action"] == LEVY_VASSAL)
        ui.apply(remuster["id"])
        assert ui.gs.lords[CHATATOURIOS].vassals[0].service_box == 4
        assert not check_invariants(ui.gs)
        replay = LLMSession.start_new("emperor_and_the_lion", seed=1,
                                      options={"vassal_service": True})
        for entry in ui.gs.history:
            replay.apply(entry["action"])
        assert replay.gs.to_json() == ui.gs.to_json()


@pytest.mark.parametrize("seed,required,legacy", [
    (41, (True, True), False), (41, (True, True), True),
    (6, (True, False), False), (16, (False, True), False),
])
def test_each_summer_weather_event_requires_an_enemy_no_command(tmp_path, seed, required, legacy):
    session = _first_summer(seed)
    if seed == 41:
        _resolve(session, "S12", lord=CHATATOURIOS, what="service", direction="right")
        _resolve(session, "R10")
    elif seed == 6:
        _resolve(session, "R5", lord="alp_arslan", what="service", direction="right")
    else:
        _resolve(session, "R13")
    _advance_until(session, lambda meta: meta.subphase == "campaign.plan")
    assert ("R17" in session.gs.roman.this_campaign_events) == required[0]
    assert ("S17" in session.gs.seljuk.this_campaign_events) == required[1]
    if legacy:
        # Older saves of the same double draw recorded only this obligation.
        session.gs.meta.notes["weather_no_command_side"] = "seljuk"
    ui = CompactInterface(_roundtrip(session, tmp_path))
    all_lord = {
        "seljuk": ["alp_arslan"] * 4 + ["arisighi"] * 4 + ["ibn_khan"],
        "roman": ["romanos_diogenes"] * 4 + ["nikephoros_bryennios"] * 4 + [CHATATOURIOS],
    }
    for side, forced in zip(("seljuk", "roman"), required, strict=True):
        entry, = ui.actions(type="build_plan")["entries"]
        assert entry["action"]["side"] == side
        hints = entry["hints"]["_constraints"]
        assert hints["size"] == 9
        assert hints["no_command_min"] == int(forced)
        assert hints["no_command_reasons"] == (["Unpredictable Weather"] if forced else [])
        plan = all_lord[side]
        if forced:
            before = ui.gs.to_json(), ui.version
            with pytest.raises(IllegalAction, match="weather_no_command"):
                ui.apply(entry["id"], parameters={"cards": plan})
            assert (ui.gs.to_json(), ui.version) == before
            plan = plan[:-1] + ["no_command"]
        ui.apply(entry["id"], parameters={"cards": plan})
        assert ui.gs.side_decks(side).command_plan == plan
    assert not check_invariants(ui.gs)
    _roundtrip(ui.session, tmp_path)

    if seed == 41 and not legacy:
        replay = LLMSession.start_new("emperor_and_the_lion", seed=seed)
        for entry in ui.gs.history:
            replay.apply(entry["action"])
        assert replay.gs.to_json() == ui.gs.to_json()
        _advance_until(ui.session, lambda meta: meta.calendar_box == 3)
        assert "R17" not in ui.gs.roman.this_campaign_events
        assert "S17" not in ui.gs.seljuk.this_campaign_events
        for side in ("seljuk", "roman"):
            assert not campaign.no_command_required(ui.gs, side)


def test_summer_weather_preserves_existing_treachery_plan_constraints():
    state = scenarios.load_scenario("emperor_and_the_lion")
    state.meta.calendar_box = 2
    for side, card in (("seljuk", "S17"), ("roman", "R17")):
        state.side_decks(side).draw_deck.remove(card)
        state.side_decks(side).this_campaign_events.append(card)
    state.meta.notes.update(weather_plan9=True, treachery_side="seljuk",
                            treachery_no_command_side="roman")
    campaign.start_campaign(state)
    seljuk = campaign.plan_constraints(state, "seljuk")
    roman = campaign.plan_constraints(state, "roman")
    assert (seljuk["size"], seljuk["treachery_count"], seljuk["no_command_min"]) == (10, 1, 1)
    assert (roman["size"], roman["treachery_count"], roman["no_command_min"]) == (10, 0, 1)
    assert roman["no_command_max"] == 6
    assert roman["no_command_reasons"] == ["Treachery", "Unpredictable Weather"]


DISCARD_CASES = [
    ("R11", "manzikert", "roman", "seljuk", ["S1", "S2", "S3", "S4", "S6", "S10", "S18", "S21"]),
    ("S11", "specter_of_norman_betrayal", "seljuk", "roman",
     ["R3", "R4", "R6", "R9", "R18", "R21", "R23", "R24"]),
]


def _held_discard_session(card, scenario, owner, victim, hand):
    """Stage an accumulated hand with one copy of each physical card."""
    state = scenarios.load_scenario(scenario, seed=7)
    staged = {card, *hand}
    for deck in (state.seljuk, state.roman):
        for zone in (deck.draw_deck, deck.held_events, deck.capabilities_in_play,
                     deck.this_campaign_events):
            zone[:] = [cid for cid in zone if cid not in staged]
    for lord in state.lords.values():
        lord.capabilities[:] = [cid for cid in lord.capabilities if cid not in staged]
    state.side_decks(victim).held_events = list(hand)
    state.meta.phase, state.meta.subphase = "levy", "levy.pay"
    state.meta.active_player = "seljuk"
    state.meta.pending = [{"type": "event_pending_resolution", "side": owner,
                           "card": card, "tags": ["immediate"]}]
    return LLMSession(state)


@pytest.mark.parametrize("size", [1, 4, 5, 7, 8])
@pytest.mark.parametrize("card,scenario,owner,victim,full_hand", DISCARD_CASES)
def test_random_discard_uses_every_index_with_the_same_weight(
    monkeypatch, size, card, scenario, owner, victim, full_hand,
):
    hand = full_hand[:size]
    draw = Mock(side_effect=range(size))
    monkeypatch.setattr(DiceRoller, "randbelow", draw, raising=False)
    selected = Counter()
    for index in range(size):
        session = _held_discard_session(card, scenario, owner, victim, hand)
        deck = session.gs.side_decks(victim)
        prior_deck = list(deck.draw_deck)
        result = _resolve(session, card)
        assert result["discarded_held"] == hand[index]
        selected[result["discarded_held"]] += 1
        assert deck.held_events == hand[:index] + hand[index + 1:]
        assert deck.draw_deck == prior_deck + [hand[index]]
        assert not check_invariants(session.gs)
    assert selected == Counter(hand)
    assert draw.call_count == size
    assert all(call.args == (size,) for call in draw.call_args_list)


@pytest.mark.parametrize("card,scenario,owner,victim,hand", DISCARD_CASES)
def test_seeded_draw_and_rng_continue_identically_after_load(tmp_path, card, scenario, owner, victim, hand):
    session = _held_discard_session(card, scenario, owner, victim, hand)
    restored = _roundtrip(session, tmp_path)
    version, stream, spare = session.gs.meta.rng_state
    expected_rng = Random()
    expected_rng.setstate((version, tuple(stream), spare))
    expected = hand[expected_rng.randrange(len(hand))]
    ui = CompactInterface(session)
    entry, = ui.actions(type="resolve_event", card=card)["entries"]
    ui.apply(entry["id"], parameters={"args": {}})
    result = ui.gs.history[-1]["result"]
    assert result["discarded_held"] == expected
    assert _resolve(restored, card) == result
    assert restored.gs.to_json() == ui.gs.to_json()
    assert engine.roller_for(ui.gs).get_state() == expected_rng.getstate()


@pytest.mark.parametrize("cause", ["empty_hand", "wrong_allegiance"])
@pytest.mark.parametrize("card,scenario,owner,victim,hand", DISCARD_CASES)
def test_random_discard_no_op_leaves_hand_and_rng_intact(cause, card, scenario, owner, victim, hand):
    session = _held_discard_session(card, scenario, owner, victim, hand if cause == "wrong_allegiance" else [])
    if cause == "wrong_allegiance":
        if card == "R11":
            session.gs.lords["arisighi"].side = "seljuk"
        else:
            for lord in ("robert_crepin", "roussel_de_bailleul"):
                session.gs.lords[lord].side = "roman"
    deck = session.gs.side_decks(victim)
    before = deck.model_dump(), engine.roller_for(session.gs).get_state()
    assert _resolve(session, card)["no_op"]
    assert (deck.model_dump(), engine.roller_for(session.gs).get_state()) == before
