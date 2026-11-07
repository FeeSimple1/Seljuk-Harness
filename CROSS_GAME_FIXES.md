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

## Second audit, batch 2 — SEL2-06

- **SEL2-06 — Mandatory Approach validation:** the public dispatcher now
  requires `respond_approach` while an `approach_response` is pending, during
  both Campaign and Winter. Pass, end activation, another March and other
  unrelated commands cannot leave an unresolved Battle behind or move its
  named attacker elsewhere. Rejection preserves the board, command cost,
  RNG, history and existing object references.

The defender's Avoid, Withdraw and Stand choices remain available. A resolved
Approach still proceeds to its normal Besiege/Bypass decision, Battle recovery
or further legal commands. Local Scouts and Battle Events remain inputs to
the response; the existing compact-interface private handoffs are preserved.
The play guide and packaged reference describe the mandatory timing.

Twenty-one new regressions exercise both factions and both seasonal activation
paths, real March-created Approaches, save/load, corrected retries, all three
defender responses, resumed movement and in-Battle Held Events. Against the
preceding main, 19 cases fail and two preservation cases pass. The focused
Approach, atomicity and compact-interface suites pass all 101 cases.

Validation: **1,174 tests passed**. The move round-trip sweep was clean across
five scenarios and five seeds; 30 randomized smoke runs reported zero
findings. Focused undefined-name/syntax lint and compile checks passed.

Second-audit progress: **3 of 6 Seljuk groups fixed**. SEL2-02 (excess Capability
choice), SEL2-03 (Grow choice) and SEL2-04 (voluntary Reset discard) remain
open. All seven original findings remain fixed.

## Second audit, batch 3 — SEL2-02

- **SEL2-02 — Excess Capability election:** entering Campaign now pauses for
  the Seljuk player and then the Roman player to choose their excess board-edge
  Capabilities. Every currently deployed card is available at each selection.
  Choose one card per action until the side reaches its Mustered-Lord limit;
  any legal retained subset is reachable. This Lord cards and Held Events
  neither count toward the quota nor qualify for this discard.

The public dispatcher blocks Planning and unrelated actions until both players
finish. Saved games retain a partially completed election. The compact
interface supplies the owner's complete paginated menu, remaining quota and
help, with existing versioned IDs and private-player handoffs. Both self-play
drivers resolve the choices through actual legal actions. Discarding Gifts
Exchanged removes its Capability coin pool while preserving the separate
This Campaign Peace Offering Event effect. Standalone legacy helpers retain
their documented deterministic default; public play never chooses a card.

Immediate Campaign victory is checked before creating a discard election.
The Manzikert replay's first 131 checkpoints are exactly unchanged, including
board, RNG and history. At the final checkpoint only R16 and R25 remain at
the Roman board edge instead of being discarded after the Romans have already
lost for having no Mustered Lords. That one expected hash is updated; all 132
original moves, ten Wastage follow-ups, winner and score remain unchanged.

Twenty-seven new regressions cover either Roman card being retained, every
two-of-four retained subset, Seljuk-first handoff, all offered moves validating,
exclusion of This Lord/Held cards, malformed inputs, atomic retry, save/load,
paginated stable selections, stale-ID rejection, private ownership, quota
completion, Gifts Exchanged and immediate victory. Against preceding main,
25 cases fail and two no-excess preservation cases pass.

Validation: **1,201 tests passed**, including the complete Manzikert and Showdown
interface replays. The move round-trip sweep was clean across five scenarios
and five seeds; 30 randomized smoke runs reported zero findings. Focused
undefined-name/syntax lint, new-test lint and compile checks passed.

Second-audit progress: **4 of 6 Seljuk groups fixed**. SEL2-03 (Grow selection)
and SEL2-04 (voluntary Reset discard) remain open. All seven original findings
remain fixed.

## Second audit, batch 4 — SEL2-03

- **SEL2-03 — Grow selection:** public Spring completion now pauses for
  Seljuk then Roman to select which enemy Ravaged markers to remove. Every
  eligible Locale remains reachable. Each selection removes one marker and
  updates VPs; the original removal quota stays fixed until met, leaving half
  the original total rounded up. Zero/one-marker cases require no election.

Repair, Wastage and Reset wait for both owners to finish. Game End precedes
Grow, and non-Spring completion creates no Grow decision. Invalid markers,
wrong owners, repeated removals and attempts to skip the decision reject
without state, RNG or history changes. Pending quotas survive save/load;
the compact interface keeps complete paginated choices, stable IDs, explicit
owner routing and stale-selection rejection. Both self-play drivers and the
Campaign integration tests resolve the new selections through real actions.
Standalone helpers retain the documented deterministic default.

Forty-one new regressions cover all four Springs, both marker owners, counts
zero through six, every two-of-four retained subset, fixed quotas, Seljuk-first
handoff, malformed and bypass actions, retry, score changes, ordering against
Repair/Wastage/Reset, Game End, save/load and private compact-interface use.
Against preceding main, 34 fail and seven preservation cases pass. The focused
Grow, integration and Manzikert suites pass all 83 cases.

The Manzikert and Showdown replay fixtures each add three explicit selections
matching the preceding automatic map-order removals. At all 132 Manzikert and
376 original Showdown checkpoints, every state field except history and cached
VPs is identical to preceding main, including RNG. Grow now refreshes VPs
immediately while later choices remain pending (one Manzikert checkpoint and
13 Showdown checkpoints). Exact Manzikert hashes are updated from index 45
onward for the added history/VP refresh; serialized continuation remains
checked. The interface replays execute 145 and 379 actions respectively.
All original decisions, final scores and winners are preserved.

Validation: **1,242 tests passed**, including both complete interface replays.
The move round-trip sweep was clean across five scenarios and five seeds;
30 randomized smoke runs reported zero findings. Focused undefined-name/syntax
lint, new-test lint and compile checks passed.

Second-audit progress: **5 of 6 Seljuk groups fixed**. Only SEL2-04 (voluntary
Reset discard) remains open. All seven original findings remain fixed.

## Second audit, batch 5 — SEL2-04

- **SEL2-04 — Voluntary Reset discards:** after Themata retention and mandatory
  Reset cleanup, Seljuk then Roman can return any owned Held Event, board-edge
  Capability or This Lord Capability. Each candidate is explicitly offered;
  discard cards individually or choose `reset_done` to keep the rest. Any
  subset remains reachable, with no mandatory voluntary discard. Owners with
  no candidates need no action.

Cards return to their printed-side decks. Special-Vassal cards use the shared
contingent cleanup and can cause recyclable Lord Disband; losing the final
Mustered Lord ends Campaign immediately before another player's election or
Winter. R4 retention is already complete and is never repeated when its card
is subsequently discarded. This Campaign cards and Gifts Exchanged expire
once before the voluntary window. Winter Holds may be kept or discarded
before their activation window. Game End still precedes all Reset actions.

The dispatcher blocks unrelated actions during the election. Menus, private
owner handoffs, paginated stable IDs, stale-selection rejection, save/load and
result details include the new actions. Self-play preserves cards explicitly;
the randomized smoke driver explores both discarding and keeping. Older
Campaign/Winter tests now explicitly keep cards before testing later steps.

Thirty-four new regressions cover all eight subsets across the three card
areas, both owners, mandatory cleanup, all four Special Vassals with optional
Service, final-Force Disband/victory, R4 retention, Winter Holds, malformed and
foreign choices, bypass prevention, atomic retry, printed-side deck routing,
private menus, save/load and Game End. Against preceding main, 31 cases fail
and three preservation cases pass. The focused suite passed 142 cases.

The recorded Manzikert game adds four keep-all choices and Showdown adds ten.
At all 132 and 379 preceding checkpoints respectively, every non-history state
field is identical, including cards, board, RNG, cached VPs and winner. The
Manzikert hashes from index 46 onward change only for the additional history.
The full interface replays now execute 149 and 389 actions, preserving every
original decision and both final scores and winners.

Validation: **1,276 tests passed**. The move round-trip sweep was clean across
five scenarios and five seeds; 30 randomized smoke runs reported zero findings.
Focused undefined-name/syntax lint, new-test lint and compile checks passed.

Second-audit progress: **6 of 6 Seljuk groups fixed**. All seven original
findings remain fixed. Across the five harnesses, all **24 of 24** confirmed
second-audit groups are now fixed.

## Third audit, batch 1 — SEL3-01

Battle and Sally now offer Concede at the start of every round, attacker
first. The first concession resolves that round's Strikes with Pursuit and
determines the losing side even if the opponent Routs. Reposition begins
after the first round. Storm offers its own attacker-only Concede from
Round 2 under 4.9.1.

Manzikert's recorded shared script adds two Round 1 declines to preserve
the intended later concession. All 149 checkpoints match the preceding
non-history state, including RNG, score, and winner. Checkpoint hashes
reflect the new decision traces. The packaged guide explains the queue order.

Three new public-action regressions fail on preceding main and pass here.
The full run passed 1,278 tests, including both recorded interface games.
The sole failure was the stale packaged guide checksum. Regenerating the
package passed that check and the 38-case focused rerun. The move
round-trip sweep was clean across five scenarios and five seeds.

Third-audit progress is **one of five Seljuk groups** and **19 of 23 overall**.

## Third audit, batch 2 — SEL3-02

Conceding Lords who survive Losses and Retreat to the same Locale Share spare
Carts under 1.5.2, 4.3.2, and 4.8.3. The calculation uses each Lord's own Carts
first, then shares spare capacity in group order, as in Avoid Battle. Retained
Provender stays on its original mat. Only excess Provender and all Loot become
Spoils for these Lords. Lords who Withdraw, are removed, or Retreat to a
different Locale do not contribute to the group's Carts.

Six public Approach cases cover both directions of sharing, partial capacity,
own Carts, separate destinations, and Withdrawal. A seventh case covers a Lord
removed by Losses. The three shared-capacity cases failed on preceding main,
and all 75 focused tests passed after the fix.

Validation: **1,286 tests passed**, including the Manzikert and Showdown
interface replays. The move round-trip sweep was clean across five scenarios
and five seeds, and 30 randomized games reported no findings.

Third-audit progress is **two of five Seljuk groups** and **20 of 23 overall**.

## Third audit, batch 3 — SEL3-03

Relief Sally (4.8.1) takes the approaching player's `sally_join` selection
on `respond_approach`. Choose any subset of eligible Besieged Lords at the
Battle Locale, including an empty list. Only participants enter the Sallying
row, fight, and trigger the siege reduction after an attacking loss. Omission
retains the historical all-join behavior for existing actions and replays.

The compact interface presents the choice in the approaching player's input
window. After playing Local Scouts, the approaching player can wait for the
defender's response before choosing. Invalid selections reject atomically.
The choice survives save/load and appears in the public Battle result.

The public-action regressions cover every subset of two Lords, participation,
Feeding, siege aftermath, ownership, invalid choices, and Local Scouts timing.
The three cases exercising a strict subset failed on preceding main. The
all-join case also detected the missing menu hint. The focused suite passed 104
tests. The full suite passed **1,301 tests**, including the recorded Manzikert
and Showdown games. The round-trip sweep passed across five scenarios and
five seeds, and 30 randomized games reported no findings.

Third-audit progress is **three of five Seljuk groups** and **21 of 23 overall**.

## Third audit, batch 4 — SEL3-04

The approaching player can distribute the Loot and excess Provender left
by Avoiding Lords (4.3.4, 4.8.3). The shared Spoils allocator applies the
eight-marker cap to each Asset on each eligible approaching Lord's mat.
The response reports the pool, transfers, and any amount lost to the cap.

Use `avoid_spoils_decisions` for a separate allocation script. A response
without Battle also accepts the existing `battle_decisions` script for this
purpose. Omission fills eligible mats in their existing order. If Battle
follows, its own script and Spoils pool are resolved separately.

The compact input window shows the final pool and eligible capacity to its
owner. When Local Scouts could change who Avoids, the final pool is shown
after the card decision and any defender response. Tests cover owner routing,
save/load, mixed Avoid and Stand, cap overflow, and Hidden Mats timing.

Validation: **1,308 tests passed**, including the Manzikert and Showdown
replays. The move round-trip sweep passed across five scenarios and five seeds.

Third-audit progress is **four of five Seljuk groups** and **22 of 23 overall**.

## Third audit, batch 5 — IF3-02

Vassal Service (6.2) exposes the identity and Service box of each levied
Vassal whose marker is on or beside the Calendar. Filtered state and compact
Lord inspection show those markers under `public_vassal_service`. The
briefing, focused Lord view, and Calendar render the same public information.
Hidden Mats masks enemy mat data, including Vassals without a
Calendar marker, current Forces, Assets, and This Lord Capabilities.

The regression starts Emperor and the Lion with both optional rules enabled,
uses legal actions to Muster Alp Arslan's first Vassal, and checks both
players' views, compact inspection, and the CLI after save/load. Additional
checks cover shifted and off-edge markers, Special Vassals, and option gating.

Validation: **1,315 tests passed**, including the Manzikert and Showdown
replays. The move round-trip sweep passed across five scenarios and five seeds.
Thirty randomized games reported no findings.

Third-audit progress is **five of five Seljuk groups** and **23 of 23 overall**.

## Round 4 Seljuk audit

- R1 Forts use the active Fort profile for Siege, Themata assignments, and
  Storm spoils. Conquest or Ruin clears the constructed Fort marker.
- Roman Lords cannot Withdraw at Hama or Aleppo during Approach or after
  Battle. A Seljuk Lord can Withdraw into friendly Aleppo under the normal
  requirements. Local Scouts retains its specific Aleppo exception.
- Owners can assign Shared Cart capacity across co-Avoiding Lords or surviving
  co-Retreaters who conceded and move to the same destination. Food remains on
  its owner's mat and unallocated food becomes Spoils.
- Losing owners can elect removal alongside their legal Retreat or Withdrawal
  options. Mandatory Sally Withdrawal still applies.
- Hidden Mats reveals the participating Lord mats after combat is committed,
  before each player finalizes their inputs. The compact interface preserves
  this window across save and resume.
