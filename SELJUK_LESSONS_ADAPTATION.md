# Seljuk Adaptation Notes for the Bug-Pattern Lesson Documents

`FUTURE_PROJECTS_LESSONS.md` and `CROSS_PROJECT_LESSONS.md` are kept in this
repo **verbatim**. They were authored while bug-hunting the *Nevsky* harness,
so their concrete examples (SMOKE numbers, function names, rule citations like
"4.8.3", subsystem names) are **Nevsky's**, not Seljuk's. They are included
because the *audit patterns* they catalog are game-agnostic and have high
expected yield on any Levy & Campaign-shaped rules engine.

This file is the bridge. It does three things:
1. Flags every Nevsky-specific reference in those documents so no one mistakes
   a Nevsky example for a Seljuk rule.
2. Maps each pattern to its Seljuk equivalent — the actual place in *this*
   codebase where the pattern will bite.
3. States plainly: **no Nevsky rules are imported into this project.** Where a
   lessons doc names a Nevsky mechanic, treat it as an illustration of the
   pattern only. Seljuk's own rules (per BRIEF.md's source priority) are the
   sole input to the harness.

---

## Nevsky-specific terms appearing in the lessons docs — and their status here

| Nevsky term in the docs | What it was in Nevsky | Seljuk status |
|---|---|---|
| **Veche** (Russian assembly; "Veche Option C") | A Russian Call-to-Arms mechanic | **Does not exist in Seljuk.** Seljuk's Call to Arms options are Marwanid Alliance, Empress Eudokia Makrembolitissa, Deep Raids, Loot, and Strategic Objective (3.5). |
| **Legate** ("Legate Use 2c", "legate_skip", auto-removal 1.4.1) | A Teutonic Call-to-Arms / piece mechanic | **Does not exist in Seljuk.** Nearest analogues for "side-specific Call-to-Arms grant" are the Seljuk/Roman CtA options above. |
| **Sail / Ship / Cogs / Lodya / Boat** | Naval movement and Ship budget | **Does not exist in Seljuk** (landlocked Anatolian theatre). Seljuk has no naval movement; Transport is **Carts only**, and the March-cost subsystem is Road vs **Pass** (Passes add cost; Holding-Box March costs a whole card). |
| **Parallel Ways** (dorpat<->odenpah trackway+waterway) | Two Way-types between one Locale pair | **Needs verification, not assumed.** Seljuk Ways are Road and Pass only. The Map Reference does not list any Locale pair joined by *both* a Road and a Pass, so Pattern 4 may be empty here — but this must be confirmed against the board, not assumed. (See the open Khliat<->Anzitene Way-type item in RULES_QUESTIONS.md.) |
| **Castle overlay / Stonemasons / Stone Kremlin / Walls+1** | Capability/Event overlays that change a Locale's effective Stronghold type | Seljuk's closest analogues are the **Imperial Fortress Construction** Capability (R1, places Fort markers on unfortified/Ruined Roman-Empire Locales) and **Ruins** markers (eliminate a Stronghold until rebuilt). Pattern 5 applies to *these*, not to Castles. |
| **Lord-flags** `moved_fought`, `in_stronghold`, `lordship_used`, `routed_units` | Per-Lord state flags | Seljuk has the **Moved/Fought** marker, Besieged/Bypassed/Withdrawn status, Lordship spend during Muster, the Routed section of a mat, plus Seljuk-only per-Lord state (Carts, Loot, Provender, Coin; Themata on the Roman Commander's mat; Strategic Objective markers on a Seljuk Lord's mat). Pattern 3 / Pattern 8 apply to all of these. |
| **VP cap 17.5; ½-VP per Ruins/Ravaged** | Nevsky VP math | Seljuk has its **own** VP math (½ VP per Ruins, ½ VP per Ravaged, 1 VP per Roman Conquered, Strategic Objective and Loot VPs in Holding Boxes, 5.1). There is **no 17.5 cap**; do not import one. Seljuk's Pattern-12 cap/floor cases are the **Asset 8-cap per type (1.7.3)**, the Feed thresholds (4.6.1), Siege markers capped at 4, Conquered markers = Stronghold Value, and the Seljuk Unity VP penalty floor. |
| **Off-Calendar drift** (boxes 1..16, off_left/off_right) | Nevsky's 16-box calendar | Seljuk's Calendar is **12 boxes** (Spring/Summer/Autumn x 1068-1071). The "set just off the board past box 1 / box 12, first shift back lands in box 1 / 12" rule (2.2.3) is real in Seljuk too, so Pattern 6 applies — but the bounds are **1 and 12**, not 1 and 16. |
| **FPD (Feed/Pay/Disband)** | End-of-card cycle | Seljuk has the same-named cycle (4.6), so the pattern transfers directly. |
| **AoW / Arts of War / capability_scope / This-Lord vs side-wide** | Card system | Seljuk has the **same card framework**: 50 Arts of War cards (R1-R25, S1-S25), each with an Event (top) and Capability (bottom); "This Lord" (max two per mat, no duplicates) vs "ALL"/"any"/"NOT" board-edge Capabilities (3.4.4). Pattern 14 applies directly. |

---

## Pattern-by-pattern applicability to Seljuk

The 14 patterns in `FUTURE_PROJECTS_LESSONS.md` and the 8 sections of
`CROSS_PROJECT_LESSONS.md` map to Seljuk as follows. "Hotspot" flags where this
game's structure makes the pattern especially likely.

1. **State-set-but-unreachable** — Applies. Hotspots: the Approach decision
   tree (Avoid/Withdraw/Battle), the Levy -> Call to Arms -> Campaign
   transitions, Bypass/Encamp/Depart/Sortie state, and the Winter interphase
   sub-steps.
2. **Mirror gaps** — Applies. Seljuk mirror pairs: Seljuk/Roman, Attacker/
   Defender, Battle/Storm/Sally, Conquer/Ruin, Pay-with-Coin/Pay-with-Loot,
   Levy-Themata (3.4.5)/Recruit-Themata (4.5.7), Winter Campaign (R9)/Winter
   March (S18). **Storm vs Battle Strike order differs** (Storm: all Defenders
   Melee before all Attackers; Battle: Horse before Foot) — a classic mirror
   trap.
3. **Stale per-Lord state flags** — Applies. Reset scopes: per-action,
   per-card, per-Levy, per-Campaign, per-Winter, per-lifecycle. Watch the
   Moved/Fought clear (4.6.3), Themata return on Commander Disband, and
   Lieutenant/Lower-Lord unstacking at Reset (4.7.5).
4. **Parallel Ways** — Likely **not applicable** (Seljuk Ways are Road/Pass and
   no Locale pair appears to carry both). Confirm against the board before
   concluding empty. The relevant Seljuk Way subtlety instead is the
   whole-Command-card March routes (the four Holding-Box Ways) and the Pass
   surcharge.
5. **Castle / overlay markers** — Applies, re-scoped: the overlays are
   **Fort markers (Imperial Fortress Construction)** and **Ruins** (which
   *remove* a Stronghold). Lookups that switch on a Locale's printed Stronghold
   type must honor these.
6. **Off-edge calendar** — Applies, bounds **1 and 12** (2.2.3), plus the
   Service-shift-left-on-Unfed/defeat and shift-right-on-Pay flows, and Lords
   placed beyond box 12 on Disband-at-limit going off-board.
7. **Card-text fidelity** — Applies, large surface: all 50 cards, with the
   Background Book / Errata clarifications integrated into the Arts of War
   reference. Read each card's text + clarification word-by-word against its
   resolver.
8. **Lifecycle leaks on Lord removal/disband** — Applies. Seljuk-specific
   cleanup: Themata on a disbanding Commander's mat (return to Thema box);
   Strategic Objective marker on a disbanding Seljuk Lord (Roman claims it);
   Special Vassal removal when its Capability is discarded; dual-allegiance
   Lords (Robert, Roussel, Arisighi) switching sides via Loyalty Check (1.4.2).
9. **Rule-cite-but-no-enforce** — Applies. Grep `# 4.x.y` citation comments and
   confirm the adjacent code enforces them.
10. **No-target no-op events** — Applies, **hotspot**. Many Seljuk Events have
    implied "if no valid target" branches that should no-op/discard, not raise:
    e.g. R13 Thrakion Reinforcements (no removed Themata), R16 Anglo-Saxon
    Exiles (no available Varangian Guard), R20 Armenian Resistance (no eligible
    Locale), S15 Thematic Troops Desert (Alp Arslan not in a Thema), S20 Alp
    Arslan Consolidates Power (no disbanded Seljuk Lords), and the asterisk
    "if already marked, discard and draw a new Event" cards (R1, R7, R10, R15,
    S5).
11. **Active-player / turn-order desync** — Applies. Seljuk-first alternation
    (2.2.4), Approach handing the baton to Inactive Lords, and the
    "Seljuk first then Roman" ordering inside Pay/Disband/Feed/Grow/Wastage/
    Reset are all desync risks.
12. **Cap/floor not enforced uniformly** — Applies, re-scoped (see the VP-cap
    row above): Asset 8-cap (1.7.3), Feed thresholds (4.6.1), max 4 Siege
    markers, Conquered = Value, two-"This Lord"-Capabilities limit, Storm
    6-Hit Melee cap, Seljuk Unity penalty.
13. **Per-window once-only flags not reset** — Applies. "Once per game"
    asterisk cards; "Events trigger at most one Call to Arms per Levy" (3.5);
    "only one Seljuk Ravage attempt per Locale per Command card" (4.5.5);
    Javelins / Steeled Resolve "any 1 Round (mark)"; Mules "first March across
    Pass per card."
14. **Capability scope (this-lord vs side-wide)** — Applies directly; same
    framework as Nevsky (3.4.4).

From `CROSS_PROJECT_LESSONS.md`:
- §1-2 **enumerator/handler divergence and the round-trip sweep** — the single
  highest-yield discipline; applies in full once Seljuk has a `legal_moves`
  enumerator and `_h_*` handlers.
- §3 **event resolvers must no-op gracefully** — see Pattern 10 hotspots above.
- §4 **different agent styles surface different bugs** / §8 **LLM full-game play
  is the highest-yield detector for a mature harness** — adopt for Phase 5.
- §5 **LLM-play interface design** — adopt for Phase 5.
- §6-7 **audit lenses and small idioms** (try/except around static-data loads in
  the enumerator, source-marker regression tests, seeded RNG in
  `state.meta.rng_state`, append-only SMOKE log) — adopt from the start.
- §8.2-8.3 **combat/siege predicates and "define each predicate once"** — Seljuk
  hotspots: "valid Approach target," "Friendly here for Withdraw," "who is
  Besieged vs Bypassed," "who may Sally / join a Relief Sally," "Laden,"
  "within the Roman Empire," "adjacent (incl. across a Pass)." Define each once;
  never re-derive inline.
- §8.4 **auto-resolved player choices are silent fidelity bugs** — Seljuk grants
  the owner the choice for Hit absorption, Concede, Retreat-vs-Withdraw,
  Themata-to-defend, Conquer-vs-Ruin, Reserve advance, Center fill, Flanker
  target. Surface each as a decision, defaulting to a sensible auto-choice only
  via the decision context.
