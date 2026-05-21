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

**Phase 5 — LLM interface + audit agents (merged).** `src/seljuk/llm/` provides
the consumer interface: a hidden-information `view` (opponent deck/hand/unrevealed
Plan masked), a compact `briefing`, card/Lord/Locale `tools` lookups, and an
`LLMSession` (start_new / state / briefing / legal_actions / pending / apply /
lookups / save / load) that routes through the same engine and manages
Levy<->Campaign transitions. `scripts/self_play.py` is a greedy bug-finding
driver that plays every scenario to a terminal state; `scripts/roundtrip_sweep.py`
is the standalone enumerator/handler sweep. Both run as CI gates across all five
scenarios.

**The harness is feature-complete against the rules**, with the documented
remainders noted below. 210 tests pass.

### Known remainders (tracked, not silently skipped)
Most of the Phase-4/5 remainder is now closed (Phase 6): special-Vassal-adder
Capabilities (R2/R7/R17/S20), the remaining immediate/This-Campaign Event
resolvers, the Treachery/Loyalty Plan wiring (R8/S16/S19 + Imperial Coffers R14),
most Hold Events (Michael Attaleiates, Eastern Rebellions, Sultan's Horse,
Nomadic Tribes, Common Cultural Cause, Bad Omens, Summer Heat, Kleisourai,
Honors of War, plus Mountain Ambush and Betrayal in Battle), the Relief Sally
core (besieged Lords join a relief Attack, 4.8.1), and a combat-aggressive
self-play agent. Still genuinely open (each needs invasive timing/ordering work):
- Cavalry Charge (R24) and Command Confusion (S6) — per-Lord Strike sub-ordering
  within a step.
- Surprise (S1, besiege-2-then-Storm), Winter Campaign / Winter March (R9/S18,
  a pre-Bounty activation window), Local Scouts (R18, forcing an Avoider to
  Battle), Basil Alousianos (R7, Surrender-to-Bypass).
- The full Relief Sally rearguard rows + Siegeworks-vs-Sallying-only nuance
  (the core join-the-attack is implemented; rows are approximated).

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
