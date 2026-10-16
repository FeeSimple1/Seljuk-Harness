"""Measure actual helper stdout, INCLUDING navigation and inspection follow-ups.

Usage: python scripts/benchmark_llm_interface.py --baseline-root /path/to/base \
          --output /tmp/seljuk-interface-measurements

The baseline is imported in a separate process; never measure the old helper
against new briefing/filter code. No model calls or inferred thinking tokens.
With tiktoken installed, report exact o200k_base counts; otherwise token counts
are null and only exact characters/UTF-8 bytes are reported (no chars/4 claim).
Transcripts combine both players' private test contexts: keep them trusted.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = '18d03047effb527dced80679cefcdd01341a2e9c'


class Meter:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []

    def call(self, name, fn, *args, supplement=False, **kwargs):
        out = io.StringIO()
        with redirect_stdout(out):
            result = fn(*args, **kwargs)
        text = out.getvalue()
        self.rows.append({'call':name, 'supplement':supplement, 'output':text})
        if isinstance(result, dict) and 'error' in result:
            raise AssertionError((name, result))
        return result

    def emit(self, name, data, supplement=True):
        return self.call(name, lambda: print(json.dumps(data, ensure_ascii=False, separators=(',',':'))),
                         supplement=supplement)

    def save(self, final):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in self.rows))
        def counts(rows):
            return {'calls':len(rows), 'characters':sum(len(r['output']) for r in rows),
                    'utf8_bytes':sum(len(r['output'].encode()) for r in rows)}
        return {'raw':counts([r for r in self.rows if not r['supplement']]),
                'with_lookup_repairs':counts(self.rows),
                'calls_by_method':dict(Counter(r['call'] for r in self.rows)),
                'transcript_sha256':hashlib.sha256(self.path.read_bytes()).hexdigest(),
                'final':final}


def worker(args):
    source = Path(args.source_root)
    sys.path[:0] = [str(source/'src'), str(source/'scripts')]
    import chatgpt_play_helper as nv
    from seljuk.llm import LLMSession
    from seljuk import engine, scenarios, static_data as sd
    from seljuk.state import GameState
    record = json.loads(Path(args.dataset).read_text())[args.workload]
    actions = record['actions']
    compact = args.mode == 'compact'
    meter = Meter(args.transcript)
    with patch('secrets.token_bytes', return_value=b'benchmark-key-not-for-real-saves!!'):
        meter.call('start', nv.start, record['scenario'], seed=record['seed'])
    if compact:
        from llm_interface_replay import prepare, canonical, position
    cards_seen, lords_seen, places_seen = set(), set(), set()
    original_texts = json.loads((ROOT/'src/seljuk/data/static/llm_references.json').read_text())
    # Both get the same unabridged adjudications, once, not repeated per action.
    if compact:
        meter.call('reference', nv.reference, 'decisions', full=True)
    else:
        meter.emit('reference_complete', original_texts['decisions']['text'])
    for n, action in enumerate(actions, 1):
        gs = nv._S['session'].gs
        # These are fixed, reproducible inspection requests. Decision oracle is
        # the recorded action, not a model policy or a strategic menu filter.
        card = action.get('card')
        if card and card not in cards_seen:
            meter.call('lookup_card', nv.lookup_card, card)
            if not compact:
                # Old stdout clips structured fields and omits the curated
                # mechanics. Count an explicit intact completion request.
                from seljuk.llm.tools import lookup_card
                import re
                text = original_texts['cards']['text']
                sections = list(re.finditer(r'^([RS]\d+)\. .+$', text, re.M))
                match = next(i for i, m in enumerate(sections) if m[1] == card)
                end = sections[match+1].start() if match+1 < len(sections) else len(text)
                meter.emit('card_complete', {'data':lookup_card(card),'reference':text[sections[match].start():end]})
            cards_seen.add(card)
        lid = action.get('lord')
        if lid and lid not in lords_seen:
            meter.call('lookup_lord', nv.lookup_lord, lid)
            if compact:
                meter.call('state', nv.state, path='/lords/'+lid, full=True)
            else:
                meter.call('state', nv.state)
                # Restores the requested subtree, not another truncated root.
                meter.emit('state_subtree_complete', nv._S['session'].state(nv._active_side())['lords'][lid])
            lords_seen.add(lid)
        if action['type'] == 'cmd_march':
            place = gs.lords[action['lord']].cylinder
            if place not in places_seen:
                meter.call('map', nv.map, place)
                places_seen.add(place)
        if not compact:
            if action['type'] == 'build_plan':
                meter.call('plan_help', nv.plan_help)
            elif action['type'] in engine._PALETTE_TEMPLATES:
                # The old helper prints _desc only; print the returned intact
                # template constraints as a counted follow-up, not free data.
                selected = next(m for m in nv._menu(False) if m['type'] == action['type'])
                meter.emit('template_hints', selected, supplement=False)
            meter.call('apply', nv.apply, deepcopy(action))
            assert len(nv._S['session'].gs.history) == n, (n, action)
            continue
        actor = nv._UI.owed
        primary, extra, expected, control = prepare(gs, action, actor)
        page = meter.call('actions', nv.actions, type=action['type'], limit=6)
        first_variant = page['entries'][0] if page['entries'] else None
        direct_variant = False
        while True:
            row = next((r for r in page['entries'] if all(primary.get(k) == v for k,v in r['action'].items())), None)
            if row:
                break
            if not page['next_cursor']:
                # Some legal parameter combinations have no default concrete
                # row (e.g. group Carts make a solo discard unnecessary). Read
                # the complete handler and use the documented versioned flat
                # action path; count BOTH requests, never alter its parameters.
                if first_variant is None:
                    raise AssertionError(('recorded action category not found', n, primary))
                row, direct_variant = first_variant, True
                meter.call('implementation', nv.implementation, action['type'])
                break
            page = meter.call('actions_next', nv.actions, cursor=page['next_cursor'])
        if row['kind'] == 'template' or row.get('parameters_available'):
            meter.call('plan_help' if action['type'] == 'build_plan' else 'details',
                       nv.plan_help if action['type'] == 'build_plan' else nv.details,
                       *([] if action['type'] == 'build_plan' else [row['id']]))
        parameters = {k:v for k,v in primary.items() if k not in row['action']}
        if direct_variant:
            applied = meter.call('apply_variant', nv.apply, primary, version=nv._UI.version)
        else:
            applied = meter.call('apply', nv.apply, row['id'],
                                 **({'parameters':parameters} if parameters or row['kind']=='template' else {}))
        if nv._UI._joint:
            page = meter.call('response_actions', nv.actions)
            template = next(r for r in page['entries'] if r['kind'] == 'template')
            meter.call('response_details', nv.details, template['id'])
            if extra:
                applied = meter.call('supply_inputs', nv.apply, template['id'], parameters={'inputs':extra})
            else:
                decline = next(r for r in page['entries'] if r['action']['type']=='decline_inputs')
                applied = meter.call('decline_inputs', nv.apply, decline['id'])
        # Count every consequential-change continuation, not just page one.
        change_page = applied['changes']
        while change_page['next_cursor']:
            change_page = meter.call('changes_next', nv.changes, change_page['next_cursor'])
        result = nv._UI._receipts[-1][actor]['decision_result']
        if any(k in result for k in ('battle','storm','sally')):
            meter.call('combat_detail', nv.result, path='/combat_detail', full=True)
        assert canonical(result) == canonical(expected), (n, action)
        assert position(nv._UI.gs) == position(control), (n, action)
        # Serialize/reload every accepted action, no invisible game edits.
        nv._UI.session.gs = GameState.from_json(nv._UI.gs.to_json())
    gs = nv._S['session'].gs
    assert nv._S['session'].is_over()
    final = {'actions':len(actions), 'winner':nv._S['session'].winner(), 'vp':scenarios.score(gs)}
    assert final['winner'] == record['expected_winner'] and final['vp'] == record['expected_score']
    result = meter.save(final)
    Path(args.result).write_text(json.dumps(result, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root')
    parser.add_argument('--output', default='/tmp/seljuk-interface-measurements')
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--mode', choices=['legacy','compact'])
    parser.add_argument('--source-root')
    parser.add_argument('--dataset')
    parser.add_argument('--workload')
    parser.add_argument('--transcript')
    parser.add_argument('--result')
    parser.add_argument('--retokenize', action='store_true', help='Tokenize existing outputs after installing optional tiktoken')
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=True)
    if not args.retokenize:
        if not args.baseline_root:
            parser.error('--baseline-root is required (an untouched checkout)')
        sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
        from llm_interface_replay import records
        dataset = out/'datasets.json'
        dataset.write_text(json.dumps(records()))
        for workload in ('manzikert','showdown'):
            for mode, source in (('legacy',Path(args.baseline_root).resolve()),('compact',ROOT)):
                subprocess.run([sys.executable, __file__, '--worker', '--mode', mode,
                                '--source-root', str(source), '--dataset', str(dataset), '--workload',workload,
                                '--transcript', str(out/f'{workload}-{mode}.jsonl'),
                                '--result', str(out/f'{workload}-{mode}.json')], check=True)
    try:
        import tiktoken
        encoding = tiktoken.get_encoding('o200k_base')
    except ImportError:
        encoding = None
    summary = {'baseline_commit':BASE_COMMIT, 'tokenizer':'o200k_base' if encoding else None,
               'method':'Actual printed helper responses plus counted follow-ups; no input/thinking tokens. Each response tokenized separately.',
               'workloads':{}}
    for workload in ('manzikert','showdown'):
        variants = {}
        for mode in ('legacy','compact'):
            data = json.loads((out/f'{workload}-{mode}.json').read_text())
            transcript = [json.loads(line) for line in (out/f'{workload}-{mode}.jsonl').read_text().splitlines()]
            for key, rows in (('raw',[r for r in transcript if not r['supplement']]),('with_lookup_repairs',transcript)):
                data[key]['tokens'] = sum(len(encoding.encode(r['output'], disallowed_special=())) for r in rows) if encoding else None
            data['characters_by_method'] = dict(Counter())
            for row in transcript:
                key = row['call']
                data['characters_by_method'][key] = data['characters_by_method'].get(key,0) + len(row['output'])
            variants[mode] = data
        assert variants['legacy']['final'] == variants['compact']['final']
        variants['character_reduction_vs_legacy_raw'] = 1-variants['compact']['raw']['characters']/variants['legacy']['raw']['characters']
        if encoding:
            variants['token_reduction_vs_legacy_raw'] = 1-variants['compact']['raw']['tokens']/variants['legacy']['raw']['tokens']
        summary['workloads'][workload] = variants
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
