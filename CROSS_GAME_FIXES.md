# Cross-game audit repairs

The November 4, 2026 cross-game audit identified seven Seljuk defect groups.
The first repair batch addressed audit ID **R3**:

- **R3 — Rejected compound actions:** the public dispatcher restores the
  board, RNG and appended history when resolution raises an exception. A
  multi-Lord Approach response with an invalid later choice no longer leaves
  an earlier Lord moved or Assets transferred to the enemy.

Regression tests submit the original mixed valid/invalid Avoid response
through `LLMSession.apply`, verify retained board references, then compare a
corrected retry against a pristine position. A second test checks rollback
following dice use and partial history changes. Existing history entries are
not copied or traversed on each action.

## Combat repair batch — S1, S2, S3 and S6

- **S1 — Spoils allocation:** Battle and Sack rewards accept the winning
  owner's typed `spoils_recipient` and `spoils_amount` decisions, allowing
  arbitrary legal splits. The default fills eligible mats in order, spilling
  overflow to allies before losing markers at the per-type eight-Asset cap.
  Captured Lord Assets use the same allocator. Avoid-discard Spoils also spill
  to allies with remaining capacity.
- **S2 — Removal by Losses:** a losing Lord whose last Force dies in Losses
  transfers all Assets before removal, even if the earlier fate was Withdraw
  or a conceding Retreat. Surviving Withdrawers still retain their Assets.
- **S3 — Withdrawal capacity:** aftermath Withdrawal counts Lords already
  inside the Stronghold and those who have just Withdrawn, so successive
  defenders cannot exceed its Size.
- **S6 — Constructed Forts:** Approach and aftermath Withdrawal recognize
  R1 Imperial Fortress Construction markers and enforce their one-Lord limit.

Thirteen regression cases cover overflow, player allocation through the combat
resolver, Losses removal, existing occupants, and constructed Forts through
both Withdrawal paths. Against the previous main revision, twelve of these
cases fail and the surviving-Withdrawer preservation case passes. The 132-action Manzikert replay was compared against
the previous main revision: all board and RNG states, actions, score and winner
are identical. Its 100 changed state hashes reflect only new Spoils decision
and allocation history; exact state and save/load checks remain in place.

Validation: 1,104 tests passed; the round-trip move sweep was clean across five
scenarios and five seeds; 30 smoke games produced zero findings.

The two remaining Seljuk findings are **S4** (Shared Carts while Avoiding)
and **S5** (player-selected Wastage).
