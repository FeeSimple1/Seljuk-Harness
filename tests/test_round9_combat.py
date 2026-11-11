"""Guard Pursuit exemption and Steeled Resolve missile provenance."""

import pytest

from seljuk import battle, engine
from seljuk.invariants import check_invariants
from seljuk.rng import DiceRoller
from seljuk.state import GameState
from tests.test_round8_combat import _capability, _dispatch, _place, _position


def _guard_position(infantry=1):
    state = _position(2, "chatatourios")
    _place(state, "chatatourios", {"infantry": infantry}, "laodikeia")
    _place(state, "alp_arslan", {"infantry": 2}, "antioch")
    # Resolve R16 in its ordinary immediate-Event window, then construct
    # the later Campaign position. This obtains the Guard from the pool.
    state.meta.phase = "levy"
    state.meta.pending = [{"type": "event_pending_resolution", "card": "R16",
                           "side": "roman", "tags": ["immediate"]}]
    event = {"type": "resolve_event", "card": "R16", "args": {"lord": "chatatourios"}}
    assert _dispatch(state, event)["added_varangian"] == "chatatourios"
    state.meta.phase, state.meta.subphase, state.meta.pending = "campaign", "campaign.command", []
    target = state.locales["antioch"]
    target.conquered_side, target.conquered_count = "seljuk", 3
    return state


def _stand(state, active, enemy, concede):
    _dispatch(state, {"type": "cmd_march", "lord": active, "to": "antioch"})
    return {"type": "respond_approach", "choices": {enemy: {"action": "stand"}},
            "battle_decisions": {state.lords[active].side: [
                ["concede", concede], ["concede", True],
            ]}}


def _observe_protection(monkeypatch, state, resolve):
    restored = GameState.from_json(state.to_json())
    trace = []
    original = battle._roll_protection

    def observe(gs, lord, unit, hit_type, protection, ctx, roller, rerolls_used):
        saved = original(gs, lord, unit, hit_type, protection, ctx, roller, rerolls_used)
        trace.append((lord.id, unit, hit_type, protection, saved))
        return saved

    with monkeypatch.context() as patch:
        patch.setattr(battle, "_roll_protection", observe)
        result = resolve(state)
    assert resolve(restored) == result
    assert restored.to_json() == state.to_json()
    assert not check_invariants(state)
    return result, trace


def _attack(result, step):
    return next(s for s in result["strikes"]
                if s["round"] == 1 and s["by"] == "attacker" and s["step"] == step)


@pytest.mark.parametrize("concede", [False, True])
@pytest.mark.parametrize("infantry", [1, 2])
def test_varangian_guard_hits_are_exempt_from_pursuit(concede, infantry):
    state = _guard_position(infantry)
    move = _stand(state, "chatatourios", "alp_arslan", concede)
    result = _dispatch(state, move)["battle"]
    # The Guard contributes three, and only the Infantry are halved.
    assert _attack(result, "foot_melee")["hits"] == (4 if concede else 3 + infantry)
    assert "infantry" in _attack(result, "foot_melee")["routed_units"]


def _javelin_position(forces, *, steeled, simultaneous="off"):
    state = _position(9, "sav_tekin")
    _place(state, "sav_tekin", forces, "laodikeia")
    _place(state, "chatatourios", {"infantry": 4}, "antioch")
    _capability(state, "seljuk", "S11", "sav_tekin")
    if steeled:
        _capability(state, "roman", "R3", "chatatourios")
    origin = state.locales["laodikeia"]
    origin.conquered_side, origin.conquered_count = "seljuk", 1
    state.meta.options["simultaneous_horse"] = simultaneous
    return state


@pytest.mark.parametrize("steeled", [False, True])
@pytest.mark.parametrize("forces", [{"infantry": 2}, {"infantry": 1, "ghulam_cavalry": 1}])
def test_steeled_resolve_does_not_save_infantry_from_javelins(monkeypatch, steeled, forces):
    state = _javelin_position(forces, steeled=steeled)
    move = _stand(state, "sav_tekin", "chatatourios", True)
    result, trace = _observe_protection(monkeypatch, state, lambda s: engine.apply_action(s, move))
    # With Pursuit the ordinary total is one Hit in both cases; the mixed
    # fractional Hit contains Javelins and gains no vs-Horse bonus.
    first = _attack(result["battle"], "missile")
    assert first["hits"] == 1 and first["routed_units"] == ["infantry"]
    assert trace[0] == ("chatatourios", "infantry", "missile", (1, 3), False)


@pytest.mark.parametrize("simultaneous", ["off", "missiles", "both"])
def test_mixed_horse_and_javelins_keep_separate_protection_rules(monkeypatch, simultaneous):
    state = _javelin_position({"infantry": 2, "ghulam_cavalry": 2},
                              steeled=True, simultaneous=simultaneous)
    move = _stand(state, "sav_tekin", "chatatourios", True)
    _, trace = _observe_protection(monkeypatch, state, lambda s: engine.apply_action(s, move))
    assert [row[:4] for row in trace[:2]] == [
        ("chatatourios", "infantry", "missile", (1, 4)),
        ("chatatourios", "infantry", "missile", (1, 3)),
    ]
    assert trace[0][-1] is True  # The same seed's first die of 4 now saves against Horse.


def _strike(gs, active, *, enemy, second=None, step="missile", round_no=1, pursuit=False, seed=9):
    attacker = battle._Side(gs, [active], "attacker")
    defender = battle._Side(gs, [enemy] if second is None else [enemy, second], "defender")
    attacker.front = dict(left=None, center=active, right=None)
    defender.front = dict(left=second, center=enemy, right=None)
    attacker.reserve = defender.reserve = []
    log = []
    battle._resolve_step(gs, step, attacker, defender, "attacker", {"attacker": pursuit},
                         round_no, battle.DecisionContext(), DiceRoller(seed=seed), log)
    return log


@pytest.mark.parametrize("horse", [False, True])
@pytest.mark.parametrize("marked_round", [2, 3])
def test_retargeted_missiles_use_their_origin_and_new_lords_mark(monkeypatch, horse, marked_round):
    active = "alp_arslan" if horse else "sav_tekin"
    state = _position(seed=9, active=active)
    _place(state, active, {"turkic_horse": 2} if horse else {"infantry": 2}, "laodikeia")
    _place(state, "chatatourios", {"militia": 1}, "antioch")
    _place(state, "romanos_diogenes", {"infantry": 3}, "antioch")
    _capability(state, "roman", "R3", "romanos_diogenes")
    state.lords["romanos_diogenes"].flags["steeled_resolve_round"] = marked_round
    if not horse:
        _capability(state, "seljuk", "S11", active)
        state.lords[active].flags["javelins_round"] = 2
    origin = state.locales["laodikeia"]
    origin.conquered_side, origin.conquered_count = "seljuk", 1
    _dispatch(state, {"type": "cmd_march", "lord": active, "to": "antioch"})
    # A later Round: the attacking left Front has already Routed.
    _, trace = _observe_protection(monkeypatch, state, lambda gs: _strike(
        gs, active, enemy="chatatourios", second="romanos_diogenes", round_no=2))
    assert [(lid, armor) for lid, _, _, armor, _ in trace] == [
        ("chatatourios", (1, 1)),
        ("romanos_diogenes", (1, 4) if horse and marked_round == 2 else (1, 3)),
    ]


@pytest.mark.parametrize("pursuit", [False, True])
def test_varangians_still_cannot_strike_in_later_rounds(pursuit):
    state = _guard_position()
    log = _strike(state, "chatatourios", enemy="alp_arslan", step="foot_melee",
                  round_no=2, pursuit=pursuit, seed=2)
    assert log[0]["hits"] == 1  # The single Infantry, with no Guard Strike.
