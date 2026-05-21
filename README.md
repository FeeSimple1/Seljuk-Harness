# Seljuk Harness

Python harness for GMT's *Seljuk* (Levy & Campaign Series, Volume V, 2025) —
the 11th-century campaigns in Anatolia between the Roman Empire and the Seljuk
Sultanate culminating at Manzikert. The harness will hold full game state,
validate and resolve every rules-defined action, run Battle and Storm
engagements automatically, roll all dice from a seeded RNG, and expose a
structured interface for an LLM playing one or both sides.

The detailed project specification is in [`BRIEF.md`](BRIEF.md). **Rules
accuracy and completeness are the priority** — see the hard constraints there.

## Status

**Phase 3b — March + Approach + Battle (merged).** Lords now move and fight.
March (4.3) covers adjacency, the cost model (Laden, Turkic-Horse first-march,
Pass, whole-card Holding-Box), Group March (4.3.1) and Lieutenant stacks; the
Approach decision tree (4.3.4: Avoid Battle / Withdraw / Stand) and Besiege/
Bypass (4.3.5) are pending sub-decisions. The full Battle engine (4.8) runs the
Array (3 Front + Reserve), Rounds (Concede + Pursuit halving, Reposition with
Reserve-advance and Center-fill), the six Strike steps in initiative order
(Missile then Melee; Defending then Attacking; Horse before Foot), Flanking,
Hits (summed Strike values, rounded up), Protection by Hit type (Armor / Evade
/ Unarmored), Rout, and the Ending (Retreat / Withdraw / Removal, Losses —
Harsh vs Normal, Spoils, Service shift, Lord Removal by Combat 4.8.5,
Aftermath). Player choices flow through a DecisionContext (typed scripted
entries for tests, else a deterministic fallback).

Next: Phase 3c (Siege, Storm, Sally, Relief Sally — Garrisons/Themata/
Siegeworks/Sack), then Phase 4 (the 50 Arts of War card effects) and Phase 5
(LLM interface + agents).

## Where things are

- `src/seljuk/` — the harness (module stubs in Phase 0). Intended layout:
  `state.py` (Pydantic state model), `static_data.py` + `data/` (JSON reference
  data), `scenarios.py` (loaders + victory math), `legal_moves.py` (the move
  enumerator), `actions.py` / `campaign.py` (per-action handlers), `battle.py`
  (Battle/Storm/Sally), `events.py` + `capabilities.py` (the 50 Arts of War
  cards), `map.py`, `rng.py`, `render.py`, `previews.py`, `cli.py`, and `llm/`
  (the Phase 5 consumer interface).
- `reference/` — the curated, errata-applied `.txt` references. **The first
  stop for any rules question** (see the consultation chain in `BRIEF.md`).
- `source/` — the authoritative PDFs: `Seljuk_Rules.pdf` (Rules of Play &
  Scenarios), the Errata & Clarifications PDF, and the Background Book
  (Playbook — examples and history, not a rules source).
- `tests/` — pytest suite. Phase 0 ships an import smoke test and the
  source-marker regression-test pattern.
- `scripts/` — agents and sweeps (Phase 5).

## How to run things (Phase 0)

```
pip install -e ".[dev]"
PYTHONPATH=src pytest -q
```

The Phase 0 suite verifies the package imports and that the CLI entry point
responds. A real test-per-rule suite accumulates from Phase 1 onward.

## Documentation map

- [`BRIEF.md`](BRIEF.md) — the project specification: source priority, scope
  constraint, the rules-accuracy and completeness hard constraints, the
  ambiguity/consultation chain, the no-agent constraint, architecture and
  interface requirements, the phase plan, and the engine/operator split for
  Battle decisions.
- [`RULES_DECISIONS.md`](RULES_DECISIONS.md) — adjudicated rules calls (the
  user's verbatim answer, citation, and commit hash). Permanent; never deleted.
- [`RULES_QUESTIONS.md`](RULES_QUESTIONS.md) — open rules questions awaiting
  user adjudication.
- [`SMOKE_TEST_FINDINGS.md`](SMOKE_TEST_FINDINGS.md) — append-only log of every
  SMOKE finding with round-by-round context. The institutional memory of bugs.
- [`FUTURE_PROJECTS_LESSONS.md`](FUTURE_PROJECTS_LESSONS.md) and
  [`CROSS_PROJECT_LESSONS.md`](CROSS_PROJECT_LESSONS.md) — game-agnostic
  bug-pattern catalogs (authored against Nevsky; kept verbatim).
- [`SELJUK_LESSONS_ADAPTATION.md`](SELJUK_LESSONS_ADAPTATION.md) — flags every
  Nevsky-specific reference in those two catalogs and maps each pattern to its
  Seljuk equivalent. **No Nevsky rules are used in this project.**

## Provenance

This is a private project. Nevsky-Harness was used only as a structural model
(see "Relationship to Nevsky-Harness" in `BRIEF.md`); none of its rules, data,
cards, scenarios, or code are included here. The authoritative rules sources,
in priority order, are the Errata & Clarifications, the curated `.txt`
references, the Rules of Play PDF, and the Background Book (examples only).
