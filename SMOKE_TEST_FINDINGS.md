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

### R-playtest — SMOKE-003: skip_first_levy scenarios re-draw Capabilities on their first played Levy

**Pattern:** lifecycle/flag initialization gap (a setup step that stands in for
a skipped phase must also set the phase's "done" flag) — surfaces as a silent
rules divergence, not a crash or invariant violation.
**Found by:** a purposeful solo playthrough of `manzikert` (the structural
sweeps/fuzzers never flagged it: drawing Capabilities instead of Events keeps
all invariants valid and the enumerator/handler in sync, so only rules-aware
play notices). At the box-11 (Summer) Levy, three `deploy_capability` pendings
(S21, R22, R18) appeared and lingered through the rest of the turn.
**Symptom:** `manzikert` and `year_of_treacherous_ambition` set
`skip_first_levy=True` and start mid-campaign in `campaign.plan` with their
Capabilities pre-placed by setup (`board_edge_capabilities` + per-Lord). The
loader left `notes["first_aow_done"]` unset, so the first PLAYED Levy's Arts of
War (`actions.resolve_arts_of_war`) computed `first = not first_aow_done = True`
and performed a First-Levy Capability deploy (A.1.2 / 3.1.2) instead of the
required later-Levy Event draw (A.1.3 / 3.1.3) — deploying Capabilities a second
time on top of the pre-placed ones.
**Consultation (BRIEF chain):** Sequence of Play reference A.1.2 vs A.1.3 (first
Levy = Capabilities, second-or-later = Events). Decisive check: the scenario
JSON pre-places Capabilities, so a first-Levy draw at the first played Levy
double-deploys them — unambiguously wrong. No external sources consulted.
**Fix:** `scenarios.py::load_scenario` now sets
`notes["first_aow_done"] = bool(skip_first_levy)`. A skip_first_levy scenario's
setup pre-placement IS its First Levy Arts of War, so its first played Levy
correctly draws Events. Non-skip scenarios are unchanged (flag False at load;
`start_new`'s opening Arts of War sets it). Verified: `manzikert` box-11 Levy now
classifies draws as Events (held/this-campaign/immediate), no `deploy_capability`
pendings. Marked `SMOKE-003` in `src/seljuk/scenarios.py`. Tests:
`tests/test_phase2_aow_cta_loyalty.py::test_skip_first_levy_treats_setup_as_first_aow_smoke003`
and `::test_load_scenario_first_aow_done_matches_skip_first_levy_smoke003`.

### R-advisory — SMOKE-004: co-location invariant added; fuzzer stranded Lords by dropping an Approach

**Pattern:** missing invariant + driver mishandling of an un-satisfiable pending
(cf. Inferno-Harness Retreat advisory; same class as SMOKE-002).
**Context:** acting on the Inferno-Harness cross-project advisory ("Retreat that
penalizes but never relocates"). The advisory's MAIN bug is ABSENT here: Battle
(`battle._lord_fate`) and Sally (`battle._end_sally_besiegers_lose`) both
RELOCATE the losing Lord's `cylinder` (and a Storm correctly does not retreat
the attacker). Verified on the cold "Concede -> loser survives -> Retreat"
branch: a scripted Attacker Concede leaves the loser alive, relocated out of the
battle Locale, still Mustered (test `test_phase3b_battle::
test_conceding_loser_relocates_no_colocation_4_8_3`).
**What was missing / found:** there was no invariant forbidding the illegal
"opposing un-besieged Lords share a Locale" state (advisory #3). Added one in
`invariants.py`, keyed on the `besieged`/`bypassed` flags and excluding the
legitimate mid-Approach transient. With it active, the aggressive smoke fuzzer
surfaced that `smoke_fuzz._rand_resolve_pending` resolved an `approach_response`
by trying "withdraw" even with no Friendly Stronghold present; the engine
correctly rejects it, after which the driver's `except -> pending.remove` left
the attacker and defender stranded co-located.
**Fix:** `scripts/smoke_fuzz.py` now falls back to "stand" (always legal,
triggers the Battle) when a random Approach choice is rejected. The co-location
invariant + the concede regression test are the durable guards. Marked
`SMOKE-004`. Engine unchanged for this item.

### SMOKE-005 (OPEN) — stale `locale.bypass` suppresses Approach against a fresh un-bypassed enemy Lord

**Pattern:** lifecycle leak (a flag set but never cleared) producing an illegal
board state — surfaced by the new SMOKE-004 co-location invariant.
**Symptom (reproduced deterministically):** `locale.bypass` is set True when a
Lord Bypasses a Stronghold (`campaign.h_besiege_bypass`) but is never cleared
when the bypassing Lord leaves, nor at End Campaign (only `battle.py` clears it
post-combat). `campaign._resolve_arrival` does `if gs.locales[to].bypass:
enemy_lords = []`, so once a Locale's bypass flag is stale, a later enemy Lord
marching in triggers NO Approach (4.3.4) and the two opposing Lords end
un-besieged, un-bypassed, co-located. The same stale flag also blocks a later
Besiege (`_resolve_arrival` line ~1185).
**Rule basis:** Battle & Storm reference: Approach fires on an "Unbesieged,
**Unbypassed** Enemy Lord"; the `bypassed` state is per-Lord, not a permanent
property of the Locale.
**Why not fixed yet:** the correct lifecycle of `locale.bypass` (cleared when
the last bypasser leaves? at End Campaign? or replace the blanket
locale-level suppression with a per-Lord `bypassed` exclusion in
`_enemy_lord_ids_at`?) is a Rules-of-Play 4.3.5 / design question; needs
consultation before a fix to avoid a regression. Surfaced to the user.

### SMOKE-006 (OPEN) — Retreat destination rules incomplete (4.8.3)

**Pattern:** rules-coverage gap (clear rule, partially enforced).
**Symptom:** `battle._lord_fate` (Battle) and `battle._end_sally_besiegers_lose`
(Sally) build Retreat options by excluding adjacent Locales that contain enemy
**Lords**, but NOT those containing an enemy **Stronghold** that is not already
Besieged or Bypassed (4.8.3 A). Two further 4.8.3 restrictions are unenforced
because the approach breadcrumb is dropped: "Defenders may NOT Retreat along the
Way the Attackers Approached" and "Marching Attackers MUST Retreat to the Locale
whence they Approached." `campaign.h_respond_approach` even computes an
`attacker_origin` variable, but it reads the attacker's CURRENT cylinder (= the
battle Locale, since the March already moved them) and is unused — the true
origin is never recorded on the March / approach pending.
**Impact:** legal-state correctness (offers/forces illegal Retreat
destinations), not an illegal co-location. Does not trip the SMOKE-004 invariant.
**Fix scope:** the enemy-Stronghold exclusion is contained; the approach-Way
rules require recording the March origin (h_cmd_march -> approach_response
pending -> battle). Surfaced to the user for scope.

### SMOKE-005 — RESOLVED

Rules of Play 4.3.5 / 4.4.1 confirm: "A Locale can only have a maximum of one
Bypass marker" and "Whenever a Besieged or Bypassed Stronghold becomes free of
Enemy Lords in the Locale, remove all Siege and Bypass markers there, then
return all Themata Service Markers." So Approach (4.3.4) correctly fires only on
an Unbypassed Locale — the blanket suppression in `_resolve_arrival` is right;
the bug was the never-cleared marker. **Fix:** `campaign._refresh_invest(locale)`
removes Siege/Bypass markers and returns Themata once a Locale has no Lords of
the besieging side; called after each March (on the vacated origin) and after
Feed/Pay/Disband. A marching Lord's `bypassed` flag is also cleared on
departure. Test `test_phase3b_march::test_bypass_marker_cleared_when_bypasser_
leaves_smoke005`. Smoke fuzz now clean (co-location invariant satisfied).

### SMOKE-006 — RESOLVED

Per 4.8.3, implemented the three missing Retreat-destination rules.
**Fix:** `battle._retreat_blocked(gs, dst, side)` now also rejects a destination
holding an enemy Stronghold that is not Ruins / Besieged / Bypassed (used by both
`_lord_fate` and the Sally besieger retreat). An approach breadcrumb is recorded
on the March (`h_cmd_march` -> `_resolve_arrival` stores `from` on the
`approach_response` pending -> `h_respond_approach` passes `approach_origin` to
`begin_battle` -> `resolve_battle` -> `_end_battle` -> `_lord_fate`). With it:
a losing Defender may not Retreat to the approach-origin Locale, and a Marching
Attacker (not a Relief-Sally Lord) must Retreat to the approach origin or be
Removed if that is not legal. The dead/incorrect `attacker_origin` variable was
replaced. Tests in `test_phase3b_battle.py`
(`test_retreat_blocked_by_unbesieged_enemy_stronghold_483`,
`test_marching_attacker_retreats_to_approach_origin_483`,
`test_defender_cannot_retreat_along_approach_way_483`).
