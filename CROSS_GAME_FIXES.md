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

## Avoid and Wastage batch — S4 and S5

- **S4 — Shared Carts**. Co-Avoiders going to the same destination use their
  own Carts first and share the remaining capacity. Food stays on its original
  mat. Lords going elsewhere or Withdrawing remain outside that Cart pool.
  Local Scouts is applied before the Avoid groups are formed. Loot and excess
  Provender still become Spoils, and existing capacity limits apply.
- **S5 — Player-selected Wastage**. Normal Campaign completion and Events
  pause for explicit owner choices. Qualification still requires more than
  one of an Asset type or more than one This Lord Capability, but any held
  Asset or This Lord card may then be selected. Repeated Wastage rechecks
  qualification after each discard. R1 and S25 route choices to the affected
  faction. R22/S22 route the target choice to the raider's owner and the
  discard to the victim's owner. Reset and subsequent Events wait until the
  choices finish. Pending choices survive save/load and use the existing
  private, versioned menu.

Twenty-five new regression cases cover shared capacity and shortages,
separate destinations, Withdrawing allies, atomic rejection and retries,
singleton Asset/card choices, printed-side deck routing, private menus and
stale selections, R1/S25 ownership, repeated qualification, raider targets,
and final Game End preceding Wastage. Standalone helpers retain a deterministic
default for existing direct callers, while public play presents the choices.

The Manzikert replay preserves its 132 original moves and adds ten explicit
Wastage follow-ups. The Showdown replay adds 38 such choices to its 338
original actions. Exact state/save-load and private-interface replay tests
cover both games. Their final scores and winners match the preceding main.

Validation completed with 1,129 passing tests on Python 3.12. The move sweep
was clean across five scenarios and five seeds. Thirty smoke games reported
zero findings.

All seven original Seljuk findings are fixed.

## Second audit, batch 1 — SEL2-01 and SEL2-05

- **SEL2-01 — Final Thema at Reset:** returning the final Force now immediately
  Disbands the Commander under 1.6/3.3.2. Its cylinder goes to the current
  Calendar box plus printed Service, including off-right placement, and normal
  Disband cleanup returns cards, Assets and Vassals and detaches Lieutenants.
  Retaining the Thema with Coin or R4, or keeping any other Force, preserves
  the Commander. Final Game End still precedes Reset.
- **SEL2-05 — Special-Vassal Capability discard:** Wastage routes This Lord
  cards through a shared discard helper. Discarding R2, R7, R17 or S20 sets
  aside its Special Vassal and Service marker and returns its provided Forces
  as able, leaving Themata separate. An unlevied Vassal removes no units.
  Re-Levying the card creates one fresh Ready marker. Cards return to their
  printed-side deck, and a Lord losing his final Force receives the same
  recyclable Disband cleanup.

Both paths recheck the immediate no-Mustered-Lords Campaign victory before
continuing Wastage, Winter or the next Levy. Game End clears outstanding
Wastage follow-ups; the Calendar does not advance. Empty-Lord Disband during
Levy does not itself trigger Campaign victory.

Twenty-four regression cases cover all four cards, optional Vassal Service,
unlevied and depleted contingents, final-Force removal, mat and stack cleanup,
retention/return choices, save/load, retry after rejection, current-box timing,
off-right placement, immediate victory and final Game End. Against the prior
main, 20 cases fail and four preservation cases pass. The play guide and its
packaged reference are synchronized. The smoke driver now resolves Wastage
through actual legal owner choices instead of dropping pending records.

Validation: **1,153 tests passed**. The move round-trip sweep was clean across
five scenarios and five seeds; focused undefined-name/syntax lint and compile
checks passed. Thirty randomized smoke runs reported zero findings.

Second-audit progress: **2 of 6 Seljuk groups fixed**. SEL2-02 (excess Capability
choice), SEL2-03 (Grow choice), SEL2-04 (voluntary Reset discard) and SEL2-06
(mandatory Approach validation) remain open. All seven original findings
remain fixed.
