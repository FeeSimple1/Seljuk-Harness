# Cross-Harness Findings — Seljuk status

Tracks every bug/finding raised by sibling Levy & Campaign harnesses (Inferno
Vol. III, Nevsky Vol. II, Plantagenet Vol. IV) and their cross-harness advisories,
with Seljuk's status against each. Companion to `SMOKE_TEST_FINDINGS.md` (which
logs Seljuk's own findings in detail). "Absent" = audited and not present;
"Fixed" = was present, now fixed; commit/test cited for verification.

## Summary table

| # | Source | Bug class | Seljuk status | Evidence |
|---|--------|-----------|---------------|----------|
| 1 | Inferno Adv #1 | Door A: Retreat applies penalty but doesn't relocate the loser | **Absent** | `battle._lord_fate` / `_end_sally_besiegers_lose` set `cylinder`; Storm doesn't retreat attacker. Test `test_conceding_loser_relocates_no_colocation_4_8_3` (commit `0dc1b93`) |
| 2 | Inferno Adv #1 / #2 | Retreat destination rules incomplete (enemy Stronghold at dest; approach-Way; marching-attacker-to-origin) | **Fixed (SMOKE-006)** | `battle._retreat_blocked` + approach breadcrumb March→pending→battle. Tests in `test_phase3b_battle.py` (commit `ced8eef`) |
| 3 | Inferno Adv #2 | Door B: Siege/Bypass marker not cleared when Stronghold freed of enemies (stale → Approach/Besiege suppressed) | **Fixed (SMOKE-005)** | `campaign._refresh_invest` on March-out + Disband. Test `test_bypass_marker_cleared_when_bypasser_leaves_smoke005` (commit `ced8eef`) |
| 4 | Inferno Adv #2 | Door B (2nd harm): inside defender left `besieged` forever after besiegers depart | **Fixed (SMOKE-007)** | `_refresh_invest` clears `besieged`. Test `test_besieged_flag_cleared_when_besiegers_leave_smoke007` (commit `65629b4`) |
| 5 | Inferno Adv #2 / Nevsky | Door B empty/undefended-Stronghold case (besieger takes it, then leaves) | **Absent** | `_refresh_invest` keys on "no enemy Lords present"; verified clears markers with no defender (commit `65629b4`, findings log) |
| 6 | Inferno Adv #2 | Door C: placement (Muster/auto-Muster/summon) onto an enemy-occupied/Conquered Locale | **Absent** | All placement paths gated by `_seat_is_free`; Winter sends each Lord to its own Seat/Holding Box. Audited (commit `65629b4`, findings log) |
| 7 | Inferno Adv #2 / Nevsky | Missing co-location invariant (no always-on illegal-state guard) | **Fixed (SMOKE-004)** | `invariants.check_invariants` co-location check (besieged/bypassed/pending-combat excluded) (commit `0dc1b93`) |
| 8 | Nevsky Adv §3 | No VP / marker bound invariants | **Added** | VP≥0, per-Locale siege_markers∈0..4 (commit `2a07c2d`) |
| 9 | Nevsky Adv §5 | Cold paths (Concede / loser-survives) never exercised by first-legal auto-play | **Fixed** | smoke_fuzz injects random Concede into Battle/Storm/Sally (8 Battles/5 conceders/17 Storms per 45 games) (commit `6831a1b`) |
| 10 | Nevsky Adv §2 | No validated agent-facing palette (over-enum reaches the player) | **Added** | `engine.validated_legal_moves` (probe-and-drop, RNG-in-state safe); `legal-moves --validate`; `LLMSession.legal_actions(validated=True)` (commit `00d0dbc`) |
| 11 | Nevsky Adv §6 | Single decision-maker; rotate deciders | **Done** | greedy self-play + aggressive concede-fuzz + Claude Manzikert playthrough + ChatGPT emperor_and_the_lion run (0 anomalies) |
| 12 | Nevsky Adv §8 | Feed/starvation spiral (only-Tax/Supply forced to Feed) | **Absent** (starvation direction) | Tax/Forage/Supply/Recruit don't set `moved_fought` (`844f341`) |
| 12b | Nevsky Adv §8 (re-audit) | Feed scope wrong on OTHER set-sites | **Fixed (SMOKE-009)** | Re-auditing the asserted "Feed N/A" (Inferno's lesson) found Siege over-marked all Lords (4.5.1 marks only the besieger) and Ravage under-marked (4.5.5 marks both sides). Fixed `h_cmd_siege`/`h_cmd_ravage` (commit `9d5b50e`) |
| 17 | Nevsky Adv §1/§2 / Inferno SMOKE-095 | Under-enumeration: a working handler with no menu entry | **Fixed (SMOKE-008)** | Handler-coverage cross-check (over-enum sweep can't catch this): Levy menu didn't surface `deploy_capability`/`resolve_event` AoW pendings. Fixed `engine.legal_moves`; `play_hold_event`/R14 deferred (commit `5e4f212`) |
| 13 | Plantagenet ChatGPT run | Over-enum: `levy_capability` offered after `lordship_exhausted` | **Absent** | `enumerate_muster` filters actors by `_can_act_in_muster` (= the handler's gate, incl. `lordship_remaining<=0`). Test `test_enumerator_offers_no_levy_for_lordship_exhausted_lord_341` (commit `56fbcbc`) |
| 14 | Nevsky ChatGPT run | Over-enum: `cmd_march` offered to a Besieged Lord | **Absent** | `command_menu` gates March/Tax/Forage/Supply/Ravage behind `not lord.besieged`; besieged menu = {sally,pass,end}. Test `test_besieged_lord_menu_only_sally_pass_end_421` (commit `844f341`) |
| 15 | Nevsky ChatGPT run | Over-enum: `withdraw` offered into a non-Friendly Stronghold | **N/A (template)** | Seljuk's `respond_approach` is consumer-parameterised; Withdraw legality is handler-validated (`_validate_withdraw`) → clean IllegalAction, not a menu offer |
| 16 | Seljuk ChatGPT run | 0 anomalies; winner-on-low-VP looked contradictory | **Clarified** | Correct 5.2 sudden-death; added `notes["win_reason"]` so game-over self-explains (commit `844f341`) |

## Notes

- Items 1, 5, 6, 12, 13, 14 were **audited and found absent** — Seljuk already
  shared the relevant legality predicate between enumerator and handler, or
  handled the lifecycle correctly. Each carries a negative/guard test so a future
  refactor can't reintroduce the sibling's bug silently.
- Items 2, 3, 4, 7 were **real bugs in Seljuk**, found via the advisories'
  invariant/cold-path lenses and fixed (see `SMOKE_TEST_FINDINGS.md`).
- The dominant cross-harness class (enumerator/handler over-enumeration) is
  guarded three ways in Seljuk: the round-trip sweep (every enumerated move
  probed through `apply`, clean to 60 seeds), the runtime validated palette
  (`--validate`), and per-finding negative-enumerator tests.

## Corrections (audit pass following the Nevsky advisory)

Two rows above were originally recorded as "Absent"/"N/A" by assertion; holding
them to the advisory's "an asserted N/A deserves the same audit as a suspected
bug" standard, the proper audits proved both wrong and found real bugs:
- **Under-enumeration (item 17, SMOKE-008):** the over-enum round-trip sweep is
  silent on under-enum; a handler-coverage cross-check found the Levy AoW pendings
  unsurfaced.
- **Feed scope (item 12b, SMOKE-009):** checking only Forage/Tax/Supply missed
  that Siege/Ravage mark `moved_fought` wrongly.
The other asserted-N/As (parallel Ways, overlays, off-edge calendar, cap/floor
uniformity, capability data-scope, no-op unconditional side-effects) were
re-audited and **verified** N/A.
