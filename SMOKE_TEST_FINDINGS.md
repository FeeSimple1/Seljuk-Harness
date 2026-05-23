# SMOKE Test Findings — Seljuk Harness

Append-only log of every bug surfaced during development and how it was fixed.
Nothing here is ever overwritten or deleted; the round-by-round history is the
institutional memory of the project (see CROSS_PROJECT_LESSONS.md §7).

Conventions (adopted from the audit methodology in the lessons docs):
- Each finding gets a sequential **SMOKE-NNN** id.
- Each finding records: the round it was found, the pattern it matches (see
  FUTURE_PROJECTS_LESSONS.md's 14 patterns), the rule citation, a one-line
  description, and the fix (commit / file / test).
- Add a source-marker regression test for each fix (`assert "SMOKE-NNN" in
  inspect.getsource(module)`) so a later refactor that drops the guard fails CI.

---

## Round log

### R000 — Phase 0 (skeleton)

Foundation only; no game logic, so no SMOKE findings yet. SMOKE numbering
begins once handlers and the legal-moves enumerator exist (Phase 2+), at which
point the enumerator/handler round-trip sweep (CROSS_PROJECT_LESSONS.md §2)
becomes the primary detector.

### R001 — SMOKE-001: Strategic Objective "place" enumerated without a target

**Pattern:** enumerator/handler divergence (CROSS_PROJECT_LESSONS.md sections
1-2; FUTURE_PROJECTS_LESSONS.md "arg-shape/semantic mismatch").
**Found by:** the Phase 2 Levy round-trip sweep
(`tests/test_phase2_roundtrip_sweep.py`) on the Specter scenario.
**Symptom:** `enumerate_call_to_arms` emitted a single
`{"type":"cta_strategic_objective","mode":"place"}` move with no `target`, but
`h_cta_strategic_objective` requires a `target` (3.5.3) and rejected it with
`bad_so_target`.
**Fix:** the enumerator now emits one concrete `place` move per legal target —
each Mustered enemy Seljuk Lord and each Enemy Stronghold in the Sultanate.
Marked `SMOKE-001` in `src/seljuk/actions.py`.

### R-hardening — SMOKE-002: self-play driver strands a revealed Treachery card (false stall)

**Pattern:** harness-vs-driver divergence / incomplete sub-decision handling
(CROSS_PROJECT_LESSONS.md: "agents surface stalls"; the driver itself was the
agent that under-resolved a pending).
**Found by:** a hardening pass running `self_play.play_game` across all five
scenarios at seeds 1–5 and asserting `over is True`. `emperor_and_the_lion`
seed=2 returned `over=False` at step 64 (calendar box 3) — not a max-steps
timeout — i.e. `legal_actions()` was empty while the game was neither over nor
owed a pending decision.
**Symptom:** the active Seljuk Plan slot was a Treachery card
(`active_card="treachery"`, `active_lord=None`, `actions_remaining=0`,
`pending=[]`). `_reveal_next` (4.2 / 1.4.1) correctly enqueues a
`loyalty_check` pending when it reveals a Treachery card, and
`h_resolve_loyalty` is what calls `_after_card` to advance the Command
sequence. But `self_play._resolve_pending` had no `loyalty_check` case, so it
fell through to the `else: pending.remove(p)` branch, deleting the pending
WITHOUT running the handler. `_after_card` was never called, leaving the
Treachery card stranded as `active_card` with no legal moves forever.
**Root cause:** the bug-finding driver, not the engine. Resolving the
`loyalty_check` through the proper action (`{"type":"resolve_loyalty",...}`)
lets the same game complete normally (winner=roman, box=5). The smoke fuzzer
already handled `loyalty_check`, which is why only the greedy driver stalled.
**Why it was masked:** `test_self_play_reaches_terminal` ran seed=1 only (no
Treachery on that path), and `test_invariants_fuzz` tolerates an empty-moves
break (a stalled state still satisfies all invariants).
**Fix:** `scripts/self_play.py::_resolve_pending` now handles `loyalty_check`
(and `basil_response`, for parity with the fuzzer and the documented pending
set). Marked `SMOKE-002`. `tests/test_phase5b_selfplay.py` now parametrizes
`test_self_play_reaches_terminal` over seeds 1–5 and adds a source-marker
regression test (`test_self_play_resolves_loyalty_check`).
**No engine change:** `src/seljuk/` is untouched; the harness already resolves
Treachery/Loyalty correctly via the consumer interface.
