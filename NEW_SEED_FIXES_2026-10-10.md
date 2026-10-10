# Seed 20261012: four defect fixes

## Scope and authority

Fixes the four defects reported from the 1,022-action Emperor and the Lion
playtest on `b1ace4bb2956c44972697349b7386561aadf3cc5`. No house rules,
scenario setup changes, old-save migrations, or replacement dice are added.

Rules authority remains the repository's references and recorded decisions:
`source/rules.txt` 1.4/1.4.1 and 4.5.1; `reference/Seljuk Battle and Storm
Reference.txt` 4.9.1, Remove Themata; `reference/Seljuk Arts of War Reference.txt`
R13 Thrakion Reinforcements. These rules remove captured defenders from active
play while retaining physical counters that R13 can return, and assign loyalty
counterpayment to the revealing player's opponent, not the target's owner.

## Fixes

| Finding | Correction | Regression coverage |
|---|---|---|
| NS-01: Surrender loses defending Themata counter records | A shared capture helper transfers defending markers into the removed pool for both Conquer and Ruin. Sack no longer performs a separate transfer, so it cannot duplicate those counters. | Recorded Melitene Surrender; R13 return; all four Conquer/Ruin/Sack paths; double-marker identity; JSON persistence; no transfer when Surrender is declined. |
| NS-02: Loyalty counterpayment uses the wrong faction | A single pair-of-budgets helper derives the paying sides from the revealing player and opponent. Both planning menus and the resolver use it, independent of the target's current allegiance. | Recorded Robert Crepin position; both revealing factions; already-switched and opposing targets; besieged-target restrictions. |
| NS-03: Rejected second payment consumes the first | The complete request is validated before either side spends or any die rolls. Imperial Coffers also retains its card and pending window when payment is rejected. | Direct resolver, Treachery, and Imperial Coffers; over-budget first/second payments; unchanged full state and RNG; rejected-request retry matches a fresh valid action. |
| NS-04: Negative amounts grant free modifiers | Both amounts must be nonnegative integers. Handlers no longer silently coerce malformed values with int(). | Both fields through all three entry points; negative, fractional, floating-point, Boolean, string, null, list, and object values; legal payments and natural-1/natural-6 controls. |

The Imperial Coffers card-preservation check closes the same rejection problem
at the second caller of the shared loyalty resolver. Successful checks still
consume the Capability once. The fix is specific to loyalty-payment rejection;
it is not a claim that every action in the harness is now transactional.

## Reproducible checkpoints and tests

`tests/fixtures/new_seed_20261012/` contains the two original game positions,
with only their prior history lists omitted. All position, pending, and RNG
fields are retained. The accompanying README identifies the recorded actions.

`tests/test_new_seed_20261012_fixes.py` adds **88 cases**. On the original source,
**70 fail and 18 controls pass**. With the corrections, all **88 pass**.
The original supplied reproductions separately change from **7 failures and
4 controls passing** to **all 11 passing**.

No existing tests, assertions, or expected replay hashes were changed.
The full suite passes **989 tests**: all **901 existing cases** plus the
**88 new cases**, with no failures, errors, or skips.

## Recorded full-game replay verification

The saved seed-20261012 game was replayed with every original accepted action
unchanged. This was a replay verification, not another newly played game.

- All **1,022 action results** match the recorded results.
- Save/load was checked before every action.
- All **30 physical Themata markers** are conserved after every action.
- There are no built-in invariant failures.
- All 12 Campaigns and three Winters complete, with the same Roman **16-2**
  final-scoring result.
- Before Melitene's Surrender, state hashes are unchanged. From action 950
  onward, the only state change is the two newly retained Melitene counter
  records. All **2,044 before/after state comparisons** match the originals
  when those exact two records are omitted from a temporary comparison view.
  They remain present in the real corrected game state throughout.

Corrected terminal SHA-256:
`c430321135335abc8e2cd21846bb985cc746c895320dc60f6999e554139fb39a`.

The retained counters are one double-Infantry marker and one Tagmata marker,
both with home Thema Melitene. They are removed from play, not automatically
returned to the map or a Lord; R13 remains the means to return a removed marker.

## Repeatable checks

```bash
python -m pytest -q
PYTHONPATH=src python scripts/roundtrip_sweep.py --seeds 1,2,3,4,5
PYTHONPATH=src python scripts/smoke_fuzz.py --rounds 2 --seeds 1,2,3
```

The permanent repository CI runs this suite, the 25 scenario/seed move sweeps,
and the 30 aggressive smoke checks. Tests support these fixes and neighboring
behavior; they are not proof that every reachable position is defect-free.
