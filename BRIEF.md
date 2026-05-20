Seljuk Harness — Project Specification

Goal

A Python harness for *Seljuk* (GMT Games, 2025), Volume V of the Levy &
Campaign Series, covering the 11th-century campaigns in Anatolia between the
Roman Empire and the Seljuk Sultanate that culminated in the Battle of
Manzikert (1071). The harness holds full game state, validates and executes
all rules-defined actions, runs Battle and Storm engagements automatically,
rolls all dice, and exposes a structured interface designed to be consumed by
an LLM (Claude or ChatGPT) playing one or both sides.

The user supplies strategic judgment via the LLM. The user adjudicates rules
ambiguities surfaced during development. The harness supplies everything else:
state, rules enforcement, mechanical resolution.

This is a private project. Code quality should be good enough for the user to
maintain, not for external readers.

This harness is for Seljuk ONLY. The Nevsky-Harness was used as a structural
model for *how to shape the project* (architecture, document discipline, audit
methodology). No Nevsky rules, data, scenarios, cards, or game logic are
carried into this project. See "Relationship to Nevsky-Harness" below.

Authoritative Sources (Priority Order)

1. Seljuk Errata and Clarifications (Jan 31, 2026) — overrides any conflict in
   other sources. Present in the repo in two forms that are CONTENT-IDENTICAL:
   `reference/Seljuk Errata and Clarifications.txt` and
   `source/Seljuk+Errata+and+Clarifications+-+March+2026.pdf`. (The PDF's
   filename says "March 2026" but its content is dated "Jan 31, 2026"; the two
   were diffed and carry the same nine items. The `.txt` is the cleaner version
   because it disambiguates two strikethrough corrections that the plain PDF
   extraction shows with the to-be-deleted text still inline.)
2. The curated reference `.txt` files in `reference/` (Sequence of Play, Map,
   Units and Strongholds, Lords, Themata and Scenario, Battle and Storm, Arts
   of War, Errata and Clarifications). These are designer-clarified
   distillations with errata applied inline and are the FIRST stop for any
   question about card text, capability mechanics, Lord stats, map topology, or
   rule interpretation. Several of them integrate clarifications from the
   Background Book (Playbook) and the published scenario pages.
3. `source/Seljuk_Rules.pdf` — Rules of Play & Scenarios (© 2025 GMT Games).
   Used to confirm what's in the `.txt` references and to fill anything missing
   from them. Sections 4.3-4.5 (the detailed Command rules) and section 7 (the
   five scenario setups) live primarily here; the Sequence of Play reference
   summarizes but does not fully reproduce them.
4. `source/Seljuk_Background_Book_web.pdf` — the Playbook: examples of play,
   strategy notes, card lists and implementation tips, plus historical
   reference. This is the analogue of Nevsky's Playbook. It is NOT a rules
   source; it is useful only for clarifying examples and the card-implementation
   tips that the Arts of War reference has already integrated.

PDFs in the repo's `source/` directory ARE readable; treat them as ordinary
inputs. When sources conflict, higher priority wins. For Q-NNN consultation,
the FIRST step is always the relevant `.txt` reference file's section. Skipping
that step is a process bug. The `.txt` references are not optional starting
material — they are the canonical answers.

Scope of Inquiry — Hard Constraint

This is a software project to encode a board game's rules. It is NOT a
historical research project. The game's setting in 11th-century Anatolia,
Armenia, and Syria is theme, not subject matter.

Sources you may consult:
- The repo's reference `.txt` files.
- The repo's PDFs (Rules of Play & Scenarios, Background Book/Playbook, Errata).
- Standard Python documentation, language references, and library docs needed
  to write the code.
- Files in the repo that the user has placed there.

Sources you may NOT consult without explicit user instruction:
- Wikipedia, encyclopedias, or any general-knowledge reference on the
  historical period, persons, places, battles, or events.
- Academic or popular history sources — even when the rulebook references them.
- Other GMT board games or board-game databases (BoardGameGeek, Consimworld)
  for comparative rules interpretation. This explicitly INCLUDES Nevsky and the
  other Levy & Campaign volumes (Almoravid, Inferno, Plantagenet, Pendragon).
  Do not reason "Nevsky did X, so Seljuk does X." Seljuk's own rules are the
  only input.
- Your own pre-existing knowledge of Seljuk, Nevsky, the Levy & Campaign
  system, or their themes when that knowledge comes from outside the repo
  files. If you find yourself "remembering" something, treat that memory as if
  it doesn't exist; consult the repo files instead.
- Web searches of any kind related to the game's subject matter.

Why this matters

Proper names and identifiers (Romanos Diogenes, Alp Arslan, Manzikert, Themata,
Tagmata, Ghulam, Varangian Guard) are tokens used by the rules to identify
specific game pieces with specific game stats. Their historical referents are
irrelevant to the harness. Encoding any historical "fact" as game logic is a
bug, not a feature. The Rules of Play even flags this directly: "Italicized
Calendar notes provide historical background; they do not affect play," and the
Design Notes are rationale, not rules.

Names and identifiers

Use proper names from the game (Lords, Vassals, Locales, Capabilities,
Strongholds, Themata) exactly as the rules use them, for state tracking, code
identifiers, file names, comments, and user-facing displays. Use the rulebook
spelling where the user's input differs (the Map Reference already lists the
corrections applied, e.g. "Charsianon" not "Charisianon"). Do not annotate them
with historical context or transliterate alternates.

Rules Accuracy Trumps Simplification — HARD CONSTRAINT

Where the rules are clear, the harness MUST implement them faithfully.
Simplifications, approximations, "Phase N+ deferrals," and convenience
shortcuts are NOT acceptable when the rules are explicit about a behavior.

The only acceptable reasons to depart from the rules are:
  1. The rules are ambiguous (-> follow the Ambiguity Policy / Q-NNN
     consultation chain below).
  2. The user has explicitly adjudicated a deviation (recorded in
     RULES_DECISIONS.md as [HOUSE RULE]).

Reasons that are NOT acceptable:
  - "Easier to implement this way."
  - "Phase N is just a stub; Phase N+1 will fix it."
  - "Most games won't hit this case."
  - "The simplification is conservative / lenient."
  - "Nevsky / another L&C volume handled it this way."

When implementing a feature, if the chosen approach diverges from the rules in
any measurable way, the divergence MUST be either fixed in the same PR before
merge, or logged as a Q-NNN in RULES_QUESTIONS.md and surfaced to the user
before merge. Code comments that say "simplified," "approximated," "deferred,"
or similar are flags for audit; each must trace to a Q-NNN, a [HOUSE RULE]
decision, or a future-phase commitment with an explicit issue tracking it.

Completion Is Essential — HARD CONSTRAINT

Every rule and aspect of the game covered in the source and reference documents
must eventually be completely covered. The phased plan below sequences the work;
it does not license dropping anything. "Out of scope" (bottom of this file)
lists the only things deliberately excluded. If a rule appears in the sources
and is not in scope, it is in scope. By the end of the phase plan the harness
must implement: all five scenarios; the full Levy sequence including Loyalty
Checks, all Call to Arms options, and Themata; every Command (March, Supply,
Siege, Storm, Sally, Forage, Ravage, Tax, Recruit, Pass) with Bypass / Encamp /
Depart / Sortie; full Battle, Storm, and Sally resolution; all 50 Arts of War
cards (R1-R25, S1-S25), both Event and Capability halves; the End Campaign and
Winter sequences (Grow, Repair, Wastage, Reset, Bounty, Seljuk Unity, Winter
Quarters, Aleppo Diplomacy, the Aleppo auto-victory); and the four optional
rules (6.1-6.4) behind flags.

Ambiguity Policy

The harness encodes rules deterministically. Every rule encoded in code must
trace to a source. The user is the sole authority on rules interpretation when
sources are silent or unclear.

Consultation Chain — REQUIRED before logging any question. Work through this
chain in order and document each step:

1. Curated reference file. Identify the most relevant `.txt` file (Battle and
   Storm for combat, Sequence of Play for phase flow, Arts of War for card text
   and capability mechanics, Map for topology, Lords for stats, Units and
   Strongholds for Forces/Garrison/Walls, Themata and Scenario for setup) and
   read the relevant section IN FULL. If the answer is there, the consultation
   ends and the question is not logged.
2. Rules of Play, primary section. Find the rule section number cited in the
   reference and read the full section in `source/Seljuk_Rules.pdf`, plus
   sub-sections.
3. Rules of Play, related sections. Use the Key Terms index (page 36) to locate
   cross-referenced sections and read those too.
4. Background Book / Playbook examples. Search for worked examples and the card
   implementation tips. Examples are not rules but often resolve apparent
   ambiguity.
5. Errata and Clarifications. Check whether the case is addressed by an erratum
   or clarification (Jan 31, 2026).

Only after all five steps are performed and documented should a question be
logged. If the consultation resolves the question, encode the answer with a
citation comment in the code and proceed.

Question Format — REQUIRED fields (append to RULES_QUESTIONS.md):
Question ID (Q-NNN, sequential); Context; Consultation log (what was checked at
each of the five steps, with section numbers and quoted text, and an explicit
confirmation that no external/historical sources were consulted); What is
ambiguous; Options (>= 2 concrete possibilities, each with a rules argument);
Affects (files, functions, tests, scenarios); Blocking?. Do not log a question
without all seven fields.

Decision Log

When the user answers a question, MOVE the entry from RULES_QUESTIONS.md to
RULES_DECISIONS.md, appending the user's adjudication, any rules citation, and
the commit hash where the answer is encoded. Decisions are permanent — never
delete an entry from RULES_DECISIONS.md. If the user marks a decision
[HOUSE RULE] (rules silent), treat it as authoritative and cite it like any
other rule.

No Agent in the Harness — Hard Constraint

The harness encodes the rules and exposes state. It MUST NOT make strategic
decisions on the consumer's behalf. The LLM (or human) consumer applies all
strategic judgment. The harness's job is to maintain authoritative game state;
enforce rules (actions either succeed and mutate state or raise IllegalAction
with a code); surface state in forms the consumer can read efficiently;
enumerate legal moves with their mechanical effects; and compute
previews/forecasts on request.

The harness MUST NOT recommend specific actions, editorialise about strategic
trade-offs, pick decisions for the consumer (Concede, Avoid Battle, Withdraw,
Plan ordering, Capability picks, hit absorption, Themata-to-defend selection,
Reserve advance, etc.), or run an internal agent that selects actions when the
consumer hasn't. If a comment, docstring, note field, or helper output in
`src/seljuk/` contains language like "Use when...", "should," "recommend," or
"prefer," that's a bug; replace it with a description of the rule's mechanical
effect and let the consumer decide.

Test fixtures that drive the engine with heuristic policies (under
`tests/_playthrough_*.py`) and any agents under `scripts/` ARE agents
necessarily, to stress-test the engine, but they are NOT part of the shipped
harness. They live outside `src/seljuk/` and are excluded from the package. A
future STRATEGY_DIGEST.md (advisory, consumer-facing, never parsed by the
harness) is the only place strategy advice belongs.

Architecture Requirements

- Language: Python 3.11+.
- State representation: a single JSON file holds complete game state. State
  files are portable across sessions; loading a state file fully reconstructs
  the game.
- Determinism: given a state file and an action, the resulting state is
  deterministic except for dice. Dice use a seedable RNG; the seed is stored in
  the state file. (All Seljuk rolls are standard d6.)
- Two interfaces: a library API (functions/classes) for programmatic use, and a
  CLI that wraps the library, suitable for an LLM to call via shell or for the
  user to run directly.
- No graphical interface.

LLM-Consumer Interface — Required Capabilities (target by end of Phase 5)

- `new` — initialize a state file from a scenario. All five scenarios
  supported: The Emperor and the Lion (1068, 12 turns); Specter of Norman
  Betrayal (1069, 3 turns); Year of Treacherous Ambition (1070 Learning, 3
  turns); Showdown in Anatolia (1070, 6 turns); Manzikert (1071, 3 turns).
- `state` — render current state: Summary mode (compact, ~500 tokens), Verbose
  mode (full), Focused views (a single Lord's mat, a Locale, the Calendar, a
  Thema box, deck composition, the Mosul & Baghdad and Constantinople Holding
  Boxes / VP tracks).
- `legal-moves` — enumerate all legal actions for a given player in the current
  phase, each with action grammar, costs, prerequisites met, and a brief
  description with rule citation. Primary interface for an LLM to decide.
- `do` — execute a submitted action; validate, mutate, and return a structured
  result describing what happened (dice rolled, hits, markers, VP changes).
  Errors include rule citations.
- `pending` — when an action triggers a sub-decision (Approach: each Inactive
  Lord chooses Avoid/Withdraw/Stand; Battle hit absorption; Loyalty Check coin
  spend; Themata-to-defend at Siege start), record it in the state file and
  report which player owes a response.
- `history` — last N actions and results.
- `save` / `load` — explicit persistence in addition to the automatic state
  file.

Action Grammar

Actions are submitted as JSON. The grammar is part of the specification and
must be documented in ACTIONS.md as it is developed. Every action type has a
schema; the harness rejects malformed actions with a clear error.

Dice and Mechanical Resolution

The harness rolls all dice (Fealty, Loyalty Check, Surrender, Forage,
Protection, Losses, Service shift, Aleppo Diplomacy, Support from Aleppo, etc.).
The LLM never rolls. Every roll is logged in the action result with context
(whose roll, against what target, what happened). This is non-negotiable: it
removes a class of errors and makes the game auditable.

Two-Sided Play

The harness supports: LLM plays one side, user plays the other; LLM plays both
sides (alternating activations, Seljuk first per 2.2.4); pure observer mode. It
does not need to know which player is the LLM; it exposes legal moves and
validates submissions per the active player.

Phasing

Each phase is a separate PR. Do not start the next phase until the previous PR
is merged by the user. Branch naming: `phase-N-short-description`.

- Phase 0 (THIS PR): Project skeleton, JSON schema for state, reference and
  source material in place, module stubs, basic CLI structure, test framework,
  the two bug-pattern lesson docs plus the Seljuk adaptation note, and the
  project-discipline documents (this BRIEF, README, RULES_DECISIONS,
  RULES_QUESTIONS, SMOKE_TEST_FINDINGS). No game logic yet.
- Phase 1: State model (Pydantic); static-data encoding from the references
  (Lords and ratings, Forces and Strikes/Protection, Strongholds and
  Garrison/Walls, the Locale + Way map graph, Themata rosters, the 50 Arts of
  War cards as data, Command decks); scenario loader for all five scenarios;
  state display (summary/verbose/focused); `state` command and victory math.
- Phase 2: Levy phase — Arts of War (shuffle, first-Levy Capability draw, later
  Event draw with Hold / This Campaign / asterisk handling); Pay (Coin and
  Loot, Commander long-range Coin); Disband (Beyond Service, At Limit, Themata
  return on Commander disband); Muster (Lords with Fealty rolls and Seats /
  Holding Boxes, Vassals incl. Special Vassals, Transport, Capabilities incl.
  the two-"This Lord" limit, Themata); Call to Arms (Marwanid Alliance, Empress
  Eudokia, Deep Raids, Loot, Strategic Objective); Loyalty Checks (Treachery
  cards and Imperial Coffers, coin modifiers, side-switching per 1.4.2).
  legal-moves for Levy.
- Phase 3a: Plan (season card counts, Lieutenants) and the simple Commands —
  Tax, Forage, Ravage (incl. Seljuk one- vs two-action and Themata defence),
  Supply (Sources, Routes, Carts, Pass cost), Recruit (Roman Commander),
  Pass; Bypass / Encamp / Depart / Sortie; the Feed-Pay-Disband cycle; End
  Campaign (Capability Discard, Grow, Repair, Wastage, Reset); Winter (Aleppo
  auto-victory check, Bounty, Seljuk Unity, Winter Quarters, Aleppo Diplomacy).
  legal-moves for these.
- Phase 3b: March with the Approach decision tree (Avoid Battle, Withdraw,
  Battle), Group March and Lieutenants, Laden rules and Turkic-Horse / Pass /
  Holding-Box March costs; full Battle resolution (Array with up to three Front
  positions and Reserve, Rounds, Concede + Pursuit, Reposition incl. Center
  fill, Strike initiative Missile-then-Melee with Horse before Foot, Flanking,
  Hits/Protection/Rout, Retreat/Withdraw/Removal, Losses, Spoils, Service
  shift, Aftermath).
- Phase 3c: Siege and Surrender (dice by Stronghold Value, Ravage aids
  Surrender, Siegeworks); Storm (Garrison units and columns, Fatimid column,
  Themata garrison selection, Walls, Siegeworks, defenders-Melee-first order,
  6-Hit Melee cap, no-Evade-in-Storm, Sack: Conquer / Ruin / Spoils / remove
  Lords and Themata); Sally and Relief Sally (Storm-like Array, Siegeworks for
  besiegers, Raid reduction on a failed Sally).
- Phase 4: Per-card Arts of War effects for all 50 cards (Events upper half,
  Capabilities lower half), wired into the relevant phases. Until Phase 4,
  cards are tracked as data with effect text in a notes field and the harness
  flags when a card in play would affect a current action.
- Phase 5: LLM-consumer interface (hidden-information filter, curated briefing,
  on-demand lookups, session object routing through the same handlers) and the
  agents / sweeps recommended by CROSS_PROJECT_LESSONS.md (greedy self-play,
  combat-aggressive agent, enumerator/handler round-trip sweep, LLM full-game
  play, tournament). Optional rules 6.1-6.4 behind flags.

Test Discipline

Every rule encoded in code must have at least one test. The test's docstring
cites the rule section. A rule without a test does not exist in the harness.
`pytest -v` should read as a list of every rule the harness claims to
implement, organized by rule section. End-to-end scenario tests should exist
for at least one full Levy + Campaign turn (Year of Treacherous Ambition, the
Learning Scenario, is the natural target) by end of Phase 3a, and at least one
full Battle by end of Phase 3b. The enumerator/handler round-trip sweep (see
CROSS_PROJECT_LESSONS.md §2) becomes a CI gate as soon as legal-moves and
handlers coexist.

Commit and PR Workflow

Small, focused commits with descriptive messages; each commit message
references the rule section it implements OR the question/decision it resolves.
One PR per phase (regular, not draft). The user reviews and merges PRs. The
harness developer does NOT merge to main. Branch naming:
`phase-N-short-description`.

When to Ping the User

The only times to ping the user: a new question batch is ready in
RULES_QUESTIONS.md (let questions accumulate to a reasonable batch, then ping);
a phase PR is ready for review; a test is failing in a way the consultation
chain cannot resolve; a playtest issue requires interpretation. Outside these
triggers, work autonomously.

Out of Scope

AI opponents, strategy advice, or playstyle tuning; graphical interface;
networked / multi-user play; sharing or distribution (private project); the
historical Background Book content as anything other than clarifying examples;
anything not directly serving "run a Seljuk game with state persistence, rules
enforcement, and an LLM-friendly interface."

Engine / Operator Split — Battle and Storm decisions

Battle, Storm, and Sally resolution faithfully implements the Array with
Flanking, Reposition, per-step Strike initiative, Pursuit, Garrison/Themata
defence, Siegeworks, and Sack. Some moments require player judgment that no
deterministic rule pins down: which Reserve Lord advances and to which slot;
which Left/Right Lord slides to fill an empty Center; where to direct Hits when
Flanking creates ambiguity; which unit absorbs each Hit (the owner chooses, per
the Errata/Playbook clarification — the harness must NOT hard-code
weakest-first); whether to Concede; whether each losing Lord Retreats or
Withdraws; which available Themata Service Markers garrison a Stronghold at the
start of a Siege; and whether the Seljuk Sacker Conquers or Ruins.

These choice points flow through a decision context: a scripted_decisions list
(FIFO, for tests), then a callback (for live play), then a deterministic
fallback (e.g. leftmost / first option) so the harness is usable as a
deterministic black box. The full decision trace appears in the result so a
Battle reproduced from a state file plus a recorded decisions list replays
deterministically. Tests that assert specific Hit counts or Routs must use
scripted_decisions; the fallback is acceptable only for structural assertions.

Relationship to Nevsky-Harness

Nevsky-Harness was the structural template for this project: the document set
(BRIEF / README / RULES_DECISIONS / RULES_QUESTIONS / SMOKE_TEST_FINDINGS), the
phased-PR discipline, the no-agent constraint, the ambiguity consultation
chain, and the audit methodology. The two bug-pattern catalogs in this repo
(FUTURE_PROJECTS_LESSONS.md and CROSS_PROJECT_LESSONS.md) were authored against
Nevsky and are kept verbatim because the *patterns* (enumerator/handler
divergence, mirror gaps, lifecycle leaks, no-target no-op events, etc.) are
game-agnostic. SELJUK_LESSONS_ADAPTATION.md flags every place those documents
reference Nevsky-specific subsystems (Veche, Legate, Sail, the dorpat/odenpah
parallel Way, Castle overlays) and maps each pattern to its Seljuk equivalent
or marks it not-applicable. No Nevsky rules, data, cards, scenarios, SMOKE
findings, or code are imported. When the lessons docs cite a Nevsky SMOKE
number or rule, that is an illustrative example of a *pattern*, never a Seljuk
rule.
