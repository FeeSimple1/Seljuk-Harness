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
