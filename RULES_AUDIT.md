# Seljuk Rules of Play — Full Traceability Audit

A clause-by-clause walk of the entire Rules of Play (Sections 1.0–5.0), mapping
each rule to its implementing code and a pinning test. This complements
`ERRATA_AUDIT.md` (which covers only the Errata & Clarifications corrections).

Authority order (project rule): the Rules of Play and Errata & Clarifications
trump all else. Sources audited: `reference/*.txt` (curated rule references) and
`source/Seljuk_Rules.pdf` / `source/Seljuk_Background_Book_web.pdf` (Playbook).

Status: **OK** = implemented and tested. Where a clause was found wrong or
untested during this or an earlier audit, the fix/commit is noted inline.
At audit time: 420 tests pass; round-trip + invariant sweep clean (5 scenarios ×
8 seeds); 20 randomized smoke rounds clean.

Legend: code = `module.function`; test = `test_file::test_name` (representative).

---

## 1.0 Components & Core Concepts

| Clause | Rule | Code | Test |
|--------|------|------|------|
| 1.1–1.3 | Sides (Seljuk/Roman), board, Locales/Ways/Passes | `static_data`, `map` (`ways_from`, `adjacent_to_pass`, `is_adjacent`) | `test_phase1_map_state` |
| 1.3.1 | Special Locales: Aleppo (no Withdraw), Holding Boxes, Passes | `map.adjacent_to_pass`; `battle._lord_fate` (no_withdraw_aleppo) | `test_phase1_map_state`, `test_errata_audit` |
| 1.4 | Treachery & Loyalty | `actions.resolve_loyalty_check`, `_switch_side`, `events._set_treachery` | `test_phase6_treachery`, `test_coverage_actions` |
| 1.4.1 | Loyalty Check roll (nat 1 fails, nat 6 succeeds, > Fealty switches) | `actions.resolve_loyalty_check` | `test_coverage_actions::test_loyalty_natural_one_never_switches_and_six_always` |
| 1.4.2 | Switched Lord Disbands & re-enters next Levy before Pay | `actions._switch_side`, `resolve_treachery_reentry` | `test_errata_treachery_reentry` (4 tests) |
| 1.5.1 | Forces & units; Themata Service Markers | `static_data.forces`, `state.ThemataMarker` | `test_phase1_data_integrity` |
| 1.5.2 | Sharing co-located Carts/Provender/Loot | `campaign._available_carts`, `_share_food` | `test_phase3a_end_winter::test_feed_sharing_covers_shortfall_461` |
| 1.5.3 | Command rating (+ Capability bonuses) | `capabilities.command_rating` | `test_phase4a_ratings` |
| 1.5.4 | Lordship / Fealty / Service ratings | `capabilities.lordship_rating`, `fealty_rating`; `state.LordState.service_box` | `test_phase4a_ratings` |
| 1.6 | Forces categories (Horse/Foot), Strike values | `battle._category`, `_MISSILE/_HORSE_MELEE/_FOOT_MELEE` | `test_phase3b_battle`, `test_phase4b_combat_caps` |
| 1.7.3 | Asset 8-cap | enforced at every `min(.., 8)`; `invariants.check_invariants` | `test_invariants_fuzz` |
| 1.9.1 | Cards return to decks | `campaign.build_plan`, `actions.resolve_arts_of_war` | `test_phase1_scenarios` |
| 1.9.2 | Plan card limits (≤4/Lord, ≤5 No Command) | `campaign.build_plan` | `test_coverage_campaign::test_build_plan_*` |

## 2.0 Calendar, Setup & Ready

| Clause | Rule | Code | Test |
|--------|------|------|------|
| 2.0/2.1 | Scenario setup (5 scenarios), first-turn overrides | `scenarios.load_scenario`, `_build_vassals` | `test_phase1_scenarios` |
| 2.2 | Seasonal turns; 12-box Calendar; advance | `campaign.season_index`, `_advance_or_end`; `state.Meta.calendar_box` | `test_phase3a_end_winter::test_end_campaign_advances_turn_when_not_final` |
| 2.2.3/2.2.4 | Ready (cylinder on Calendar); availability to Muster | `actions.h_levy_lord` (target_not_ready gate) | `test_phase2_muster` |

## 3.0 Levy

| Clause | Rule | Code | Test |
|--------|------|------|------|
| 3.1.1 | Shuffle decks | `scenarios` deck setup; `rng.DiceRoller` | `test_phase1_scenarios` |
| 3.1.2 | First Levy — draw & deploy Capabilities | `actions.resolve_arts_of_war`, `_deploy_first_levy_capability`, `h_deploy_capability` | `test_phase2_aow_cta_loyalty` |
| 3.1.3 | Later Levy — draw Events (immediate/Hold/Treachery classified) | `actions._classify_drawn_event`, `events.resolve_event`, `play_hold_event` | `test_phase4c_events_passives`, `test_phase6_more_events` |
| 3.1.4 | Greed (Asset/Capability discard) | `events._wastage_once` (shared) | `test_coverage_events::test_wastage_*` |
| 3.2.1 | Pay with Coin (own + co-located; Commander Coin any distance) | `actions._pay_targets`, `h_pay` | `test_phase2_pay_disband`, `test_coverage_actions::test_pay_*` |
| 3.2.2 | Pay with Loot (Friendly Locale free of Siege) | `actions._payer_can_use_loot` | `test_coverage_actions::test_pay_loot_location_guard` |
| 3.3.1 | Disband Beyond Service Limit (Lords past their Service box) | `actions.resolve_disband`, `_disband_beyond` | `test_phase2_pay_disband` |
| 3.3.2 | Disband At Service Limit (recycle to Calendar; Themata return home) | `actions._disband_at_limit`, `_return_themata_home` | `test_phase2_pay_disband`, `test_errata_audit::test_themata_return_to_box_when_commander_disbands` |
| 3.4.1 | Levy Other Lords (1 Lordship, Fealty roll, free Seat) | `actions.h_levy_lord`, `_muster_seats`, `_seat_is_free` | `test_phase2_muster` |
| 3.4.2 | Levy Vassals (slide ready Vassal Forces) | `actions.h_levy_vassal`, `_vassal_levyable` | `test_phase2_muster`, `test_phase6_special_vassals` |
| 3.4.3 | Levy Transport (+1 Cart, 8-cap) | `actions.h_levy_transport` | `test_phase2_muster` |
| 3.4.4 | Levy Capabilities (scope/eligibility/no-dupe) | `actions.h_levy_capability`, `_capability_eligible`, `_maybe_add_special_vassal` | `test_phase2_muster`, `test_phase6_special_vassals` |
| 3.4.5 | Levy Themata (Roman Commander in his Thema) | `actions.h_levy_themata` | `test_phase2_muster::test_levy_themata_roman_commander_only_345` |
| 3.5.1 | Call to Arms — Capability-driven options (Marwanid/Empress/Deep Raids) | `events` resolvers; `actions.enumerate_call_to_arms` | `test_phase4c_events_passives` |
| 3.5.2 | Call to Arms — Loot (shift a Ready Seljuk Lord) | `actions.h_cta_loot` | `test_phase2_aow_cta_loyalty`, `test_coverage_actions::test_cta_loot_*` |
| 3.5.3 | Call to Arms — Strategic Objective (Commander in Constantinople) | `actions.h_cta_strategic_objective` | `test_phase2_aow_cta_loyalty`, `test_errata_audit` |

## 4.0 Campaign — Plan, Activation & Non-Combat Commands

| Clause | Rule | Code | Test |
|--------|------|------|------|
| 4.0 | Capability Discard (side-wide caps > Mustered Lords) | `campaign._capability_discard` | `test_phase3a_campaign` |
| 4.1.1/4.1.2 | Plan: select & arrange ordered face-down stacks | `campaign.build_plan` | `test_phase3a_campaign`, `test_coverage_campaign` |
| 4.1.3 | Lieutenants (Lieutenant + Lower Lord, same Locale, no Commander) | `campaign._designate_lieutenant` | `test_phase3a_campaign`, `test_coverage_campaign::test_designate_lieutenant_guards` |
| 4.2.1 | Command actions = Lord's Command rating | `campaign._reveal_next`, `spend_actions` | `test_phase3a_campaign` |
| 4.2.2 | Command Menu | `campaign.command_menu`, `legal_moves_campaign` | `test_phase3a_commands`, `test_smoke_enumerator_affordability` |
| 4.2.3 | No Command card / off-map / Lower-Lord card = Pass | `campaign._is_pass_card`, `_reveal_next` | `test_phase3a_campaign` |
| 4.3.1 | Group March (Commander leads co-located Lords; stacks move) | `campaign._marching_group` | `test_phase3b_march` |
| 4.3.2 | Laden / Over-laden (Loot or Prov > Carts; >2 Prov/Cart can't move) | `campaign.group_laden`, `_over_laden` | `test_phase3b_march`, `test_smoke_enumerator_affordability::test_over_laden_suppresses_march` |
| 4.3.3 | March cost (Road 1, Pass +1, Laden +1, Turkic first-march −1, Mules) | `campaign.march_cost`, `h_cmd_march` | `test_phase3b_march`, `test_smoke_enumerator_affordability` |
| 4.3.4 | Approach: Avoid / Withdraw / Stand (→ Battle) | `campaign.h_respond_approach`, `_validate_avoid`, `_validate_withdraw` | `test_phase3b_march`, `test_phase6_relief_strategic` |
| 4.3.5 | Besiege / Bypass an enemy Stronghold | `campaign.h_besiege_bypass`, `_resolve_arrival` | `test_phase3b_march` |
| 4.4 / 4.4.1 | Supply (Route to un-Ruined Seat, Cart budget, blocked Locales) | `campaign._min_supply_cost`, `_blocks_supply`, `h_cmd_supply` | `test_phase3a_end_winter::test_supply_*_44*` |
| 4.5.1 | Siege (advance Siege / roll Surrender / add Siegeworks) | `campaign.h_cmd_siege` | `test_phase3c_siege_storm` |
| 4.5.2 | Storm command | `campaign.h_cmd_storm` → `battle.resolve_storm` | `test_phase3c_siege_storm` |
| 4.5.3 | Sally command (Besieged Lord attacks Besiegers) | `campaign.h_cmd_sally` → `battle.resolve_sally` | `test_phase3c_siege_storm::test_sally_*_492` |
| 4.5.4 | Forage (auto at Friendly/Gardens; else roll; Besieged limits) | `campaign.h_cmd_forage` | `test_phase3a_commands`, `test_coverage_campaign_commands` |
| 4.5.5 | Ravage (Enemy Locale; Roman 1 action; Seljuk 1–2; Themata defence) | `campaign.h_cmd_ravage`, `h_resolve_ravage_defence` | `test_phase3a_commands`, `test_coverage_campaign_commands` |
| 4.5.6 | Tax (own Seat; Roman Commander Empire Tax → Ravaged marker) | `campaign.h_cmd_tax` | `test_phase3a_commands`, `test_coverage_campaign_commands` |
| 4.5.7 | Recruit (Roman Commander in Thema takes a Themata) | `campaign.h_cmd_recruit` | `test_phase3a_end_winter::test_recruit_roman_commander_takes_themata_457` |
| 4.5.8 | Pass | `campaign.h_cmd_pass` | `test_phase3a_commands` |
| 4.6.1 | Feed (requirement by unit count; Loot anywhere; Share; Unfed→Service −1) | `campaign.feed_pay_disband`, `_feed_requirement`, `_feed_side`, `_consume_food`, `_share_food` | `test_phase3a_end_winter::test_feed_*_461` |
| 4.6.2/4.6.3 | Campaign Pay & Disband; remove Moved/Fought markers | `campaign.feed_pay_disband` | `test_phase3a_campaign` |
| 4.7.1 | Game End (final box) | `campaign._advance_or_end`, `_set_game_over` | `test_phase3a_end_winter` |
| 4.7.2 | Grow (Spring: halve enemy Ravaged) | `campaign._grow` | `test_phase3a_end_winter::test_grow_*_472` |
| 4.7.3 | Repair (remove 1 Siege from 3–4) | `campaign._repair` | `test_phase3a_end_winter::test_repair_*_473` |
| 4.7.4 | Wastage (discard excess Asset/Capability) | `campaign._wastage`, `events._wastage_once` | `test_phase3a_end_winter::test_wastage_*_474` |
| 4.7.5 | Reset (return unpaid Themata, unstack Lieutenants, discard This-Campaign) | `campaign._reset` | `test_coverage_campaign::test_reset_returns_themata_to_boxes` |
| 4.7.6 | Winter (Aleppo auto-victory, Bounty, Unity, Quarters; R9/S18 activation) | `campaign._winter`, `_bounty`, `_seljuk_unity`, `_winter_quarters`, `h_winter_activate` | `test_phase3a_end_winter`, `test_phase6_winter`, `test_errata_audit::test_winter_bounty_path_blocked_by_enemy_lord` |

## 4.8 Battle

| Clause | Rule | Code | Test |
|--------|------|------|------|
| 4.8.1 | Array (Front L/C/R + Reserve; Active at Center; Defender opposite) | `battle.resolve_battle`, `_fill_front`, `_fill_defender` | `test_phase3b_battle` |
| 4.8.1 | Relief Sally rows (Sallying row behind Defenders; Rearguard row) | `battle._fill_row`, `_fill_rearguard`, `_secondary` | `test_phase6_relief_rearguard` (4 tests) |
| 4.8.2 | Rounds: Concede → Reposition → Strike | `battle.resolve_battle` loop, `_offer_concede`, `_reposition` | `test_phase3b_battle` |
| 4.8.2 | Reposition: Rout / Adjust Rows / Advance / Center | `battle._purge_routed`, `_adjust_rows`, `_reposition` | `test_phase6_relief_rearguard` |
| 4.8.2 | Strike initiative (Def then Att; Missile then Melee; Horse before Foot) | `battle._strike_phase`, `_resolve_step` | `test_phase3b_battle`, `test_phase6_strike_order` |
| 4.8.2 | Flanking (no opposite → closest in row; Center chooses) | `battle._target_of` | `test_phase3b_battle` |
| 4.8.2 | Total Hits (per-unit values, round up); Strike sub-ordering (Charge/CC) | `battle._lord_step_hits_caps`, `_strike_phase` (cc/charge) | `test_phase6_strike_order` |
| 4.8.2 | Protection (Armor/Evade/Unarmored; Capability mods) | `capabilities.protection_range`, `battle._apply_hits` | `test_phase4b_combat_caps`, `test_oracle_playbook_example` |
| 4.8.2 | Pursuit halving (Conceding side; Turkic-only exception) | `battle._emit` (pursuit), `_resolve_step` | `test_phase3b_battle` |
| 4.8.3 | Ending: Retreat / Withdraw (Defender only) / Removal | `battle._end_battle`, `_lord_fate` | `test_errata_audit::test_attacker_cannot_withdraw_into_battle_site_defender_can` |
| 4.8.4 | Losses (Routed units roll Protection; Harsh for non-conceding loser) | `battle._resolve_losses`, `_natural_protection` | `test_phase3b_battle` |
| 4.8.3 | Spoils & Service | `battle._spoils_and_removal`, award helpers | `test_phase3b_battle` |
| 4.8.5 | Lord Removal by Combat (no Forces) | `battle._remove_by_combat`, `_spoils_and_removal` | `test_phase3b_battle` |
| 4.8.6 | Aftermath (Moved/Fought; Feed-Pay-Disband) | `battle._end_battle`; `campaign._after_card` | `test_phase3b_battle` |

## 4.9 Siege, Storm & Sally

| Clause | Rule | Code | Test |
|--------|------|------|------|
| 4.5.1 | Siege: Surrender roll (dice, threshold, Ravaged +1, Brutal Rep reroll) | `campaign.h_cmd_siege` | `test_phase3c_siege_storm` |
| 4.9.1 | Storm Array/Concede/Reposition (Storm variant) | `battle.resolve_storm`, `_storm_reposition` | `test_phase3c_siege_storm` |
| 4.9.1 | Garrison (foot columns + Themata defenders; R16/S23 caps) | `battle._build_garrison`, `_garrison_column` | `test_phase3c_siege_storm`, `test_phase4b_combat_caps` |
| 4.9.1 | Garrison Strikes (Missile: each unit's value, foot gains ½; Melee) | `battle._garrison_missile_hits`, `_garrison_melee_hits` | `test_oracle_playbook_example::test_storm_example_garrison_missile_total_is_two` (**fixed**: horse Themata Missiles were dropped) |
| 4.9.1 | Walls (defender) & Siegeworks (attacker) roll separately | `battle._roll_walls`, `_hit_attacker`, `_hit_defender`, `_effective_walls` | `test_phase3c_siege_storm`, `test_oracle_playbook_example` |
| 4.9.1 | Storm losses (Attacker Harsh; Armored-first); Lord removal | `battle._storm_losses`, `_loss_roll`, `_absorb_storm` | `test_phase3c_siege_storm` |
| 4.9.1 | Sack: Conquer or Ruin; Spoils; Themata removed | `battle._sack`, `conquer`, `ruin`, `award_spoils` | `test_phase3c_siege_storm::test_storm_defender_routed_sacks_and_conquers_491` |
| 4.9.2 | Sally / Relief Sally / Raid (besiegers lose → Siege ends; fail → Siege to 1) | `battle.resolve_sally`, `_end_sally_besiegers_lose`, `_absorb_simple` | `test_phase3c_siege_storm::test_sally_*_492`, `test_coverage_battle` |

## 5.0 Victory

| Clause | Rule | Code | Test |
|--------|------|------|------|
| 5.1 | Earning VP (½ Ruins, ½ Ravaged, 1 Roman Conquered; Strategic Objectives) | `scenarios.score` | `test_phase1_scenarios`, `test_phase3a_end_winter` |
| 5.2 | Campaign Victory (Aleppo auto-victory; Seljuk Unity threshold) | `scenarios.score`, `campaign._winter`, `_seljuk_unity`, `_set_game_over` | `test_phase3a_end_winter::test_aleppo_independence_auto_victory_476`, `test_phase6_winter` |
| 5.3 | End of Scenario Victory (final-box VP comparison) | `scenarios.end_of_scenario_winner` | `test_phase1_scenarios`, `test_phase5b_selfplay` |

---

## Findings & Notes

This full audit found **one new defect**, now fixed:
- **Pursuit Turkic-only exception (4.8.2)** was not implemented. The rule: a
  single Conceding Lord whose Forces are ONLY Turkic Horse at the start of the
  battle, facing a single opposing Lord, causes BOTH sides to halve Hits in the
  final Round (not just the conceder). `battle.resolve_battle` now records
  Turkic-only-at-start + solo-battle and sets both Pursuit flags on such a
  Concede. Test: `test_rules_audit_pursuit.py`.

Spot-checks of the high-stakes numeric rules matched the rulebook exactly (Feed
ladder 4.6.1 = 1/2/3/4 at 8/12/16/17+; Disband split 3.3.1/3.3.2 at Service box
</=; Shock Tactics ceil(n/2)×½ per the errata; garrison Missiles per the
Playbook). All other Section 1–5 clauses map to implementing code and at least
one pinning test.

Defects found by the **earlier** targeted passes (all fixed before this audit):
- Treachery re-entry never re-placed a switched Lord (Errata audit; 1.4.2).
- Garrison Missile fire dropped Themata horse units (Playbook oracle; 4.9.1).
- March/Ravage enumerator offered unaffordable moves (smoke fuzzer; 4.3/4.5.5).
- Plan size omitted the owed Treachery card (round-trip sweep; 4.1).

The combination of this static clause-by-clause audit with the dynamic gates
(round-trip + invariant sweep, 20 randomized smoke rounds, the Playbook oracle)
covers the rules from both directions: every clause is implemented and tested,
and every reachable state stays rule-consistent.

---

## Full Rules Audit — Pass 2 (clause-by-clause, June 2026)

A second full pass: six parallel section audits (1.x; 2-3 Levy; 4.0-4.5; 4.6-4.7;
4.8-4.9; 5/scenarios/errata/cards) against `source/Seljuk_Rules.pdf` text, with
each finding verified and the confirmed bugs fixed + pinned by tests (suite 560
green at the end of the pass).

### Fixed this pass

- **5.2 immediate victory by permanent Disband** — a permanently Disbanded Alp
  Arslan ends the game for Rome (every scenario; "removed" implies he was in
  play, covering the Specter caveat); Manzikert: a permanently Disbanded Romanos
  ends it for the Seljuks. `_campaign_5_2_over`.
- **Manzikert end-of-Autumn-1071 conditions** (no Winter phase): Aleppo Seljuk-
  Conquered → Seljuks; else Manzikert AND Khliat both Roman-Conquered (Aleppo not
  Seljuk) → Romans. `scenarios.end_of_scenario_winner`.
- **4.8.4 Harsh Losses** now apply to ANY non-conceding loser who Retreats (was
  restricted to the attacker) — Battle and Sally (losing Besiegers).
- **4.8.5** Storm now removes any Lord reduced to no Forces on either side (was
  missed in the attacker-loses branch and for a winning Attacker on a Sack).
- **4.3.4** Avoid may not cross the Way the enemy Approached on; Withdraw is
  capped at the Stronghold's Size (covers the Lieutenant-into-Fort note).
- **4.3.6** ENCAMP (Bypass→Siege) and SORTIE (defenders Approach the bypasser)
  implemented (`cmd_encamp`, `cmd_sortie`).
- **1.5.1** Manuel is Commander only if Romanos is not ON THE MAP (was `mustered`).
- **1.3.1/R14** Aleppo is Friendly to BOTH sides after Independence.
- **3.5.1.1 Marwanid** Coin model corrected: transfer Alp Arslan Coin → card
  (`cta_marwanid_bank`) vs spend card Coin to activate (one option may activate
  both Locales).
- **3.5.1.2 Empress Eudokia (R12)** implemented (`cta_empress`).
- **1.4.1 Loyalty Check** Coin DRMs deducted from valid sources + bounded; owner
  may not resist for a Besieged target.
- **4.2.1/4.5.4 Forage** while Besieged: allowed when inadequately Besieged;
  blocked at ≥ Size (handler + menu), except friendly Gardens Town/City.
- **4.8.2/4.9.1** Storm melee resolved as separate Horse/Foot steps (each rounded).
- **1.4.2** treachery re-entry places/clears the Seat's Conquered markers.

### Final tidy pass — "little things" (June 2026)

Implemented the tractable edge items left after Pass 2, each pinned by tests:

- **S9 Imperial Rivalry** — the Andronikos Doukas Muster attempt is now *forced*
  during Roman Muster while the Capability is in play and an enumerable
  levy_lord targets him (`h_pass_step` gate; latch reset each muster segment).
- **3.5.1.1 Marwanid one Supply Source per Command card** — when BOTH Amid and
  Mayyafariqin are active Seats, the first Supply that routes via one locks it
  for the rest of that card; the other Seat is excluded until the next card
  (`_min_supply_route` + `marwanid_supply_lock`, cleared in `_reveal_next`).
- **Storm Garrison Missiles "select target"** — the striker now picks the
  highest-effective armored unit among the target Lord's armored Forces, rather
  than the first in the pool (`_absorb_storm(select_target=True)`).
- **4.3.x Avoid while Laden** — a Laden Lord may now Avoid by discarding to
  Unladen (drop Loot + Provender over Carts); the discarded Assets are awarded
  to the Approaching attackers as Spoils (round-robin, 8-cap) instead of the
  Avoid being rejected outright (`_award_avoid_spoils`).
- **4.6 Feed Sharing** — Sharing now covers the *smallest* remaining shortfalls
  first, maximising fully-fed Lords and so minimising Unfed Service shifts
  (B.3.1), rather than letting one big-need Lord drain the shared Provender.
- **Housekeeping** — removed the unused `treachery_available` field; the Year
  end-of-Winter control VP bonus no longer displays one step early (gated to the
  end-of-campaign / Winter subphase; the actual winner determination is
  unchanged).

### Follow-up pass (June 2026) — the three "deferred" items, now implemented

A second LLM review correctly argued these were resolvable from the rules text
(verified against `source/Seljuk_Rules.pdf`), not genuine ambiguities. All three
are now implemented + tested:

- **4.8.2 Flanking absorb / receiving-Lord choice** — when the target Lord D is
  Struck only by the Lord directly opposite him (no Enemy Flanks D) and the
  receiving side has a Flanking Lord F whose Flank-Strike falls on that same
  opposing Lord, the receiving Player may route the pooled Hits onto F instead of
  D, resolved before unit Select Target (`_absorb_target` in `_resolve_step`).
  The earlier "deterministic, tie-prompt only" model was wrong: the choice is
  live whenever the gate (no enemy Flanks the target) holds.
- **1.6 unit-component pool as a hard Muster cap** — Muster (3.4.1), Levy Vassal
  (3.4.2) and Restore (S5/S19) now clamp added units to the pieces remaining in
  the pool (manifest: Ghulam 6, Scholai 2, Varangian 2, Norman Knights 5, Turkic
  Horse 47, Tagmata 25, Infantry 52, Militia 11). `_units_in_play` tallies an
  exact lower bound of in-play pieces (Forces + Routed + Themata) so the cap never
  wrongly blocks a legal Muster.
- **4.4.2 multi-Provender Supply** — a Lord now draws one Provender per Stronghold
  Seat used in a single Supply action, each Seat funded by its own Carts along its
  Route (Carts not shared across Routes, per the 4.4.1 Important box), bounded by
  the Cart budget and the 8-Provender cap. The old single-cheapest-Seat router
  under-supplied any Lord positioned to fund disjoint Routes to two Seats
  (`_supply_plan`).

### Optional Rules 6.0 (player-selectable, June 2026)

All four optional rules are now implemented as per-game toggles (off by default --
the designer notes they are "not the 'real' way to play"). They live in
`gs.meta.options`, are selected via `load_scenario(options=...)` /
`LLMSession.start_new(options=...)`, and are catalogued in `options.py`
(`OPTIONAL_RULES`) so a driver can present them at the outset; a driver that
isn't told which rules to use should ask before starting. Active rules show in
the LLM briefing.

- **6.1 Hidden Mats** — `llm/view.py` redacts the enemy's Mustered Lord mats
  (Forces, Assets, Vassals, This-Lord Capabilities) from the viewing side; the
  Locale, Service marker and Besieged/Bypassed status stay public.
- **6.2 Vassal Service** — a Mustering Vassal's Service Marker is placed on the
  Calendar by its Service Rating, shifts with its Lord's Marker through every
  Service-shift channel (Pay, Harsh Losses, Unfed, Events, Empress), is Unready
  (may not Muster) after Disbanding this Levy and flips up after Muster, and
  Disbands at its Service limit -- returning its Forces to the pool (1.6), and
  Disbanding a Lord left without Forces.
- **6.3 Simultaneous Horse Combat** — three-way player choice (off / melee /
  missiles / both). In Battle (not Storm), the chosen Horse-unit Strikes of both
  sides resolve simultaneously (pools computed before any application), removing
  the fire-first advantage (`_compute_pools` / `_apply_pools`).
- **6.4 Deadlier Seljuk Missiles** — in Battle, Seljuk Missiles always Strike
  first regardless of Attacker/Defender (missile sub-phase ordered Seljuk-first).

Nothing in 6.0 remains out of scope.

### Pass 2 known items (now resolved above)

### Known remaining items (low impact / edge / documented simplifications)

- S9 Imperial Rivalry: the *mandatory* Andronikos Muster attempt is not forced
  (offered as optional).
- Marwanid "only one Supply Source per Command card" when BOTH Seats are active
  (the supply pathfinder already routes each Lord to one cheapest Seat per action).
- Storm Garrison Missiles "select target" (armored-first is enforced; striker's
  pick among armored units is not).
- Supply drawing >1 Provender/action via disjoint Cart-funded routes (4.4.2 edge).
- Avoid: discard-to-Unladen + award discarded Assets to the attacker as Spoils
  (current model rejects a Laden Avoid outright — stricter).
- Feed Sharing uses greedy allocation (minimises but doesn't optimise Unfed).
- Flanking "absorb / choose target Lord" optional choice (deterministic target).
- Unit component pool is not a hard Muster limit; `treachery_available` field is
  unused; mid-Winter VP display can include the Year end-control bonus one step
  early. Optional rules 6.1-6.4 remain out of scope (BRIEF.md Phase 5).
