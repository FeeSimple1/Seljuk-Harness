"""Regression utilities for recorded actions, never a policy or a player bot.

The recorded shared combat FIFO is separated by its ORIGINAL consumed owners.
A disposable reference execution records only consumption, not new choices.
Unconsumed trailing entries remain with the original submitting actor. Each
new-interface resolution must equal the reference result and complete state
(except private action-history representation of the two separate queues).
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

from seljuk import battle
from seljuk.llm import LLMSession
from seljuk.state import GameState

ROOT = Path(__file__).resolve().parents[1]


def records():
    man = json.loads((ROOT/'tests/fixtures/manzikert_selfplay_20261009.json').read_text())
    man['actions'] = [step['action'] for step in man['steps']]
    show = json.loads((ROOT/'tests/fixtures/interface_showdown_20261016.json').read_text())
    return {'manzikert': man, 'showdown': show}


def canonical(value):
    return json.loads(json.dumps(value))


def position(gs):
    out = gs.model_dump(mode='json')
    out.pop('history')  # execution inputs now contain separately owned queues
    return out


def prepare(gs, action, actor):
    """Return (primary, opponent_inputs, control_result, control_state)."""
    action = deepcopy(action)
    primary, extra = deepcopy(action), {}
    queues = defaultdict(list)
    consumed = []
    original = battle.DecisionContext.decide

    def trace(self, dtype, options, info=None):
        head = deepcopy(self.scripted[:1])
        n = len(self.scripted)
        answer = original(self, dtype, options, info)
        if len(self.scripted) < n:
            owner = (info or {}).get('side')
            if owner not in ('roman', 'seljuk'):
                raise AssertionError(f'missing owner for consumed {dtype}')
            queues[owner].append(head[0])
            consumed.append(head[0])
        return answer

    control = LLMSession(GameState.from_json(gs.to_json()))
    with patch.object(battle.DecisionContext, 'decide', trace):
        expected = control.apply(action)
    for field in ('battle_decisions', 'storm_decisions'):
        if field in primary:
            supplied = primary.pop(field)
            assert isinstance(supplied, list), 'record uses a legacy shared queue'
            assert canonical(supplied[:len(consumed)]) == canonical(consumed)
            queues[actor].extend(deepcopy(supplied[len(consumed):]))
            for side, queue in queues.items():
                (primary if side == actor else extra)[field] = queue
    for field in ('battle_events', 'steeled_rounds', 'javelins_rounds'):
        if field in primary:
            values = primary.pop(field)
            for key, val in values.items():
                side = key if field == 'battle_events' else gs.lords[key].side
                dest = primary if side == actor else extra
                dest.setdefault(field, {})[key] = deepcopy(val)
    if 'coins_against' in primary:
        extra['coins_against'] = primary.pop('coins_against')
    if primary.get('play_sultans_horse') and actor != 'roman':
        extra['play_sultans_horse'] = primary.pop('play_sultans_horse')
    if primary['type'] == 'resolve_event':
        primary.setdefault('args', {})
    if primary['type'] == 'assign_themata_defenders':
        primary.setdefault('markers', [])
    if primary.get('local_scouts'):
        raise AssertionError('Local Scouts three-stage sequence has a focused test, not this replay fixture')
    return primary, extra, expected, control.gs


def finish(interface, primary, extra):
    actor = interface.owed
    response = interface.apply(primary, version=interface.version)
    if interface._joint:
        if interface._joint.get('bad_omens'):
            # Fixture with an explicit order never gets here. Keep defaults out
            # of regression utility decisions as well as out of the interface.
            raise AssertionError('record must specify its Bad Omens order')
        if extra:
            response = interface.apply({'type':'supply_inputs','inputs':extra}, version=interface.version)
        else:
            response = interface.apply({'type':'decline_inputs'}, version=interface.version)
    assert not interface._joint
    return response, interface._receipts[-1][actor]['decision_result']
