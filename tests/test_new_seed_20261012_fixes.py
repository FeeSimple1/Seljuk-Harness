"""Seed-20261012 fixes: retained Themata counters and atomic Loyalty payments.

Captured checkpoints cover the original seven failures and four controls.
Additional cases exercise the shared resolver, both action entry points, both
factions, malformed JSON payment types, and Conquer/Ruin/Sack counter custody.
"""
from collections import Counter
from pathlib import Path
import pytest
from seljuk import actions, battle, campaign, engine, events, map as gmap
from seljuk.llm import LLMSession
from seljuk.state import GameState, IllegalAction
from seljuk.rng import DiceRoller

DATA = Path(__file__).resolve().parent / "fixtures" / "new_seed_20261012"

def load(name):
    return GameState.from_json((DATA / name).read_text())

def inventory(gs):
    result = Counter()
    for home, markers in gs.themata.items():
        for m in markers:
            result[(home, m.unit, m.symbols)] += 1
    for lord in gs.lords.values():
        for m in lord.themata_on_mat:
            result[(m.home_thema, m.unit, m.symbols)] += 1
    for loc in gs.locales.values():
        for m in loc.themata_defending:
            result[(m.home_thema, m.unit, m.symbols)] += 1
    for m in gs.meta.themata_removed:
        result[(m.home_thema, m.unit, m.symbols)] += 1
    return result

def surrender():
    session = LLMSession(load('surrender-before.json'))
    result = session.apply({'type': 'cmd_siege', 'lord': 'artuk_beg'})
    assert result['seized'] is True
    assert result['surrender_roll'] == [1, 1]
    return session.gs, result

# NS-01: Surrender deletes the physical counter records instead of retaining
# them in the removed-from-play pool that R13 uses.
def test_ns01_surrender_preserves_removed_themata_inventory():
    before = load('surrender-before.json')
    after, _ = surrender()
    assert inventory(after) == inventory(before)

def test_ns01_r13_can_return_a_surrendered_marker():
    after, _ = surrender()
    result = events._ev_thrakion(after, {'thema': 'Melitene', 'unit': 'infantry'},
                                 engine.roller_for(after))
    assert result.get('returned') == {'thema': 'Melitene', 'unit': 'infantry'}

# NS-02: The counterpayer is the revealing player's opponent, not necessarily
# the target Lord's current owner (rules 1.4 and 1.4.1).
def test_ns02_counterpayment_hint_uses_the_opponent_budget():
    gs = load('loyalty-before.json')
    move = next(m for m in engine.legal_moves(gs) if m.get('target') == 'robert_crepin')
    assert gs.lords['robert_crepin'].side == 'seljuk'
    assert move['_max_coins_for'] == 1
    assert move['_max_coins_against'] == 0

def test_ns02_counterpayment_cannot_bill_the_revealing_side():
    session = LLMSession(load('loyalty-before.json'))
    before = session.gs.to_json()
    with pytest.raises(IllegalAction):
        session.apply({'type': 'resolve_loyalty', 'target': 'robert_crepin',
                       'coins_for': 0, 'coins_against': 1})
    assert session.gs.to_json() == before

# NS-03: This independently targets an opposing Lord, so it does not rely on
# NS-02. Rejecting an unavailable opposing payment must not take the first Coin.
def test_ns03_rejected_second_payment_does_not_consume_first_payment():
    session = LLMSession(load('loyalty-before.json'))
    before = session.gs.to_json()
    with pytest.raises(IllegalAction, match='insufficient_coin'):
        session.apply({'type': 'resolve_loyalty', 'target': 'roussel_de_bailleul',
                       'coins_for': 1, 'coins_against': 1})
    assert session.gs.to_json() == before

# NS-04: Negative values currently alter the roll without spending any Coin.
@pytest.mark.parametrize('field', ['coins_for', 'coins_against'])
def test_ns04_negative_coin_amount_is_rejected(field):
    session = LLMSession(load('loyalty-before.json'))
    before = session.gs.to_json()
    action = {'type': 'resolve_loyalty', 'target': 'roussel_de_bailleul',
              'coins_for': 0, 'coins_against': 0, field: -2}
    with pytest.raises(IllegalAction):
        session.apply(action)
    assert session.gs.to_json() == before

# Neighboring controls: legitimate payments, ordinary surrender effects, and
# R13 return of a marker already correctly stored in the removed pool.
@pytest.mark.parametrize('coins', [0, 1])
def test_control_valid_loyalty_payment(coins):
    session = LLMSession(load('loyalty-before.json'))
    result = session.apply({'type': 'resolve_loyalty', 'target': 'roussel_de_bailleul',
                            'coins_for': coins, 'coins_against': 0})
    check = result['loyalty']
    assert check['natural'] == 3
    assert check['modified'] == 3 + coins
    assert check['switched'] is False
    assert session.gs.lords['alp_arslan'].assets.coin == 1 - coins

def test_control_surrender_cleans_investment_and_sets_allegiance():
    gs, _ = surrender()
    loc = gs.locales['melitene']
    assert loc.conquered_side == 'seljuk'
    assert loc.conquered_count == 2
    assert loc.siege_markers == 0
    assert not loc.bypass
    assert not loc.themata_defending

def test_control_r13_returns_an_existing_removed_marker():
    gs = load('surrender-before.json')
    marker = gs.meta.themata_removed[0]
    before = inventory(gs)
    result = events._ev_thrakion(gs, {'thema': marker.home_thema, 'unit': marker.unit},
                                 engine.roller_for(gs))
    assert 'returned' in result
    assert inventory(gs) == before


# Every capture path owns one transfer. In particular, Sack must not transfer
# first and then have Conquer/Ruin duplicate those same physical counters.
@pytest.mark.parametrize("mode", ["conquer", "ruin", "sack_conquer", "sack_ruin"])
def test_ns01_each_capture_path_records_each_marker_once(mode):
    gs = load("surrender-before.json")
    before = inventory(gs)
    removed = [m.model_dump() for m in gs.meta.themata_removed]
    defenders = [m.model_dump() for m in gs.locales["melitene"].themata_defending]
    assert len(defenders) == 2 and any(m["symbols"] == 2 for m in defenders)
    if mode == "conquer":
        battle.conquer(gs, "melitene", "seljuk")
    elif mode == "ruin":
        battle.ruin(gs, "melitene")
    else:
        battle._sack(gs, ["artuk_beg"], [], "melitene", "seljuk",
                     battle.DecisionContext([("sack_choice", mode.removeprefix("sack_"))]),
                     engine.roller_for(gs))
    assert inventory(gs) == before
    assert [m.model_dump() for m in gs.meta.themata_removed] == removed + defenders
    assert gs.locales["melitene"].themata_defending == []
    # Re-entering capture cleanup cannot record the counters a second time.
    battle.conquer(gs, "melitene", "seljuk")
    assert [m.model_dump() for m in gs.meta.themata_removed] == removed + defenders
    # Serialized counters retain home, unit type, and double-marker identity.
    gs = GameState.from_json(gs.to_json())
    result = events._ev_thrakion(gs, {"thema": "Melitene", "unit": "infantry"}, engine.roller_for(gs))
    assert result["returned"] == {"thema": "Melitene", "unit": "infantry"}
    assert any(m.unit == "infantry" and m.symbols == 2 for m in gs.themata["Melitene"])
    assert inventory(gs) == before


def test_ns01_declining_surrender_does_not_remove_garrison():
    gs = load("surrender-before.json")
    before = inventory(gs)
    defenders = list(gs.locales["melitene"].themata_defending)
    removed = list(gs.meta.themata_removed)
    result = engine.apply_action(gs, {"type": "cmd_siege", "lord": "artuk_beg", "roll_surrender": False})
    assert not result.get("seized")
    assert gs.locales["melitene"].themata_defending == defenders
    assert gs.meta.themata_removed == removed
    assert inventory(gs) == before


def funded_loyalty(revealing="seljuk", own_target=True):
    gs = load("loyalty-before.json")
    opponent = "roman" if revealing == "seljuk" else "seljuk"
    target = "robert_crepin" if revealing == "seljuk" else "arisighi"
    gs.lords[target].side = revealing if own_target else opponent
    gs.lords[target].cylinder = "edessa"
    gs.lords["alp_arslan"].assets.coin = 3
    gs.lords["manuel_komnenos"].assets.coin = 2
    gs.meta.pending = [{"type": "loyalty_check", "side": revealing,
                        "targets": [target], "_owed_by": revealing}]
    gs.meta.active_player = revealing
    return gs, target


@pytest.mark.parametrize("side", ["roman", "seljuk"])
@pytest.mark.parametrize("own_target", [True, False])
def test_ns02_both_factions_pay_from_distinct_correct_pools(side, own_target):
    gs, target = funded_loyalty(side, own_target)
    expected = (3, 2) if side == "seljuk" else (2, 3)
    raw = gs.to_json()
    move = next(m for m in engine.legal_moves(gs) if m.get("target") == target)
    assert (move["_max_coins_for"], move["_max_coins_against"]) == expected
    assert gs.to_json() == raw  # menus may not spend
    result = actions.resolve_loyalty_check(gs, target, side, engine.roller_for(gs), 1, 1)
    assert result["natural"] == result["modified"] == 3
    assert gs.lords["alp_arslan"].assets.coin == 2
    assert gs.lords["manuel_komnenos"].assets.coin == 1


@pytest.mark.parametrize("side", ["roman", "seljuk"])
def test_ns02_besieged_target_has_no_counterpayment_and_rejection_is_atomic(side):
    gs, target = funded_loyalty(side)
    gs.lords[target].besieged = True
    move = next(m for m in engine.legal_moves(gs) if m.get("target") == target)
    assert move["_max_coins_against"] == 0
    roller = engine.roller_for(gs)
    before, rng = gs.to_json(), roller.get_state()
    with pytest.raises(IllegalAction, match="besieged_no_resist"):
        actions.resolve_loyalty_check(gs, target, side, roller, 1, 1)
    assert gs.to_json() == before and roller.get_state() == rng


def coffers_state():
    gs = load("loyalty-before.json")
    # The on-map Roman Commander must be adjacent to the Seljuk target.
    gs.lords["manuel_komnenos"].cylinder = next(iter(gmap.neighbors("edessa")))
    gs.lords["manuel_komnenos"].assets.coin = 1
    gs.lords["alp_arslan"].assets.coin = 0
    for deck in (gs.roman.draw_deck, gs.roman.held_events,
                 gs.roman.this_campaign_events, gs.roman.capabilities_in_play):
        while "R14" in deck:
            deck.remove("R14")
    gs.roman.capabilities_in_play.append("R14")
    gs.meta.phase = "levy"
    gs.meta.subphase = "levy.pay"
    gs.meta.pending = [{"type": "imperial_coffers", "_owed_by": "roman"}]
    assert "robert_crepin" in campaign.imperial_coffers_targets(gs)
    return gs


def invoke(gs, entry, coins_for, coins_against, roller):
    target = "robert_crepin" if entry == "coffers" else "roussel_de_bailleul"
    if entry == "resolver":
        return actions.resolve_loyalty_check(gs, target, "seljuk", roller, coins_for, coins_against)
    return engine.apply_action(gs, {"type": "discard_imperial_coffers" if entry == "coffers" else "resolve_loyalty",
                                    "target": target, "coins_for": coins_for, "coins_against": coins_against})


@pytest.mark.parametrize("entry", ["resolver", "treachery", "coffers"])
@pytest.mark.parametrize("payments", [(1, 1), (2, 0)])
def test_ns03_every_entry_point_preflights_both_budgets(entry, payments):
    gs = coffers_state() if entry == "coffers" else load("loyalty-before.json")
    roller = engine.roller_for(gs)
    before, rng = gs.to_json(), roller.get_state()
    with pytest.raises(IllegalAction, match="insufficient_coin"):
        invoke(gs, entry, *payments, roller)
    assert gs.to_json() == before  # includes cards, pending, RNG, and history
    assert roller.get_state() == rng


@pytest.mark.parametrize("entry", ["resolver", "treachery", "coffers"])
@pytest.mark.parametrize("field", ["coins_for", "coins_against"])
@pytest.mark.parametrize("bad", [-2, 0.5, 1.0, True, False, "1", None, [], {}])
def test_ns04_only_nonnegative_integer_coin_counts_are_accepted(entry, field, bad):
    gs = coffers_state() if entry == "coffers" else load("loyalty-before.json")
    roller = engine.roller_for(gs)
    before, rng = gs.to_json(), roller.get_state()
    payments = {"coins_for": 1, "coins_against": 0, field: bad}
    with pytest.raises(IllegalAction, match="bad_coin_amount"):
        invoke(gs, entry, payments["coins_for"], payments["coins_against"], roller)
    assert gs.to_json() == before
    assert roller.get_state() == rng


def test_coffers_valid_payment_consumes_card_once_and_clears_window():
    gs = coffers_state()
    menu = engine.legal_moves(gs)
    move = next(m for m in menu if m.get("target") == "robert_crepin")
    assert (move["_max_coins_for"], move["_max_coins_against"]) == (1, 0)
    result = invoke(gs, "coffers", 1, 0, engine.roller_for(gs))
    assert result["loyalty"]["modified"] == result["loyalty"]["natural"] + 1
    assert gs.lords["manuel_komnenos"].assets.coin == 0
    assert "R14" not in gs.roman.capabilities_in_play
    assert gs.roman.draw_deck.count("R14") == 1
    assert not any(p["type"] == "imperial_coffers" for p in gs.meta.pending)
    assert len(gs.history) == 1


def test_rejected_payment_retry_matches_fresh_valid_submission():
    fresh = load("loyalty-before.json")
    gs = GameState.from_json(fresh.to_json())
    with pytest.raises(IllegalAction):
        invoke(gs, "treachery", 1, 1, engine.roller_for(gs))
    gs = GameState.from_json(gs.to_json())
    first = invoke(gs, "treachery", 1, 0, engine.roller_for(gs))
    control = invoke(fresh, "treachery", 1, 0, engine.roller_for(fresh))
    assert first == control and gs.to_json() == fresh.to_json()


@pytest.mark.parametrize("side", ["roman", "seljuk"])
@pytest.mark.parametrize("die", [1, 6])
def test_paid_checks_keep_natural_one_and_six_overrides(side, die):
    gs, target = funded_loyalty(side)
    class Roller:
        def d6(self):
            return die
    # Force an otherwise contrary modifier: +2 on a 1, -2 on a 6.
    for_coins, against = (2, 0) if die == 1 else (0, 2)
    result = actions.resolve_loyalty_check(gs, target, side, Roller(), for_coins, against)
    assert result["natural"] == die
    assert result["switched"] is (die == 6)
