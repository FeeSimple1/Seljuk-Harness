# Open Rules Questions

Append questions here using the seven required fields (see `BRIEF.md` —
Question Format). When the user answers, MOVE the entry to
`RULES_DECISIONS.md` with the adjudication, citation, and commit hash.

Work the five-step consultation chain (BRIEF.md) BEFORE logging. Most apparent
ambiguities resolve on reading the references and Rules of Play; only genuinely
undetermined cases belong here.

---

## Q-002 — Steeled Resolve Infantry armor value: reference vs data disagree

**Context.** R3 Steeled Resolve (Bottom Capability).
**Question.** Does the Capability set the Lord's Infantry armor to 1-3 or 1-4 vs Horse?
**Conflict.** `reference/Seljuk Arts of War Reference.txt` states "Armor 1-3" in
both the card text and the clarification. `Seljuk_Units_and_Strongholds.txt` (and
the engine, `capabilities.protection_range` + `battle._ARMORED`) implement base
Infantry armor 1-3 with Steeled Resolve -> 1-4. These are inconsistent: if base
Infantry armor really is 1-3, a "1-3" Capability is a no-op, which is implausible.
**Two coherent resolutions.** Either (a) base Infantry armor is 1-2 and the
reference's "1-3" is the buffed value (engine should change base to 1-2, keep
SR -> 1-3); or (b) the reference propagated a "1-3"-for-"1-4" transcription error
and the data (base 1-3, SR -> 1-4) is correct.
**Deciding fact (unresolved).** The printed Forces table's Infantry armor value
on the physical Player Aid. Not extractable from the PDFs in the project (the
rulebook Forces excerpt shows only Horse rows).
**Current engine state.** Implements (b): base 1-3, SR vs Horse -> 1-4 (the only
internally coherent pair as written in the data files). Whichever value wins, one
reference file needs a correction entry.

(Q-001 was adjudicated by the user and moved to `RULES_DECISIONS.md` as D-001.)


(Q-002 adjudicated by the user 2026-05-20 and moved to RULES_DECISIONS.md as D-002.)
