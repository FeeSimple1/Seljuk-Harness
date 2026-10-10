# Chat audit fixes — 2026-10-09

This change set addresses the 20 findings supplied in the chat audit of
`1cd25101b4a77bd51e794afe926a8cedd4dfb52a`. Rules references and existing
adjudications in this repository remain the authority; no house-rule changes
are introduced to replace them.

## Findings and regression coverage

The numbered test prefixes below refer to `tests/test_chat_audit_regressions.py`.

| # | Finding | Correction | Tests |
|---|---|---|---|
| 1 | Dispatcher rewinds combat/effect dice | Share one state-specific RNG stream throughout an action, including nested effects; keep validation-copy streams separate. | `test_01_*` |
| 2 | Final cleanup/Winter changes winner | Score and end a final campaign before Grow, Repair, Wastage, Reset, or Winter. | `test_02_*` (all five scenarios) |
| 3 | Mat Themata ignored | Include surviving units in strikes, routing, feeding, displays, and force counts; track marker-specific casualties and returns without changing printed symbols. | `test_03_*` |
| 4 | Mountain Ambush crashes Sally | Provide the map helper to the Sally resolver; exercise both R2 and S2 through the action dispatcher. | `test_04_*` |
| 5 | Hits stop at routed Lord | Continue remaining Battle/Storm hits against eligible surviving front Lords, without spilling into Reserve or unrelated array rows. | `test_05_*` |
| 6 | Filtered history reveals plans | Expose only action types from raw replay history in player views; omit RNG seed/state as well. Preserve the private replay in the real game state. | `test_06_*` |
| 7 | JSON decisions ignored | Accept typed JSON arrays and nested tuple-valued choices equivalently to Python tuples, including actual CLI execution. Preserve exact bare offered choices. | `test_07_*` |
| 8 | Javelins fires every round | Apply S11 infantry missiles in the owner's declared Battle round only, reset after Battle, and never apply in Storm. | `test_08_*` |
| 9 | Storm rounds half-hits twice | Add Garrison and Lord missile strike values before rounding once. | `test_09_*` |
| 10 | Sack deletes defender assets | Pool defeated Lords' assets as spoils along with printed stronghold rewards; allocate among survivors subject to asset limits. | `test_10_*` |
| 11 | No paid Themata retention | Add an explicit Roman Reset decision: pay one Coin per Thema, return it, or use R4 once for an unpaid Thema. Decisions survive save/load and block premature continuation. | `test_11_*` |
| 12 | Winter leaves abandoned siege | Recompute investment at the departure Locale; clear siege markers only when the last besieger leaves. | `test_12_*` |
| 13 | Opening special Vassals missing | Use shared Capability placement for opening deployment and normal muster, including special-Vassal initialization. | `test_13_*` |
| 14 | Duplicate opening Capabilities | Recalculate eligibility after each assignment and validate it again on direct submission. Return unplaceable drawn cards to the deck. | `test_14_*` |
| 15 | Gifts Exchanged uninitialized/illegal | Require adjacent opposing on-map Lords to muster S13 and initialize its four Coins and use counters. | `test_15_*` |
| 16 | Mandatory opening bypass | Reject unrelated direct actions while opening Capability/Event decisions remain; retain the Imperial Coffers decision gate. | `test_16_*` |
| 17 | Muster enemy Lord | Require the target's current allegiance to match the acting Lord before spending Lordship or rolling. | `test_17_*` |
| 18 | Affordable March missing | Consider discard-to-unladen March before rejecting the ordinary laden cost. | `test_18_*` |
| 19 | Group March splits stack | Validate complete co-located stacks and include each Lieutenant's Lower Lord; reject a Lower Lord moving alone and unlink stacks when a partner disbands. | `test_19_*` |
| 20 | Winter events wrong side order | Offer Seljuk S18 before Roman R9 when both are held. | `test_20_*` |

## Interface and implementation notes

- Atomic Battle/Sally actions accept `javelins_rounds: {lord_id: round}`. The
  default is round 1, analogous to the existing `steeled_rounds` declaration.
  This is an explicit owner choice, not an every-round effect.
- Reset offers `retain_themata` with `mode: "pay"`, `"return"`, or
  `"pressed_levy"`, and a `lord` and `thema`. One payment retains that Lord's
  markers from the chosen Thema together. The self-play drivers handle this
  newly interactive window rather than silently skipping it.
- Themata markers retain their printed `symbols`; optional `strength` and
  `routed` fields represent surviving units and routed units. Older saves with
  neither field load as full-strength, unrouted markers. Returning a surviving
  marker home restores its printed units; a marker whose units are all lost
  goes to the removed-marker pool.
- Combined Storm missile rounding uses deterministic Garrison-first assignment
  of the resulting integer hit budget, preserving special-target priority.
  This allocation convention is not a new quoted ruling about fractional-hit
  attribution; the fix is to round the combined strike values only once.
- The player-filtered view is deliberately not a full replay. Trusted save,
  debug, and raw-history access remain omniscient and must not be presented to
  an opponent as a public turn log. See `LLM_PLAY_GUIDE.md`.
- Existing tests that isolated a later Levy step by bypassing unresolved
  opening assignments now explicitly prepare that isolated fixture. Integration
  tests resolve actual opening decisions. No original test cases were removed.

## Validation

- Original suite: **773 tests**.
- Updated suite: **825 passing tests**, including **52 new regression cases**.
- Running those new cases against the original audited source produces
  **49 failures and 3 passes**; the passes are adjacent controls. Some cases
  intentionally also require new interfaces introduced by the fixes.
- Legal-move round-trip sweep: **five scenarios × five seeds**, clean.
- Aggressive smoke checks: **30 runs**, zero findings.
- Optional-rule soak: **70 runs**, zero failures (seven option profiles × five
  scenarios × two seeds).
- Longer play checks: **five games**, all reached a terminal result, with zero
  findings. Three ended at their scenario's final calendar box; two ended early
  when one side had no Lords. These are automated checks, not human playtests
  or a statistical balance study.

The permanent GitHub Actions workflow runs the full suite, the 25-case move
sweep, and the 30-run aggressive smoke checks. Tests are evidence for the
reported fixes and neighboring behavior, not proof that every possible game
position is defect-free.
