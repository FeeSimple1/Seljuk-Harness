"""A Roman Commander can retain a Thema with Coin from a Friendly mat."""

import pytest

from seljuk import engine, scenarios
from seljuk.state import Assets, IllegalAction
from tests.test_round7_combat import _dispatch

ROMANOS = "romanos_diogenes"
ALLY = "nikephoros_bryennios"


def _reset_with_recruited_thema(*, own_coin, remote=False, pressed_levy=False):
    state = scenarios.load_scenario("emperor_and_the_lion", seed=1)
    state.meta.calendar_box = 2
    state.meta.phase, state.meta.subphase = "campaign", "campaign.command"
    state.meta.active_player = "roman"
    state.meta.active_lord = state.meta.active_card = ROMANOS
    state.meta.actions_remaining = state.meta.notes["card_full_actions"] = 4
    state.meta.pending = []
    state.meta.notes["first_plan_done"] = True
    for lord in state.lords.values():
        if lord.mustered:
            lord.assets = Assets(carts=min(lord.assets.carts, 1),
                                 provender=min(lord.assets.provender, 1))
            lord.moved_fought = False
    for side, lid in (("roman", ROMANOS), ("seljuk", "alp_arslan")):
        deck = state.side_decks(side)
        deck.command_plan = ["no_command"] * 4 + [lid] * 4
        deck.plan_pointer = 8
    state.lords[ROMANOS].cylinder = "ankyra"
    state.lords[ROMANOS].assets.coin = own_coin
    state.lords[ALLY].cylinder = "to_constantinople" if remote else "ankyra"
    state.lords[ALLY].assets.coin = 1
    if pressed_levy:
        state.roman.draw_deck.remove("R4")
        state.roman.capabilities_in_play.append("R4")
    _dispatch(state, {"type": "cmd_recruit", "lord": ROMANOS, "marker_index": 0})
    _dispatch(state, {"type": "end_activation"})
    while state.meta.subphase == "campaign.fpd_pay":
        _dispatch(state, {"type": "fpd_done"})
    return state


@pytest.mark.parametrize("own_coin", [0, 1])
def test_retention_can_spend_from_the_chosen_colocated_mat(own_coin):
    state = _reset_with_recruited_thema(own_coin=own_coin, pressed_levy=bool(own_coin))
    assert state.meta.subphase == "campaign.reset"
    moves = engine.legal_moves(state)
    expected_payers = {ALLY, ROMANOS} if own_coin else {ALLY}
    assert {m["payer"] for m in moves if m["mode"] == "pay"} == expected_payers
    move = next(m for m in moves if m.get("payer") == ALLY)
    before = state.to_json()
    with pytest.raises(IllegalAction) as exc:
        engine.apply_action(state, {**move, "payer": "alp_arslan"})
    assert exc.value.code == "bad_retention"
    assert state.to_json() == before
    if not own_coin:
        move.pop("payer")  # An older pay action still works with the only eligible mat.
    result = _dispatch(state, move)
    assert result["payer"] == ALLY
    assert state.lords[ROMANOS].assets.coin == own_coin
    assert state.lords[ALLY].assets.coin == 0
    marker, = state.lords[ROMANOS].themata_on_mat
    assert marker.home_thema == "Boukellarion"


def test_remote_coin_does_not_pay_for_retention():
    state = _reset_with_recruited_thema(own_coin=0, remote=True, pressed_levy=True)
    assert {m["mode"] for m in engine.legal_moves(state)} == {"pressed_levy", "return"}
    move = next(m for m in engine.legal_moves(state) if m["mode"] == "pressed_levy")
    _dispatch(state, move)
    assert state.lords[ALLY].assets.coin == 1
    assert state.lords[ROMANOS].themata_on_mat
