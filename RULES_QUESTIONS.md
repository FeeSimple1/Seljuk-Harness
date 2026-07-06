# Open Rules Questions

Append questions here using the seven required fields (see `BRIEF.md` —
Question Format). When the user answers, MOVE the entry to
`RULES_DECISIONS.md` with the adjudication, citation, and commit hash.

Work the five-step consultation chain (BRIEF.md) BEFORE logging. Most apparent
ambiguities resolve on reading the references and Rules of Play; only genuinely
undetermined cases belong here.

---

(Q-001 was adjudicated by the user and moved to `RULES_DECISIONS.md` as D-001.)


## Q-002 — Marwanid Alliance Seats (3.5.1.1): do activated Amid/Mayyafariqin count for MUSTER?

**Context.** S8 Marwanid Alliance: "for each Coin spent, make either the Amid or
Mayyafariqin Locales ... a Seat for Seljuk Lords until the end of the next
Winter Phase. Lords may not tax in these Locales and only one may serve as a
Supply Source per Command card." The harness honors activated Marwanid Seats
for Supply Routes (4.4.1), Winter Bounty paths (4.7.6), and the Tax ban — but
`actions._muster_seats` does NOT include them, so a Ready Seljuk Lord can never
Muster (3.4.1 "at one of his free Seats") at an activated Marwanid Seat.

**Consultation log.** (1) Errata & Clarifications Jan-2026: no entry on S8 /
3.5.1.1. (2) Curated references: Arts of War Reference S8 Clarification covers
the Seat markers only; **Lords Reference lists "Amid?, Mayyafariqin? (conditional
via Marwanid Alliance)" under the Seats line of Alp Arslan, Afsin Beg, Arisighi
and Artuk Beg** — the same line that lists their Muster Seats. (3) Rules of Play
3.5.1.1 (p13): "make either the Amid or Mayyafariqin Locales ... a Seat for
Seljuk Lords", with only the Tax and Supply-Source carve-outs quoted above;
3.3.2/3.4.1 place a Mustering Lord "at one of his free Seats". (4) Background
Book: not consulted for rules (examples only). (5) RULES_DECISIONS.md: no prior
decision. No external/historical sources consulted.

**What is ambiguous.** Whether "a Seat for Seljuk Lords" confers full Seat
status (including Muster placement, since 3.4.1 keys Muster to "his free
Seats") or only the Supply/Bounty functions the rule discusses around its two
explicit exceptions.

**Options.**
- (a) Full Seats: any Seljuk Lord may Muster at an activated Marwanid Seat
  (Lords Reference lists them on each Lord's Seats line; the rule text says
  "a Seat for Seljuk Lords" without a Muster carve-out — the two explicit
  exceptions suggest everything else applies).
- (b) Supply/Bounty only: Muster stays at printed Seats (3.5.1.1 sits in Call
  to Arms and is discussed in Supply terms; "for Seljuk Lords" may mean "for
  the Seljuk side's logistics", and the ? -marks in the Lords Reference may
  simply mirror the conditional activation, not Muster eligibility).

**Affects.** `actions._muster_seats` (Muster + treachery re-entry), levy_lord
seat enumeration, `tests/test_phase2_muster.py`, all scenarios with S8 in deck.

**Blocking?** No — current behavior is Option (b); flagged for adjudication.

## Q-003 — 3.5.2 Loot / 3.5.1.2 Empress: may a cylinder be shifted RIGHT?

**Context.** Call to Arms: "the Seljuk player may remove a Loot marker from the
Mosul and Baghdad box ... to shift a Seljuk Lord cylinder 1 Calendar box"
(3.5.2); the Empress option likewise "Shift a Roman Lord cylinder 1 Calendar
box" (3.5.1.2). Handlers `h_cta_loot`/`h_cta_empress` accept a `direction`
parameter (left/right); the palette enumerates only "left" (sooner Ready).

**Consultation log.** (1) Errata & Clarifications: silent. (2) Curated
references (Sequence of Play B/Call to Arms): repeats "shift ... 1 box" without
direction. (3) Rules of Play 3.5.1.2/3.5.2 (p13): "shift", no direction stated;
no other rule constrains the direction. (4) Background Book: not consulted for
rules. (5) RULES_DECISIONS.md: no prior decision. No external sources.

**What is ambiguous.** Whether "shift 1 Calendar box" permits shifting a
cylinder RIGHT (delaying Readiness) as well as left. A right shift is almost
always self-harming, but the completeness mandate asks whether it is LEGAL,
not whether it is wise.

**Options.**
- (a) Left only: the options exist to accelerate Muster; "shift" reads as
  "advance" in context (spending Loot/the Empress to delay your own Lord has
  no rules purpose, and no card interacts with it).
- (b) Either direction: the text says "shift", not "advance"; if legal it
  should be enumerated (e.g., a Seljuk Lord could dodge an obligation timed to
  his Ready box — none currently known).

**Affects.** `actions.enumerate_call_to_arms`, `h_cta_loot`, `h_cta_empress`,
`tests/test_phase2_aow_cta_loyalty.py`.

**Blocking?** No — current behavior is Option (a); flagged for completeness.

## Q-004 — Sally (4.9.2): per-Lord ordering Hold Events (S3/S6/R24) in the side-aggregate Sally engine

**Context.** 4.9.2: a Sally IS a Battle, so Hold Events playable "in Battle"
apply. This pass wired the Sally command to honor R21/S21 (pre-battle Turkic
removal — exact) and R2/S2 Mountain Ambush (Walls 1-3 vs Missiles, Round 1 —
exact) via `battle_events`. Three Battle holds remain unplayable in a Sally:
S3 Betrayal (move a non-Commander Roman Lord to Reserve after Reposition),
S6 Command Confusion (a Roman Lord's Missiles and Melee each Strike second),
R24 Cavalry Charge (a Roman Lord's Horse Melee precedes all Missiles, Round 1).

**Consultation log.** (1) Errata & Clarifications: silent on Sally-specific
Event limits. (2) Arts of War Reference S3/S6/R24: all say "in Battle" with no
Sally carve-out. (3) Rules of Play 4.5.3/4.9.2: "Attack Besiegers in a Battle";
the approved Sally engine resolves side-aggregate strike steps (Defender then
Attacker within each step) rather than resolve_battle's per-Lord slots, so the
three cards' per-Lord strike-ORDER effects have no exact home. (4) Background
Book: not consulted for rules. (5) RULES_DECISIONS.md: no prior decision on
Sally Event scope. No external sources.

**What is ambiguous.** Not the legality (they are Battle holds and a Sally is
a Battle) but the MAPPING: how per-Lord ordering effects should behave in the
side-aggregate Sally resolver.

**Options.**
- (a) Side-level approximation: S6/R24 reorder the affected SIDE's aggregate
  strike within the step sequence when the named Lord is on that side (front
  or not); S3 removes the named Lord from the Besiegers' array for a Round.
  Playable but knowingly approximate — against the no-simplifications mandate.
- (b) Leave the three cards Sally-ineligible (current state, documented here)
  until adjudicated; they remain fully playable in Battle/Storm windows.
- (c) Rework the Sally engine onto resolve_battle's per-Lord machinery
  (invasive; would need a fresh test baseline for every Sally test).

**Affects.** `campaign.h_cmd_sally`, `battle.resolve_sally`/`_sally_emit`,
`battle._consume_battle_events` allow-set, `tests/test_under_enumeration_audit.py`.

**Blocking?** No — current behavior is Option (b); R21/S21/R2/S2 are live.
