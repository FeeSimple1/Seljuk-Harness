"""Phase 6: Winter Campaign / Winter March (R9/S18) pre-Bounty activation window."""
import pytest

from seljuk import scenarios as S, engine, campaign
from seljuk.engine import IllegalAction
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.session import LLMSession
from seljuk.state import GameState
from tests.reset_helpers import keep_reset_cards


def _settle_winter_quarters(gs):
    """Resolve any queued 4.7.6 Winter Quarters choices (first Seat)."""
    while any(p["type"] == "winter_quarters" for p in gs.meta.pending):
        p = next(p for p in gs.meta.pending if p["type"] == "winter_quarters")
        engine.apply_action(gs, {"type": "winter_quarters", "lord": p["lord"], "dest": p["dests"][0]})


def _at_winter_end(seed=1, held_side="roman", card="R9"):
    gs = S.load_scenario("emperor_and_the_lion", seed=seed)
    gs.meta.calendar_box = 3  # an Autumn / Winter box, not final
    gs.meta.phase = "campaign"
    gs.side_decks(held_side).held_events = [card]
    campaign._end_campaign(gs)
    keep_reset_cards(gs)
    return gs


def test_winter_window_opens_when_holding_r9():
    gs = _at_winter_end(card="R9", held_side="roman")
    assert gs.meta.phase == "winter" and gs.meta.subphase == "winter.activation"
    assert gs.meta.active_player == "roman"
    moves = engine.legal_moves(gs)
    assert any(m["type"] == "winter_activate" for m in moves)
    assert any(m["type"] == "winter_proceed" for m in moves)


def test_winter_proceed_resolves_winter_and_advances():
    gs = _at_winter_end()
    engine.apply_action(gs, {"type": "winter_proceed"})
    _settle_winter_quarters(gs)   # 4.7.6 Seat choices may pend first
    # Winter resolved -> advance to the next Turn's Levy (box 4) or game over.
    assert gs.meta.phase in ("levy", "game_over")
    if gs.meta.phase == "levy":
        assert gs.meta.calendar_box == 4


def test_winter_activate_then_end_advances():
    gs = _at_winter_end()
    # Activate a mustered Roman Lord, then end the activation.
    rom = next(lid for lid, l in gs.lords.items() if l.mustered and l.side == "roman")
    engine.apply_action(gs, {"type": "winter_activate", "lord": rom})
    assert gs.meta.active_lord == rom and gs.meta.subphase == "winter.activation"
    assert "R9" not in gs.roman.held_events  # consumed
    engine.apply_action(gs, {"type": "end_activation"})
    _settle_winter_quarters(gs)   # 4.7.6 Seat choices may pend first
    assert gs.meta.phase in ("levy", "game_over")


def test_no_winter_window_without_the_card():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 3; gs.meta.phase = "campaign"
    gs.roman.held_events = []; gs.seljuk.held_events = []
    campaign._end_campaign(gs)
    # No R9/S18 -> no ACTIVATION window; only the 4.7.6 Quarters choices pend.
    assert gs.meta.subphase != "winter.activation"
    _settle_winter_quarters(gs)
    assert gs.meta.phase in ("levy", "game_over")


def _bounty_winter_position(blocked):
    gs = S.load_scenario("showdown_in_anatolia", seed=7)
    # Autumn 1070 after Reset, at the choice to play Winter Campaign (R9).
    gs.meta.calendar_box = 9
    gs.meta.phase, gs.meta.subphase = "winter", "winter.activation"
    gs.meta.active_player = "roman"
    gs.meta.notes["winter_holders"] = ["roman"]
    gs.roman.draw_deck.remove("R9")
    gs.roman.held_events.append("R9")
    for lord in gs.lords.values():
        if lord.mustered:
            lord.service_box = max(10, lord.service_box or 10)
    gs.lords["alp_arslan"].cylinder = "to_mosul_and_baghdad"
    if blocked:
        manuel = gs.lords["manuel_komnenos"]
        manuel.cylinder, manuel.bypassed = "ani", True
        gs.locales["ani"].bypass = True
    return gs


@pytest.mark.parametrize("stay", [True, False])
def test_winter_quarters_elections_follow_the_current_lord_and_side(stay):
    gs = _bounty_winter_position(blocked=False)
    manuel = "manuel_komnenos"
    gs.lords[manuel].cylinder = "sebasteia"
    gs.roman.draw_deck.remove("R15")
    gs.lords[manuel].capabilities.append("R15")
    engine.apply_action(gs, {"type": "winter_proceed"})
    assert gs.meta.subphase == "winter.quarters"
    before = gs.to_json()

    def resolve(state):
        ui = CompactInterface(LLMSession(state))
        version = ui.version
        assert ui.owed == "seljuk"
        alp_choices = ui.actions(type="winter_quarters")["entries"]
        assert {row["action"]["dest"] for row in alp_choices} == {"ani", "to_mosul_and_baghdad"}
        assert all(row["action"]["lord"] == "alp_arslan" for row in alp_choices)
        for args, code in [
            ({"lord": manuel, "dest": "to_constantinople"}, "wrong_lord"),
            ({"lord": "emir_of_arran", "stay": True}, "wrong_lord"),
            ({"lord": "alp_arslan", "dest": "ani", "side": "roman"}, "wrong_side"),
        ]:
            action = {"type": "winter_quarters", **args}
            with pytest.raises(IllegalAction) as rejected:
                engine.apply_action(state, action)
            assert rejected.value.code == code
            with pytest.raises(IllegalAction) as rejected:
                ui.apply(action, version=version)
            assert rejected.value.code == code
            assert ui.gs.to_json() == before and ui.version == version

        ui.apply(next(row["id"] for row in alp_choices if row["action"]["dest"] == "ani"))
        with pytest.raises(InterfaceError) as stale:
            ui.apply(alp_choices[0]["id"])
        assert stale.value.code == "stale_selection"
        assert ui.owed == "seljuk"
        emir_choice = next(row for row in ui.actions(type="winter_quarters")["entries"]
                           if row["action"].get("stay"))
        assert emir_choice["action"]["lord"] == "emir_of_arran"
        ui.apply(emir_choice["id"])
        assert ui.owed == "roman"
        rows = ui.actions(type="winter_quarters")["entries"]
        assert {row["action"]["lord"] for row in rows} == {manuel}
        assert {bool(row["action"].get("stay")) for row in rows} == {True, False}
        ui.apply(next(row["id"] for row in rows if bool(row["action"].get("stay")) == stay))
        assert ui.gs.lords[manuel].cylinder == ("sebasteia" if stay else "to_constantinople")
        assert not any(p["type"] == "winter_quarters" for p in ui.gs.meta.pending)
        assert not check_invariants(ui.gs)
        return ui.gs.to_json()

    assert resolve(gs) == resolve(GameState.from_json(before))


@pytest.mark.parametrize("origin", ["mempet", "ani"])
@pytest.mark.parametrize("blocked,roman_vp", [(True, 12), (False, 11)])
def test_winter_bounty_requires_an_open_seat(origin, blocked, roman_vp):
    gs = _bounty_winter_position(blocked)
    emir = gs.lords["emir_of_arran"]
    emir.cylinder = origin
    emir.assets.loot = 1
    gs.meta.vp = S.score(gs)
    assert not check_invariants(gs)
    gs = GameState.from_json(gs.to_json())

    engine.apply_action(gs, {"type": "winter_proceed"})

    assert gs.meta.vp["roman"] == roman_vp
    assert gs.holding_boxes.constantinople_roman_vp_markers == roman_vp - 3


def test_winter_bounty_can_reach_another_seat_when_ani_is_blocked():
    gs = _bounty_winter_position(blocked=True)
    # Ararat neighbors blocked Ani and can reach Mosul and Baghdad via Vaspurakan.
    alp = gs.lords["alp_arslan"]
    alp.cylinder = "ararat"
    alp.assets.loot = 1
    gs.meta.vp = S.score(gs)
    assert not check_invariants(gs)

    engine.apply_action(gs, {"type": "winter_proceed"})

    assert gs.meta.vp["roman"] == 11
    assert gs.holding_boxes.constantinople_roman_vp_markers == 8


@pytest.mark.parametrize("lid, origin", [
    ("emir_of_arran", "mempet"),
    ("alp_arslan", "ani"),  # A Seat with another Seat reachable via Ararat.
])
def test_besieged_origin_blocks_winter_bounty(lid, origin):
    gs = _bounty_winter_position(blocked=False)
    lord = gs.lords[lid]
    lord.cylinder = origin
    lord.assets.loot = 1
    # Manuel is outside the friendly Stronghold besieging the Seljuk Lords.
    gs.lords["manuel_komnenos"].cylinder = origin
    gs.locales[origin].siege_markers = 1
    for friend in gs.lords.values():
        if friend.mustered and friend.side == "seljuk" and friend.cylinder == origin:
            friend.besieged = True
    gs.meta.vp = S.score(gs)
    assert not check_invariants(gs)
    saved = GameState.from_json(gs.to_json())

    action = {"type": "winter_proceed"}
    result = engine.apply_action(gs, action)
    assert engine.apply_action(saved, action) == result
    assert saved.to_json() == gs.to_json()
    assert gs.lords[lid].assets.loot == 1
    assert gs.meta.vp == {"roman": 12, "seljuk": 3}
    assert gs.holding_boxes.constantinople_roman_vp_markers == 9
    assert not check_invariants(gs)
    assert GameState.from_json(gs.to_json()).to_json() == gs.to_json()
