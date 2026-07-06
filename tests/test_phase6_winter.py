"""Phase 6: Winter Campaign / Winter March (R9/S18) pre-Bounty activation window."""
from seljuk import scenarios as S, engine, campaign


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
