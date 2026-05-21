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
