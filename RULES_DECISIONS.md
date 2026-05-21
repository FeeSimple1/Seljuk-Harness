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
