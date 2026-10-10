# Longest-scenario fixes — 2026-10-10

Based on the four findings from The Emperor and the Lion at commit
`f1cd077be15d7a4c97b36877d0a77961c41c7d02`. These are changes to the existing
rules implementation, not new rules or changes to recorded adjudications.

## Fixes

| Finding | Correction | Regression tests |
|---|---|---|
| EL-01: post-Battle Withdrawal omits investment | Refresh the battle locale and offer the mandatory Besiege/Bypass decision before recovery. Both choices end the spent card; a new Roman siege offers Themata defenders. Decisions survive save/load, cannot be skipped with a direct end/pass, and take precedence over Winter activation menus. Invalid choices leave the pending decision intact. Immediate victory is not delayed for a new investment. | `test_el01_*` |
| EL-02: Treachery omits mandatory opponent No Command | One shared predicate informs the Plan hint and direct validator. Treachery's extra Plan slot now requires a No Command, for either opponent, while Weather's existing requirement remains enforced. Invalid plans are rejected before mutation. | `test_el02_*` |
| EL-03: Reset deletes This-Campaign cards | Return cards to the draw deck before clearing seasonal effects. Handle Peace Offering/Gifts Exchanged as one physical S13 card, not two physical copies. Repeated Reset cannot return the same card twice. | `test_el03_*` |
| EL-04: relief leaves siege markers and allows friendly Storm | Immediately refresh investment after Avoid and after Battle; return defending Themata and release inside Lords when the last besieger leaves. Preserve a siege while any besieger remains. Siege/Storm eligibility independently requires a currently hostile, unruined stronghold or Fort marker; stale markers cannot authorize friendly attacks. | `test_el04_*` |

Authority: repository `reference/Seljuk Battle and Storm Reference.txt`,
Aftermath 4.8.6; `reference/Seljuk Sequence of Play Reference.txt`, Reset 4.7.5;
`reference/Seljuk Arts of War Reference.txt`, R8/S16/S19 Treachery, R17/S17
Weather and S13 Peace Offering/Gifts Exchanged; `source/rules.txt`, 3.1.3,
4.3.5, 4.5.1–2 and 4.8.6. The repository errata do not change these provisions.

## Evidence and test integrity

`tests/fixtures/longest_scenario_20261010.json` preserves five actual recorded
checkpoints, their original actions, and the invalid Treachery probe. Only the
old action history is removed to keep the fixture small; the game state and RNG
are unchanged. The accompanying `tests/test_longest_scenario_20261010.py` adds
37 cases, including the real reproductions, raw-menu and direct-action checks,
negative mutation tests, Winter/Conquered/Fort controls and card conservation.
Against the original source these cases produce **28 failures and 9 passes**.
Some checks cover newly introduced decision windows as well as original defects.

The pre-existing 132-action Manzikert fixture still submits exactly the same
132 actions and rationales and reaches the same winner, reason and score.
Ten expected hashes were rebaselined for real corrected behavior:

- Zero-based indices 43–44: the relieved Theodosiopolis siege clears immediately,
  rather than only after the Pay/Disband sequence.
- Indices 124–131: returning S17 to the deck changes the Autumn draw to S17
  instead of S6; the resulting Weather effect is represented in the saved state.

All per-action hash, invariant and JSON reload assertions remain in place.
The Honors of War positive fixture now chooses an actual enemy Fort, not the
first Fort regardless of allegiance. None of the original 864 tests or their
behavioral assertions were removed.

## Verification

- Full suite: **901 passed**, including all original 864 cases and 37 new cases.
- Original external longest-scenario specifications: **12 passed** (previously
  8 failures and 4 passing controls).
- Scenario move sweep: **5 scenarios × 5 seeds**, clean.
- Existing aggressive smoke driver: **30 runs**, zero reported findings.
- Entire 132-action Manzikert fixture replays with a JSON reload after each step.

The smoke scripts are automated diagnostics, not independent human games or a
proof of all rules. Some legacy driver branches discard unsupported event
choices; no claim of a fresh, fully rules-correct 12-turn game is made here.
The deterministic checkpoint tests exercise the reported failures directly.

Run from the repository root:

```bash
python -m pytest -q
PYTHONPATH=src python scripts/roundtrip_sweep.py --seeds 1,2,3,4,5
PYTHONPATH=src python scripts/smoke_fuzz.py --rounds 2 --seeds 1,2,3
```

## Delivery status

Implemented, tested and committed locally. This session's connected GitHub
actions provide repository reads but no write/merge action; direct GitHub access
from the execution environment fails name resolution. The downloadable patch
and corrected source package contain the changes. **They were not pushed or
merged into GitHub.**
