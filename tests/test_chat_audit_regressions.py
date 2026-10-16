"""Regression cases for all 20 findings in the October 2026 chat audit.

Keep engine/JSON entry-point coverage alongside focused arithmetic tests. Rule
numbers refer to the repository's sources and recorded adjudications.
"""
import json

import pytest

from seljuk import actions as A, battle as B, campaign as C, engine as E
from seljuk import scenarios as S, static_data as sd, map as gmap
from seljuk.llm.view import filtered_state
from seljuk.rng import DiceRoller
from seljuk.state import Assets, GameState, IllegalAction, ThemataMarker


class ConstantDice:
    def __init__(self, value=6):
        self.value = value
        self.calls = 0

    def d6(self):
        self.calls += 1
        return self.value

    def roll(self, n):
        return [self.d6() for _ in range(n)]


def game(seed=1, scenario="emperor_and_the_lion"):
    return S.load_scenario(scenario, seed=seed)


def command(gs, lord, n=4):
    gs.meta.phase = "campaign"
    gs.meta.subphase = "campaign.command"
    gs.meta.active_player = gs.lords[lord].side
    gs.meta.active_lord = gs.meta.active_card = lord
    gs.meta.actions_remaining = n
    gs.seljuk.command_plan = ["alp_arslan"] * 3
    gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["romanos_diogenes"] * 3
    gs.roman.plan_pointer = 1


def place(gs, lid, units, locale="melitene"):
    lord = gs.lords[lid]
    lord.mustered = True
    lord.cylinder = locale
    lord.forces = dict(units)
    lord.routed = {}
    lord.capabilities = []
    lord.themata_on_mat = []
    return lord


def rows(gs, attackers=("alp_arslan",), defenders=("chatatourios",)):
    att = B._Side(gs, [], "attacker")
    deff = B._Side(gs, [], "defender")
    for side, ids in ((att, attackers), (deff, defenders)):
        for slot, lid in zip(("center", "left", "right"), ids):
            side.front[slot] = lid
    return att, deff


def choose_opening(gs):
    while any(p["type"] == "deploy_capability" for p in gs.meta.pending):
        E.apply_action(gs, E.legal_moves(gs)[0])


# 01: nested rolls must consume one persistent random stream.
def test_01_nested_action_dice_are_not_rewound(monkeypatch):
    gs = game(seed=19)
    expected = DiceRoller(19)
    expected_rolls = expected.roll(3)

    def handler(state, action, roller):
        first = roller.d6()
        nested = B._roller(state)
        second = nested.d6()
        B._save_roller(state, nested)
        third = roller.d6()
        return [first, second, third]

    monkeypatch.setitem(E._HANDLERS, "regression_roll", handler)
    assert E.apply_action(gs, {"type": "regression_roll"}) == expected_rolls
    restored = GameState.from_json(gs.to_json())
    assert E.roller_for(restored).get_state() == expected.get_state()
    assert E.roller_for(restored).d6() == expected.d6()


def test_01_actual_sally_preserves_resolver_rng_state(monkeypatch):
    gs = game(seed=11)
    a = place(gs, "alp_arslan", {"ghulam_cavalry": 5}, "antioch")
    d = place(gs, "chatatourios", {"tagmata": 5}, "antioch")
    d.besieged = True
    gs.locales["antioch"].siege_markers = 2
    command(gs, d.id)
    recorded = []
    resolve = B.resolve_sally

    def wrapper(*args, **kwargs):
        result = resolve(*args, **kwargs)
        recorded.append(args[5].get_state())
        return result

    monkeypatch.setattr(B, "resolve_sally", wrapper)
    E.apply_action(gs, {"type": "cmd_sally", "lord": d.id})
    assert recorded and recorded[0] != DiceRoller(11).get_state()
    assert E.roller_for(gs).get_state() == recorded[0]


# 02: 4.7.1 is before EVERY campaign cleanup and Winter step.
@pytest.mark.parametrize("scenario", S.SCENARIOS)
def test_02_final_score_precedes_cleanup_and_winter(scenario):
    gs = game(scenario=scenario)
    gs.meta.calendar_box = gs.meta.final_box
    gs.meta.phase = "campaign"
    gs.meta.subphase = "campaign.end"  # includes final-turn scenario-specific VP
    gs.locales["ani"].siege_markers = 4
    gs.lords["alp_arslan"].assets = Assets(coin=4, loot=3, carts=2)
    gs.seljuk.held_events = ["S18"]
    gs.roman.held_events = ["R9"]
    gs.meta.vp = S.score(gs)
    before = gs.model_dump()
    expected_score, expected_winner = dict(gs.meta.vp), S.end_of_scenario_winner(gs)
    C._end_campaign(gs)
    assert gs.meta.phase == "game_over"
    assert gs.meta.notes["winner"] == expected_winner
    assert gs.meta.vp == expected_score
    assert gs.meta.pending == before["meta"]["pending"]
    assert gs.model_dump()["lords"] == before["lords"]
    assert gs.model_dump()["locales"] == before["locales"]
    assert "winter_holders" not in gs.meta.notes


# 03: Themata stay identifiable, but count as real units on their Commander's mat.
@pytest.mark.parametrize("kind", ["levy_themata", "cmd_recruit"])
def test_03_levied_and_recruited_themata_fight_and_feed(kind):
    gs = game()
    lord = place(gs, "romanos_diogenes", {"militia": 8}, "kaisareia")
    gs.themata["Charsianon"] = [ThemataMarker(unit="militia")]
    if kind == "levy_themata":
        gs.meta.subphase = "levy.muster"
        gs.meta.active_player = "roman"
        A.reset_muster_segment(gs)
    else:
        command(gs, lord.id)
    E.apply_action(gs, {"type": kind, "lord": lord.id, "marker_index": 0})
    assert C._unit_count(lord) == 9
    assert C._feed_requirement(C._unit_count(lord)) == 2
    assert B._lord_step_hits_caps(gs, lord.id, "missile", 1)[0] == 4.5
    lord.moved_fought = True
    lord.assets.provender = 2
    fed = C._fpd_feed(gs)
    entry = next(f for f in fed["feed"] if f["lord"] == lord.id)
    assert entry["needed"] == 2 and lord.assets.provender == 0
    lord.forces = {}
    assert not B._is_routed(lord)
    assert B._unrouted_units(lord) == {"militia": 1}


def test_03_double_themata_partial_and_total_losses_preserve_identity():
    gs = game()
    lord = place(gs, "romanos_diogenes", {})
    removed_at_start = len(gs.meta.themata_removed)  # setup removals are physical counters too
    lord.themata_on_mat = [ThemataMarker(unit="militia", symbols=2, home_thema="Charsianon")]
    B._apply_hits(gs, lord.id, 1, "melee", B.DecisionContext(), ConstantDice())
    assert lord.themata_on_mat[0].routed == 1
    assert lord.routed == {}  # do not mix the marker's units into Lord/Vassal units
    saved = GameState.from_json(gs.to_json())
    lord = saved.lords[lord.id]
    B._loss_roll(saved, lord, False, ConstantDice())
    assert C._unit_count(lord) == 1
    assert len(lord.themata_on_mat) == 1
    assert lord.lost == {}  # cannot restore Themata as a Lord's original units
    B._apply_hits(saved, lord.id, 1, "melee", B.DecisionContext(), ConstantDice())
    B._loss_roll(saved, lord, False, ConstantDice())
    assert not lord.themata_on_mat and B._is_routed(lord)
    assert len(saved.meta.themata_removed) == removed_at_start + 1
    assert saved.meta.themata_removed[-1].symbols == 2


def test_03_returned_themata_reset_surviving_marker_strength():
    gs = game()
    lord = gs.lords["romanos_diogenes"]
    marker = ThemataMarker(unit="militia", symbols=2, home_thema="Charsianon", strength=1)
    lord.themata_on_mat = [marker]
    count = len(gs.themata["Charsianon"])
    C._reset(gs, retained={})
    assert not lord.themata_on_mat
    assert len(gs.themata["Charsianon"]) == count + 1
    assert marker.home_thema is None and marker.unit_count() == 2


# 04: Mountain Ambush must work in either side's Sally, not raise NameError.
@pytest.mark.parametrize("side,card", [("roman", "R2"), ("seljuk", "S2")])
def test_04_mountain_ambush_sally(side, card):
    gs = game()
    locale = next(loc for loc in gs.locales if sd.locale(loc).get("is_stronghold")
                  and gmap.adjacent_to_pass(loc) and sd.locale(loc)["allegiance"] == "roman")
    attacker = place(gs, "chatatourios", {"tagmata": 3}, locale)
    attacker.besieged = True
    place(gs, "alp_arslan", {"ghulam_cavalry": 3}, locale)
    gs.locales[locale].siege_markers = 2
    gs.side_decks(side).held_events = [card]
    command(gs, attacker.id)
    result = E.apply_action(gs, {"type": "cmd_sally", "lord": attacker.id,
                                "battle_events": {side: [card]}})
    assert result["sally"]["ok"]
    assert card not in gs.side_decks(side).held_events


# 05: recalculate eligible targets as a Lord routs, but do not hit Reserve/another row.
@pytest.mark.parametrize("pool", [(3.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 3.0)])
def test_05_battle_hits_continue_after_front_lord_routs(pool):
    gs = game()
    place(gs, "alp_arslan", {"turkic_horse": 3})
    for lid in ("chatatourios", "romanos_diogenes", "robert_crepin"):
        place(gs, lid, {"militia": 1})
    att, deff = rows(gs, defenders=("chatatourios", "romanos_diogenes"))
    deff.reserve = ["robert_crepin"]
    B._apply_pools(gs, "missile", {"chatatourios": pool},
                  {"chatatourios": {"center"}}, att, deff, "attacker", {}, 1,
                  B.DecisionContext(), ConstantDice(), [], "front", "front", 0)
    assert B._is_routed(gs.lords["chatatourios"])
    assert B._is_routed(gs.lords["romanos_diogenes"])
    assert gs.lords["robert_crepin"].forces == {"militia": 1}


def test_05_battle_hits_do_not_cross_from_front_to_rearguard():
    gs = game()
    place(gs, "alp_arslan", {"turkic_horse": 3})
    place(gs, "chatatourios", {"militia": 1})
    place(gs, "romanos_diogenes", {"militia": 1})
    att, deff = rows(gs)
    deff.rearguard["center"] = "romanos_diogenes"
    B._apply_pools(gs, "missile", {"chatatourios": (3.0, 0.0, 0.0)},
                  {"chatatourios": {"center"}}, att, deff, "attacker", {}, 1,
                  B.DecisionContext(), ConstantDice(), [], "front", "front", 0)
    assert B._is_routed(gs.lords["chatatourios"])
    assert gs.lords["romanos_diogenes"].forces == {"militia": 1}


@pytest.mark.parametrize("receiving", ["attacker", "defender"])
def test_05_storm_hits_continue_across_front_not_reserve(receiving):
    gs = game()
    for lid in ("alp_arslan", "ibn_khan", "afsin_beg", "chatatourios", "romanos_diogenes", "robert_crepin"):
        place(gs, lid, {"militia": 1})
    att, deff = rows(gs, ("alp_arslan", "ibn_khan"), ("chatatourios", "romanos_diogenes"))
    att.reserve = ["afsin_beg"]
    deff.reserve = ["robert_crepin"]
    if receiving == "attacker":
        B._hit_attacker(gs, att, 3, "missile", 0, False, ConstantDice(), B.DecisionContext(), [], "test", 1)
        targets, reserve = ["alp_arslan", "ibn_khan"], "afsin_beg"
    else:
        B._hit_defender(gs, deff, {}, {}, 3, "missile", (1, 0), ConstantDice(), B.DecisionContext(), [], "test", 1)
        targets, reserve = ["chatatourios", "romanos_diogenes"], "robert_crepin"
    assert all(B._is_routed(gs.lords[lid]) for lid in targets)
    assert gs.lords[reserve].forces == {"militia": 1}


# 06: plans are secret in EVERY exported field, not merely command_plan.
def test_06_opponent_plan_is_not_recoverable_from_history():
    gs = game()
    C.start_campaign(gs)
    plan = ["alp_arslan"] * 4 + ["no_command"] * (C.plan_size(gs) - 4)
    E.apply_action(gs, {"type": "build_plan", "side": "seljuk", "cards": plan})
    before = gs.to_json()
    view = filtered_state(gs, "roman")
    assert view["seljuk"]["command_plan"] == ["<hidden>"] * len(plan)
    assert view["history"] == [{"action": {"type": "build_plan"}}]
    assert "rng_state" not in view["meta"] and "seed" not in view["meta"]
    assert filtered_state(gs, "seljuk")["seljuk"]["command_plan"] == plan
    gs.seljuk.plan_pointer = 1
    assert filtered_state(gs, "roman")["seljuk"]["command_plan"] == [plan[0]] + ["<hidden>"] * (len(plan)-1)
    gs.seljuk.plan_pointer = 0
    assert gs.to_json() == before  # view construction must not mutate the replay


# 07: typed JSON decisions and tuple-valued choices have Python parity.
def test_07_json_typed_decisions_match_python_battle():
    gs = game()
    place(gs, "alp_arslan", {"ghulam_cavalry": 8})
    place(gs, "chatatourios", {"tagmata": 8})
    command(gs, "alp_arslan")
    script = [("concede", True)]
    copy = GameState.from_json(gs.to_json())
    python_result = B.begin_battle(gs, ["alp_arslan"], ["chatatourios"], "melitene", scripted=script)
    json_result = B.begin_battle(copy, ["alp_arslan"], ["chatatourios"], "melitene", scripted=json.loads(json.dumps(script)))
    assert python_result["conceder"] == "attacker"
    assert python_result == json_result and gs.to_json() == copy.to_json()


def test_07_json_tuple_valued_choice_returns_the_offered_value():
    options = [("retreat", "ani"), ("withdraw", "melitene")]
    ctx = B.DecisionContext([["fate", ["withdraw", "melitene"]]])
    assert ctx.decide("unrelated", [True, False]) is True
    assert ctx.decide("fate", options) == ("withdraw", "melitene")
    assert not ctx.scripted


# 08: S11 is one owner-declared Battle round, not every round or any Storm.
def test_08_javelins_fires_only_in_chosen_round():
    gs = game()
    lord = place(gs, "ibn_khan", {"infantry": 2})
    lord.capabilities = ["S11"]
    lord.flags["javelins_round"] = 2
    assert [B._lord_step_hits_caps(gs, lord.id, "missile", r)[0] for r in (1, 2, 3)] == [0, 2, 0]
    att, _ = rows(gs, (lord.id,), ())
    assert B._lord_step_hits(gs, att, "missile", 2) == 0  # Storm's base-Missile path


# 09: one aggregate rounding budget for mixed Garrison and Lord Missiles.
def test_09_storm_mixed_half_missiles_make_one_hit(monkeypatch):
    gs = game()
    place(gs, "alp_arslan", {"ghulam_cavalry": 8})
    place(gs, "chatatourios", {"tagmata": 1})
    att, deff = rows(gs)
    seen = []

    def record(gs, att, hits, hit_type, siege, anti_armor, roller, ctx, log, step, round_no, **kwargs):
        if hit_type == "missile":
            seen.append((hits, anti_armor))

    monkeypatch.setattr(B, "_hit_attacker", record)
    B._storm_strike(gs, att, deff, {"militia": 1}, {}, (1, 4), 2, 1,
                    B.DecisionContext(), ConstantDice(1), [])
    assert sum(hits for hits, _ in seen) == 1


# 10: a Sack yields the defeated Lords' assets as well as printed rewards.
def test_10_sack_transfers_defender_assets_and_respects_recipient_caps():
    gs = game()
    first = place(gs, "alp_arslan", {"ghulam_cavalry": 2}, "tephrike")
    second = place(gs, "ibn_khan", {"turkic_horse": 2}, "tephrike")
    defender = place(gs, "chatatourios", {}, "tephrike")
    first.assets = Assets(coin=8, carts=8, provender=8, loot=8)
    second.assets = Assets()
    defender.assets = Assets(coin=2, carts=2, provender=2, loot=2)
    out = B._sack(gs, [first.id, second.id], [defender.id], "tephrike", "seljuk",
                  B.DecisionContext(), ConstantDice())
    assert out["lord_spoils"] == {"coin": 2, "carts": 2, "provender": 2, "loot": 2}
    for asset in ("coin", "carts", "provender", "loot"):
        assert getattr(second.assets, asset) >= 2
        assert getattr(first.assets, asset) == 8
        assert getattr(defender.assets, asset) == 0
    assert defender.cylinder == "removed"


# 11: Reset is a real, persisted Roman retention decision.
def retention_position(coins=2, free=False):
    gs = game()
    gs.meta.phase = "campaign"
    gs.meta.calendar_box = 2
    lord = gs.lords["romanos_diogenes"]
    lord.assets = Assets(coin=coins)
    lord.themata_on_mat = [ThemataMarker(unit="militia", home_thema="Charsianon"),
                           ThemataMarker(unit="tagmata", home_thema="Charsianon"),
                           ThemataMarker(unit="militia", home_thema="Armeniakon")]
    if free:
        gs.roman.capabilities_in_play.append("R4")
    C._end_campaign(gs)
    return gs


def test_11_retain_a_whole_thema_for_one_coin_and_return_other():
    gs = retention_position()
    assert gs.meta.subphase == "campaign.reset" and gs.meta.active_player == "roman"
    assert {m["mode"] for m in E.legal_moves(gs)} == {"pay", "return"}
    copy = GameState.from_json(gs.to_json())
    with pytest.raises(IllegalAction):
        E.apply_action(copy, {"type": "end_activation"})
    assert copy.to_json() == gs.to_json()
    before_coin = gs.lords["romanos_diogenes"].assets.coin
    E.apply_action(gs, {"type": "retain_themata", "lord": "romanos_diogenes", "thema": "Charsianon", "mode": "pay"})
    E.apply_action(gs, {"type": "retain_themata", "lord": "romanos_diogenes", "thema": "Armeniakon", "mode": "return"})
    lord = gs.lords["romanos_diogenes"]
    assert len(lord.themata_on_mat) == 2
    assert {m.home_thema for m in lord.themata_on_mat} == {"Charsianon"}
    assert lord.assets.coin == before_coin - 1
    assert gs.meta.phase == "levy" and gs.meta.calendar_box == 3


def test_11_pressed_levy_retains_only_one_unpaid_thema():
    gs = retention_position(coins=0, free=True)
    E.apply_action(gs, {"type": "retain_themata", "lord": "romanos_diogenes", "thema": "Charsianon", "mode": "pressed_levy"})
    assert {m["mode"] for m in E.legal_moves(gs)} == {"return"}
    before = gs.to_json()
    with pytest.raises(IllegalAction):
        E.apply_action(gs, {"type": "retain_themata", "lord": "romanos_diogenes", "thema": "Armeniakon", "mode": "pressed_levy"})
    assert gs.to_json() == before
    E.apply_action(gs, E.legal_moves(gs)[0])
    assert len(gs.lords["romanos_diogenes"].themata_on_mat) == 2


# 12: abandoned investments are cleared when Winter Quarters move their Lords.
def test_12_last_besieger_leaving_for_winter_removes_siege():
    gs = game()
    lord = place(gs, "alp_arslan", {"ghulam_cavalry": 2}, "tephrike")
    gs.locales["tephrike"].siege_markers = 2
    C._apply_winter_quarters(gs, lord, "ani")
    assert lord.cylinder == "ani" and gs.locales["tephrike"].siege_markers == 0


def test_12_siege_remains_while_another_besieger_stays():
    gs = game()
    lord = place(gs, "alp_arslan", {"ghulam_cavalry": 2}, "tephrike")
    place(gs, "ibn_khan", {"turkic_horse": 2}, "tephrike")
    gs.locales["tephrike"].siege_markers = 2
    C._apply_winter_quarters(gs, lord, "ani")
    assert gs.locales["tephrike"].siege_markers == 2


# 13 and 14: opening placement shares normal effects and recalculates eligibility.
def test_13_opening_r2_deploy_adds_oghuz_vassal():
    gs = game()
    gs.meta.subphase = "levy.pay"
    gs.roman.draw_deck.remove("R2")
    gs.meta.pending = [{"type": "deploy_capability", "side": "roman", "card": "R2", "eligible": ["romanos_diogenes"]}]
    E.apply_action(gs, {"type": "deploy_capability", "card": "R2", "lord": "romanos_diogenes"})
    lord = gs.lords["romanos_diogenes"]
    index = next(i for i, v in enumerate(lord.vassals) if v.requires_capability == "R2")
    assert "R2" in lord.capabilities
    assert A._vassal_levyable(gs, lord, index)


def test_14_opening_duplicate_lamellar_seed_165_is_not_offered_or_accepted():
    gs = game(seed=165)
    E.start_levy(gs)
    while any(p["type"] == "deploy_capability" for p in gs.meta.pending):
        moves = E.legal_moves(gs)
        chosen = next((m for m in moves if m["lord"] == "alp_arslan"), moves[0])
        E.apply_action(gs, chosen)
        for lord in gs.lords.values():
            names = [sd.card(c)["capability"]["name"] for c in lord.capabilities]
            assert len(names) == len(set(names)) and len(names) <= 2
    # Even an adversarial stale pending cannot bypass the live eligibility test.
    lord = gs.lords["alp_arslan"]
    lord.capabilities = ["S1"]
    gs.meta.pending = [{"type": "deploy_capability", "side": "seljuk", "card": "S3", "eligible": [lord.id]}]
    # Select the actual second Lamellar card, not its event-side name.
    second = next(c for c in game().seljuk.draw_deck if c != "S1" and sd.card(c)["capability"]["name"] == "Lamellar Armor")
    gs.meta.pending[0]["card"] = second
    before = gs.to_json()
    with pytest.raises(IllegalAction):
        E.apply_action(gs, {"type": "deploy_capability", "card": second, "lord": lord.id})
    assert gs.to_json() == before


# 15: Gifts Exchanged must be eligible and initialized when mustered.
@pytest.mark.parametrize("adjacent", [False, True])
def test_15_gifts_requires_adjacency_and_initializes_four_coins(adjacent):
    gs = game()
    gs.meta.subphase = "levy.muster"
    gs.meta.active_player = "seljuk"
    A.reset_muster_segment(gs)
    # A controlled map eliminates unrelated adjacent pairs from the scenario.
    for lord in gs.lords.values():
        lord.mustered = False
    own = place(gs, "alp_arslan", {"ghulam_cavalry": 2}, "ani")
    enemy = place(gs, "romanos_diogenes", {"tagmata": 2}, "ararat" if adjacent else "constantinople")
    if not adjacent:
        before = gs.to_json()
        assert not any(m.get("card") == "S13" for m in A.enumerate_muster(gs))
        with pytest.raises(IllegalAction):
            E.apply_action(gs, {"type": "levy_capability", "lord": own.id, "card": "S13"})
        assert gs.to_json() == before
    else:
        E.apply_action(gs, {"type": "levy_capability", "lord": own.id, "card": "S13"})
        assert gs.meta.notes["gifts_coins"] == 4
        assert gs.meta.notes["gifts_taken"] == {"seljuk": 0, "roman": 0}
        command(gs, own.id)
        assert any(m["type"] == "cmd_take_gift_coin" for m in E.legal_moves(gs))
        before_coin = own.assets.coin
        E.apply_action(gs, {"type": "cmd_take_gift_coin", "lord": own.id})
        assert own.assets.coin == before_coin + 1 and gs.meta.notes["gifts_coins"] == 3


# 16 and 17: handler-side validation, before state/RNG mutation.
@pytest.mark.parametrize("illegal", ["pass_step", "pay", "levy_transport"])
def test_16_cannot_skip_mandatory_opening_decisions(illegal):
    gs = game()
    E.start_levy(gs)
    before = gs.to_json()
    with pytest.raises(IllegalAction) as error:
        E.apply_action(gs, {"type": illegal, "lord": "alp_arslan"})
    assert error.value.code == "pending_decision"
    assert gs.to_json() == before
    choose_opening(gs)
    E.apply_action(gs, {"type": "pass_step"})
    E.apply_action(gs, {"type": "pass_step"})
    assert gs.meta.subphase == "levy.muster"


def test_17_lord_cannot_muster_enemy_lord():
    gs = game()
    gs.meta.subphase = "levy.muster"
    A.reset_muster_segment(gs)
    before = gs.to_json()
    with pytest.raises(IllegalAction):
        E.apply_action(gs, {"type": "levy_lord", "levyer": "alp_arslan", "target": "robert_crepin"})
    assert gs.to_json() == before


# 18: the cheaper discard variant is valid even if the laden move is unaffordable.
def test_18_one_action_discard_then_march_is_offered_and_applies():
    gs = game()
    lord = gs.lords["alp_arslan"]
    lord.cylinder = "ani"
    lord.assets.loot = 1
    command(gs, lord.id, n=1)
    moves = [m for m in E.legal_moves(gs) if m["type"] == "cmd_march"]
    assert moves and all(m.get("discard_to_unladen") for m in moves)
    result = E.apply_action(gs, moves[0])
    assert result["cost"] == 1
    assert lord.assets.loot == 0 and lord.cylinder == moves[0]["to"]


# 19: every moving stack remains physically together.
def test_19_group_cannot_take_lower_lord_without_lieutenant():
    gs = game()
    for lid in ("alp_arslan", "ibn_khan", "afsin_beg"):
        place(gs, lid, {"turkic_horse": 1}, "ani")
        gs.lords[lid].assets = Assets()
    gs.lords["ibn_khan"].lower_lord = "afsin_beg"
    gs.lords["afsin_beg"].lieutenant_of = "ibn_khan"
    command(gs, "alp_arslan")
    assert "afsin_beg" not in C._eligible_co_marchers(gs, gs.lords["alp_arslan"])
    before = gs.to_json()
    with pytest.raises(IllegalAction):
        E.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "ararat", "group": ["afsin_beg"]})
    assert gs.to_json() == before
    result = E.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "ararat", "group": ["ibn_khan"]})
    assert set(result["group"]) == {"alp_arslan", "ibn_khan", "afsin_beg"}
    assert all(gs.lords[lid].cylinder == "ararat" for lid in result["group"])


# 20: simultaneous R9/S18 windows are Seljuk-first, including a declined window.
def test_20_winter_events_resolve_seljuk_then_roman():
    gs = game()
    gs.meta.calendar_box = 3
    gs.meta.phase = "campaign"
    gs.seljuk.held_events = ["S18"]
    gs.roman.held_events = ["R9"]
    C._end_campaign(gs)
    assert gs.meta.phase == "winter" and gs.meta.subphase == "winter.activation"
    assert gs.meta.notes["winter_holders"] == ["seljuk", "roman"]
    assert gs.meta.active_player == "seljuk"
    E.apply_action(gs, {"type": "winter_proceed"})
    assert gs.meta.active_player == "roman"


@pytest.mark.parametrize("removed", ["ibn_khan", "afsin_beg"])
def test_19_stack_survivor_is_unlinked_when_partner_disbands(removed):
    gs = game()
    for lid in ("ibn_khan", "afsin_beg"):
        place(gs, lid, {"turkic_horse": 1}, "ani")
    gs.lords["ibn_khan"].lower_lord = "afsin_beg"
    gs.lords["afsin_beg"].lieutenant_of = "ibn_khan"
    A._disband_at_limit(gs, gs.lords[removed])
    assert gs.lords["ibn_khan"].lower_lord is None
    assert gs.lords["afsin_beg"].lieutenant_of is None


@pytest.mark.parametrize("entry", ["standalone", "battle"])
@pytest.mark.parametrize("whole_marker", [False, True])
def test_03_turkic_removal_events_include_levied_units(entry, whole_marker):
    from seljuk import events
    gs = game()
    lord = place(gs, "romanos_diogenes", {})
    removed_at_start = len(gs.meta.themata_removed)
    lord.themata_on_mat = [ThemataMarker(unit="turkic_horse", symbols=2, home_thema="Charsianon")]
    remove = events._remove_turkic_at if entry == "standalone" else B._remove_turkic_at
    assert remove(gs, "melitene", 1, include_themata=whole_marker) == 1
    if whole_marker:
        assert lord.themata_on_mat == []
        assert len(gs.meta.themata_removed) == removed_at_start + 1
    else:
        assert C._unit_count(lord) == 1
        assert len(lord.themata_on_mat) == 1
        assert lord.themata_on_mat[0].symbols == 2


def test_03_lord_display_includes_surviving_and_routed_themata():
    from seljuk import render
    gs = game()
    lord = place(gs, "romanos_diogenes", {"militia": 3})
    lord.themata_on_mat = [ThemataMarker(unit="militia", symbols=2, routed=1)]
    assert lord.unrouted_forces() == {"militia": 4}
    assert lord.routed_forces() == {"militia": 1}
    display = render.lord_view(gs, lord.id)
    assert render._forces_str({"militia": 4}) in display
    assert "1 routed; marker x2" in display


def test_07_cli_json_combat_decisions_match_python_session(tmp_path, capsys):
    from seljuk.cli import main
    from seljuk.llm import LLMSession
    gs = game()
    a = place(gs, "alp_arslan", {"ghulam_cavalry": 8}, "antioch")
    d = place(gs, "chatatourios", {"tagmata": 8}, "antioch")
    d.besieged = True
    gs.locales["antioch"].siege_markers = 2
    command(gs, d.id)
    path = tmp_path / "game.json"
    path.write_text(gs.to_json(), encoding="utf-8")
    action = {"type": "cmd_sally", "lord": d.id, "battle_decisions": [("concede", True)]}
    session = LLMSession(gs)
    expected = session.apply(action)
    assert expected["sally"]["conceder"] == "attacker"
    assert main(["do", "--file", str(path), "--action", json.dumps(action)]) == 0
    actual = json.loads(capsys.readouterr().out)
    assert actual == json.loads(json.dumps(expected))
    assert GameState.from_json(path.read_text()).to_json() == session.gs.to_json()


def test_08_javelins_round_declaration_reaches_battle_and_resets(monkeypatch):
    gs = game()
    lord = place(gs, "ibn_khan", {"infantry": 3})
    lord.capabilities = ["S11"]
    place(gs, "chatatourios", {"tagmata": 4})
    command(gs, lord.id)
    seen = []
    resolve = B.resolve_battle

    def wrapper(*args, **kwargs):
        seen.append(args[0].lords[lord.id].flags["javelins_round"])
        return resolve(*args, **kwargs)

    monkeypatch.setattr(B, "resolve_battle", wrapper)
    B.begin_battle(gs, [lord.id], ["chatatourios"], "melitene", javelins_rounds={lord.id: 2})
    assert seen == [2]
    assert "javelins_round" not in lord.flags


@pytest.mark.parametrize("value", [("retreat", "melitene"), ["retreat", "melitene"]])
def test_07_bare_tuple_valued_choice_is_not_mistaken_for_typed_entry(value):
    ctx = B.DecisionContext([value])
    assert ctx.decide("retreat", [("retreat", "ani"), ("retreat", "melitene")]) == ("retreat", "melitene")
    assert not ctx.scripted


def test_01_snapshot_probe_does_not_consume_live_action_stream(monkeypatch):
    from seljuk.rng import action_roller
    gs = game(seed=27)
    expected = DiceRoller(27)
    monkeypatch.setitem(E._HANDLERS, "regression_roll", lambda gs, action, roller: roller.d6())
    with action_roller(gs) as live:
        assert live.d6() == expected.d6()
        copy = GameState.from_json(gs.to_json())
        E.apply_action(copy, {"type": "regression_roll"})
        assert live.d6() == expected.d6()
    assert E.roller_for(gs).get_state() == expected.get_state()
