# Open Rules Questions

Append questions here using the seven required fields (see `BRIEF.md` —
Question Format). When the user answers, MOVE the entry to
`RULES_DECISIONS.md` with the adjudication, citation, and commit hash.

Work the five-step consultation chain (BRIEF.md) BEFORE logging. Most apparent
ambiguities resolve on reading the references and Rules of Play; only genuinely
undetermined cases belong here.

---

(No open questions. Q-001 was adjudicated by the user and moved to
`RULES_DECISIONS.md` as D-001.)


## Q-002 — Turkic Horse base Melee, and how Shock Tactics (S4/S6) interacts

**Context.** Implementing Battle/Storm Strikes (4.8.2) and the Shock Tactics
Capability. The Units reference lists Turkic Horse Melee as "0.5, capability_
modifier: SHOCK_TACTICS"; the Arts of War reference S4 says "Half of this Lord's
Turkic Horse have Melee x1/2 (round up)"; the errata (Playbook p.14) shows 3
Turkic Horse -> 2 units x1/2 = 1 Hit total *due to* Shock Tactics.

**Consultation log.** Units & Strongholds ref (Turkic Horse strikes), Arts of
War ref (S4/S6 Shock Tactics), Battle & Storm ref (Strike), and the errata
example were all read. The errata states the x1/2 Melee is produced *by* Shock
Tactics. No external sources consulted.

**What is ambiguous.** Whether Turkic Horse have any Melee WITHOUT Shock
Tactics. If the printed 0.5 is their base Melee, then Shock Tactics (which
reduces participation to half the units) would make a Lord *weaker* — implausible
for a Capability. The errata's "due to Shock Tactics" wording implies base
Melee = 0.

**Decision implemented (pending user confirmation).** Turkic Horse have **base
Melee 0**; **Shock Tactics grants** Melee = ceil(unrouted Turkic / 2) x 0.5
(per the errata example). Encoded in `battle.py` (`_HORSE_MELEE` omits Turkic;
`_lord_step_hits_caps` / `_lord_melee_capped` add the Shock-Tactics term).

**Options.** (1) Base Melee 0 + Shock Tactics grants it [implemented]. (2) Base
Melee 0.5/unit and Shock Tactics is a separate effect [rejected: contradicts the
errata and makes the Capability a downgrade].

**Affects.** `battle.py` Strike computation; any all-Turkic Lord's Melee output.
**Blocking?** No (a defensible default is implemented); please confirm or correct.
