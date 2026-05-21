"""Phase 3a integration: drive a full Campaign and round-trip-sweep the
command-step enumerator against the handlers."""
import pytest

from seljuk import scenarios as S, engine, campaign
from seljuk.state import GameState, IllegalAction


def _build_simple_plans(gs):
    """Build both sides' Plans (Seljuk then Roman) using real Lord cards, so the
    Campaign actually activates Lords (respecting <=4 cards/Lord, <=5 No Command)."""
    for _ in range(2):
        side = gs.meta.active_player
        if gs.meta.plan_submitted.get(side):
            break
        avail = [lid for lid in S.sd.command_decks()[side]["lords_with_cards"]
                 if lid in gs.lords and gs.lords[lid].mustered and gs.lords[lid].side == side]
        need = campaign.plan_size(gs)
        cards = []
        per = {}
        i = 0
        while len(cards) < need:
            if avail:
                lid = avail[i % len(avail)]
                i += 1
                if per.get(lid, 0) < 4:
                    cards.append(lid)
                    per[lid] = per.get(lid, 0) + 1
                    continue
            if cards.count("no_command") < 5:
                cards.append("no_command")
            else:
                cards.append(avail[i % len(avail)])  # fall back to cycling lords
                i += 1
        engine.apply_action(gs, {"type": "build_plan", "side": side, "cards": cards})


@pytest.mark.parametrize("scenario", ["year_of_treacherous_ambition", "manzikert"])
def test_campaign_drives_to_turn_end_with_roundtrip_sweep(scenario):
    gs = S.load_scenario(scenario, seed=1)
    campaign.start_campaign(gs)
    _build_simple_plans(gs)
    assert gs.meta.subphase == "campaign.command"

    guard = 0
    while gs.meta.phase == "campaign" and gs.meta.subphase == "campaign.command" and guard < 200:
        guard += 1
        moves = engine.legal_moves(gs)
        # Every emitted move must apply cleanly on a fresh snapshot.
        for mv in moves:
            snap = GameState.from_json(gs.to_json())
            try:
                engine.apply_action(snap, {k: v for k, v in mv.items() if not k.startswith("_")})
            except IllegalAction as e:  # pragma: no cover
                pytest.fail(f"{scenario}: enumerator emitted inapplicable {mv.get('type')}: {e}")
        # Advance the real game deterministically: resolve any pending, else end the card.
        pend = [m for m in moves if m["type"] == "resolve_ravage_defence"]
        chosen = pend[0] if pend else {"type": "end_activation"}
        engine.apply_action(gs, {k: v for k, v in chosen.items() if not k.startswith("_")})

    # The Campaign ends either at game over or by advancing to the next Levy.
    assert gs.meta.phase in ("levy", "game_over")


def test_full_turn_levy_then_campaign_for_emperor():
    """End-to-end: a non-skip scenario runs Levy to completion, then a Campaign
    turn, landing in the next Turn's Levy (or game over)."""
    gs = S.load_scenario("emperor_and_the_lion", seed=2)
    gs.meta.notes["first_aow_done"] = True  # deterministic later-Levy draw path
    engine.start_levy(gs)
    # pass through all Levy steps (Pay, Muster, Call to Arms) for both sides
    for _ in range(6):
        engine.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.subphase == "levy.complete"
    # transition to Campaign and drive it
    campaign.start_campaign(gs)
    _build_simple_plans(gs)
    guard = 0
    while gs.meta.phase == "campaign" and gs.meta.subphase == "campaign.command" and guard < 200:
        guard += 1
        engine.apply_action(gs, {"type": "end_activation"})
    assert gs.meta.phase in ("levy", "game_over")
    if gs.meta.phase == "levy":
        assert gs.meta.calendar_box == 2  # advanced from Spring 1068 to Summer 1068
