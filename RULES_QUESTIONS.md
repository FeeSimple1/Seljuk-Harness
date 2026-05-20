# Open Rules Questions

Append questions here using the seven required fields (see `BRIEF.md` —
Question Format). When the user answers, MOVE the entry to
`RULES_DECISIONS.md` with the adjudication, citation, and commit hash.

Work the five-step consultation chain (BRIEF.md) BEFORE logging. Most apparent
ambiguities resolve on reading the references and Rules of Play; only genuinely
undetermined cases belong here.

---

## Q-001 — Way type of the Khliat <-> Anzitene connection (Road or Pass?)

**Context.** Encoding the Locale + Way map graph (Phase 1 static data). Each
Way must be typed Road or Pass because the type affects March cost (a Pass adds
one Command action), Supply (two Carts per Pass vs one per Road), and the
"adjacent to a Pass" trigger used by the Mountain Ambush Events (R2 / S2).

**Consultation log.**
- Step 1 (reference file — Map Reference): the connection is listed, but the
  Map Reference's own NOTES end with an explicit "Open item": *"The
  Khliat <-> Anzitene connection was added as a Pass based on context ... If the
  rulebook map shows it as a Road, move it to the Road Ways section."* It is
  grouped with the surrounding Pass entries, and the file's stated total of 15
  Pass Ways depends on counting it as a Pass — but the author flags low
  confidence.
- Steps 2-3 (Rules of Play, 1.3.1 "Ways" and the Key Terms entries for Road /
  Pass): the rulebook defines the two Way types and their effects but does NOT
  enumerate individual edges in text — the adjacency graph exists only on the
  printed game board (a graphic), which is not present as machine-readable text
  in any repo source.
- Step 4 (Background Book / Playbook): no edge-by-edge Way listing found.
- Step 5 (Errata & Clarifications, Jan 31 2026): not addressed.
- No external or historical sources were consulted.

**What is ambiguous.** Whether the Khliat <-> Anzitene Way is a Road or a Pass.
The text sources do not determine it; only the physical board does.

**Options.**
1. **Pass** — as the Map Reference currently lists it. Argument: it is grouped
   with the surrounding Pass entries (Mayyafariqin <-> Khliat and
   Khliat <-> Anzitene appear together) and the file's stated total of 15 Pass
   Ways depends on counting it as a Pass.
2. **Road** — Argument: the author explicitly flagged the classification as a
   guess from context and invited correction if the board shows a Road.

**Affects.** `src/seljuk/data/static/map.json` (or equivalent) and any
March-cost, Supply-cost, and "adjacent to a Pass" (R2 / S2 Mountain Ambush)
logic touching Khliat or Anzitene. Also the Pass/Road totals (15 / 47) reported
by any map-integrity test.

**Blocking?** No for Phase 0 (no map data is encoded yet). Yes for Phase 1 map
encoding — the edge cannot be typed faithfully without this answer. The user can
resolve it directly by reading the printed board.
