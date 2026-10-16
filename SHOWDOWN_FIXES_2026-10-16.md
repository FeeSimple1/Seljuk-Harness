# Showdown and physical-counter corrections (2026-10-16)

## Scope and authorities

The three confirmed defects came from the 338-action Showdown in Anatolia
self-play (seed `20261016`). Rules of Play 3.5.3 limits the game to three
Strategic Objective counters; 3.3.1 / 4.5.1 / 4.9.1 retain earned Objectives
in Constantinople. R13 Thrakion Reinforcements returns physical Themata
previously removed from play. This changes rules implementation and setup
accounting, **not** strategic move ranking, automatic decisions, or the compact
LLM interface. No house rule has been added.

- **SD-01: fourth Strategic Objective minted.** Both the raw palette and the
  executor now use the same exact counter inventory: three minus markers in
  the available pool, on Lords, on Locales, claimed in Constantinople, and
  removed at scenario setup. Claimed SO counters are tracked separately from
  ordinary Roman Conquered/Unity 1-VP markers in the same holding box; they
  never go back into the available supply.
- **SD-02: duplicate placement deletes a marker.** Direct submissions to an
  already marked Seljuk Lord or qualifying Stronghold are rejected before
  taking a marker, changing phase/turn, or consuming the dice stream. The raw
  menu continues to omit such targets.
- **SD-03: setup-removed Themata vanish.** All scenario-specific removals now
  relocate the original counters to the removed-from-play pile with their
  full printed symbol counts and home Thema. This fixes Showdown's nine
  missing markers and the same underlying omission in the other scenarios.
  R13 can return the removed markers normally; no marker is fabricated.

The always-on invariant checker now flags overdrawn Strategic Objective
inventory. It does not prune actions based on perceived strategic value.

## Testing and saved games

`tests/test_showdown_20261016_rules.py` adds direct regressions at the exact
saved action-302 Showdown position; raw + validated menu coverage; successful
valid placements and claims; R20 returns; all five scenario setup inventories;
R13 return of previously setup-removed counters; legacy setup SO limits;
JSON round trips; and no-mutation rejections. It saves the original
pre-exploit game position in `tests/fixtures/showdown_rules_20261016/`.

Four preexisting synthetic fixtures had implicitly assumed the setup removed
pile was empty. They now assert the same *increment* in physical counters or
select the newly removed Thema explicitly without discarding setup counters.
All their original tested behaviors remain asserted.

The 132-action Manzikert replay retains every originally accepted action and
its terminal winner and VP, with hashes regenerated for the now-correct setup
counter inventory and SO bookkeeping. The complete 338-action Showdown
interface replay replaces the previously illegal fourth SO `take` (action 302)
with the legal `pass_step`, matching the previously recorded control
continuation's winner and VP. The implementation tests compare state/RNG
against direct execution for every action and honor the respective players'
choices and information restrictions.

Existing trusted saves from before this correction remain parseable. A save
from a game that already claimed Strategic Objectives before this patch may
lack the new `strategic_objectives_claimed` note, and previously discarded
setup-removed Themata cannot be reconstructed unambiguously from arbitrary
partial save histories. For exact physical inventory, start a new game from
this version or use a verified full replay/migration of the old save; the
engine does not silently guess that every Roman VP marker represents an SO.

## Reproduce

```bash
python -m pytest -q tests/test_showdown_20261016_rules.py
python -m pytest -q
PYTHONPATH=src python scripts/roundtrip_sweep.py --seeds 1,2,3,4,5
PYTHONPATH=src python scripts/smoke_fuzz.py --rounds 2 --seeds 1,2,3
```

These tests demonstrate the three known fixes and neighboring rules. They do
not prove all legal states are covered or that the harness is unbeatable.
