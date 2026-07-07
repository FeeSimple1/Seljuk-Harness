# Rules Decisions

Adjudicated rules calls. Each entry records the user's verbatim answer, the
rules citation (or [HOUSE RULE] if the rules are silent), and the commit hash
where the decision is encoded. **Decisions are permanent — never delete an
entry.** When the user answers a question in `RULES_QUESTIONS.md`, MOVE it here.

Format per entry:
- **D-NNN** (matches the originating Q-NNN where applicable)
- **Question** — the question as posed.
- **Decision** — the user's verbatim adjudication.
- **Citation** — rule section, or [HOUSE RULE].
- **Encoded in** — commit hash / file / test.

---

## D-001 (from Q-001) — Way type of the Khliat <-> Anzitene connection

- **Question.** Is the Khliat <-> Anzitene Way a Road or a Pass? The text
  sources do not determine it (the adjacency graph exists only on the printed
  board); the Map Reference listed it as a Pass but flagged that as a guess.
- **Decision.** "Khliat to Anzitene is a pass." (Eric, 2026-05-20, confirming
  from the physical game board.)
- **Citation.** Game board map topology (Rules of Play 1.3.1, Ways). The Map
  Reference's tentative classification is hereby confirmed correct.
- **Encoded in.** To be encoded in `src/seljuk/data/static/map.json` during
  Phase 1, with this decision cited; map-integrity test will assert 15 Pass
  Ways including Khliat <-> Anzitene.


## D-002 (from Q-002) — Turkic Horse have no base Melee; Shock Tactics grants it

- **Question.** Do Turkic Horse have any Melee without the Shock Tactics
  Capability (S4/S6)?
- **Decision (Eric, 2026-05-20).** "Turkic Horse have no base Melee; Shock
  Tactics is what grants them any Melee at all." Model: base Melee = 0; with
  Shock Tactics on the Lord, ceil(n/2) of his Turkic Horse strike at x1/2 in
  Melee (Battle and Storm).
- **Citation.** Playbook p.17 Battle Example of Play is decisive: Alp Arslan has
  Lamellar (not Shock Tactics) and unrouted Turkic Horse, yet in the Defending
  Horse Melee step only his Ghulam produce Hits ("no more Horse units that can
  Melee") — the Turkic Horse produce none. Card text S4 is granting language
  ("Half of this Lord's Turkic Horse HAVE Melee x1/2"); the S4 clarification and
  Playbook p.14 example (3 Turkic -> 2 units x1/2 = 1 Hit) confirm the arithmetic.
- **Encoded in.** battle.py (`_HORSE_MELEE` omits Turkic Horse; Shock Tactics
  adds ceil(n/2)x0.5 in `_lord_step_hits_caps` and `_lord_melee_capped`);
  forces.json turkic_horse Melee rewritten as
  {base:0, granted_by:SHOCK_TACTICS, value_when_granted:0.5, applies_to:ceil(n/2)}.
  Tests: test_phase4b_combat_caps.test_shock_tactics_grants_turkic_melee_s4_q002.


## D-002 (from Q-002) — Steeled Resolve (R3) Infantry armor value

- **Question.** Does R3 Steeled Resolve set the Lord's Infantry armor to 1-3 or
  1-4 vs Horse? The Arts of War Reference said "Armor 1-3" (card text +
  clarification), but the Units data + engine implement base Infantry 1-3 with
  Steeled Resolve -> 1-4; "1-3" would be a no-op.
- **Decision.** "Infantry base armor confirmed at 1-3. ... Steeled Resolve grants
  Armor 1-4 vs. Horse for the marked round." (Eric, 2026-06-09.) Rationale: a
  Capability granting the armor Infantry already have would be a dead card half;
  the pattern of Protection Capabilities is +1-style bumps (Klibanophoroi 1-3->1-4,
  Syndosis Unarmored->1-2); the rulebook's Protection worked example is exactly
  "a '+1' to Armor improves 1-3 to 1-4"; 1-4 is the elite-foot ceiling (Varangian).
- **Citation.** Player Aid Forces table (Infantry base Armor 1-3) + Rules of Play
  Protection section. The Arts of War Reference's "1-3" is a propagated
  transcription error (a single mistranscription echoed into the clarification);
  corrected in that file with a sourcing note. Derived correction, NOT published
  errata -- official Errata, if it ever addresses R3, takes precedence.
- **Encoded in.** Already implemented in `src/seljuk/capabilities.py`
  (`protection_range`: Steeled Resolve vs Horse -> (1,4)) and `battle.py`
  (vs-Horse scope = Missile+Melee in the owner-declared Round, Ruling 2, commit
  60450cf). Reference corrected in `reference/Seljuk Arts of War Reference.txt`.
  Tests: `tests/test_r3_steeled_resolve_and_s24.py`.


## D-006 (from Q-002, 2026-07-05) — Marwanid Alliance Seats (3.5.1.1) allow MUSTER

- **Question.** Do activated Amid/Mayyafariqin count as Seats for Muster
  (3.4.1), or only for Supply Routes / Bounty?
- **Decision.** "Unless we can make the case that muster is prohibited in this
  circumstance, allow it. It would have been easy for the sources to say it was
  not allowed if it weren't." (Eric, 2026-07-06.) Muster at an activated
  Marwanid Seat is ALLOWED for any Seljuk Lord while the activation lasts.
- **Citation.** 3.5.1.1 "a Seat for Seljuk Lords until the end of the next
  Winter Phase" with only the Tax and Supply-Source carve-outs; Lords Reference
  Seats lines ("Amid?, Mayyafariqin?" on every Seljuk Lord). Winter-Quarters
  return remains printed-Seats-only: the Playbook Winter example lists Alp
  Arslan's Quarters options exhaustively (Ani or the Mosul & Baghdad box)
  while Amid is active — a positive case that Quarters is excluded, which the
  no-prohibition principle above therefore does not override.
- **Encoded in.** `actions._muster_seats` (+ the levy_lord per-Seat palette);
  tests `test_decisions_d002m_d003.py::test_marwanid_seat_offered_and_used_for_muster_3511`
  / `..._not_offered_when_inactive_3511`.


## D-007 (from Q-003, 2026-07-05) — Loot / Empress cylinder shifts go EITHER direction

- **Question.** Does "shift a Lord cylinder 1 Calendar box" (3.5.2 Loot,
  3.5.1.2 Empress) permit shifting right (delaying Readiness)?
- **Decision.** "Allow shifting right. If it doesn't just say shift left, when
  it could, it must mean shift either direction." (Eric, 2026-07-06.)
- **Citation.** 3.5.2 / 3.5.1.2 ("shift", directionless). No-op shifts are not
  enumerated (left at box 0, right at the off-right position).
- **Encoded in.** `actions.enumerate_call_to_arms` (left/right variants for
  `cta_loot` and the Empress shift_cylinder effect; handlers already accepted
  `direction`); tests `test_decisions_d002m_d003.py::test_cta_loot_shifts_right_352`
  / `test_cta_empress_shifts_right_3512`.


## D-008 (from Q-004, 2026-07-05) — Sally resolves on the per-Lord Battle machinery

- **Question.** S3 Betrayal / S6 Command Confusion / R24 Cavalry Charge are
  Battle holds and a Sally is a Battle (4.9.2), but their per-Lord ordering
  effects had no exact home in the side-aggregate Sally resolver. Approximate,
  leave them Sally-ineligible, or rework the Sally engine?
- **Decision.** "Unfortunately, I think the invasive thing to do is the correct
  thing to do." (Eric, 2026-07-06.) Rework the Sally onto resolve_battle's
  per-Lord machinery so every Battle hold plays exactly.
- **Citation.** 4.5.3/4.9.2 ("Attack Besiegers in a Battle"; Battle rules with
  the 4.9.2 exceptions: Besiegers' Siegeworks as Walls vs Sallying strikes
  only, no Walls/Garrison for the Sallying side, Raid on a failed Sally,
  Siege ends if the Besiegers lose).
- **Encoded in.** Commit ce39ae6: `battle.resolve_sally` on `_strike_phase`
  (new `sally_walls`) + `_end_battle` (new `withdraw_inside`); full
  `_BATTLE_HOLDS` set in `h_cmd_sally`; tests `test_decisions_d008_sally.py`,
  `test_sally_concede.py` (rebaselined).


## D-009 (from Q-005, 2026-07-05) — Bounty Cart allowance is PER-LORD (errata text governs)

- **Question.** Errata Bounty: "1 VP per Loot ... up to the number of Carts he
  and co-located Lords currently possess" — per-Lord cap, or a shared
  per-Locale pool as the Playbook Winter example computes (2 returned, not 3)?
- **Decision.** "The errata should trump." (Eric, 2026-07-06.) Per-Lord cap:
  each qualifying Lord returns up to the GROUP's Carts. The Playbook example's
  shared-pool arithmetic is superseded by the errata sentence.
- **Citation.** Errata & Clarifications Jan-2026, 4.7.6 Bounty (authority rank
  1); Playbook is examples-only (rank 4).
- **Encoded in.** No code change — `campaign._bounty` already implements the
  per-Lord cap. This entry pins it as adjudicated, not accidental.
