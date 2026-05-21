# Errata & Clarifications — Traceability Audit

Source: `reference/Seljuk Errata and Clarifications.txt` (Jan 31, 2026), which is
content-identical to the March-2026 PDF errata. Per the project rule, the Rules
of Play and this Errata file trump all other inputs.

Every erratum and clarification below is traced to the implementing code and a
pinning test. Status legend: **OK** = implemented + tested before this audit;
**+TEST** = was implemented but had no targeted test until this audit;
**FIXED** = a real gap found and closed by this audit.

## Errata

| # | Erratum (rule) | Implementation | Test | Status |
|---|----------------|----------------|------|--------|
| E1 | Varangian Guard Strikes in Round 1 only; no Pursuit halving (Player Aid) | `battle.py` `_strike_table("foot_melee", r)` zeroes Varangian for r>1 | `test_phase3b_battle.py::test_varangian_strikes_only_round_one_482` | OK |
| E2 | Strategic Objective: Roman Commander must be in Constantinople to TAKE or PLACE (Player Aid / SoP) | `actions.py` `enumerate_call_to_arms` gates both options on `commander_in_cple` | `test_phase2_aow_cta_loyalty.py::..._take_requires_commander...` (positive) + `test_errata_audit.py::test_strategic_objective_unavailable_when_commander_not_in_constantinople` (negative) | +TEST |
| E3 | A Lord re-entering via Treachery arrives in the following season's Levy, before Pay (Rulebook p6, 1.4.2) | `actions.py` `_switch_side` flags `treachery_reentry_box`; `resolve_treachery_reentry` re-places at a free Seat; called from `engine._enter_step("pay")` | `test_errata_treachery_reentry.py` (4 tests) | **FIXED** |
| E4 | Winter Bounty path is blocked by enemy Lords (Rulebook p18, 4.7.6) | `campaign.py` `_bounty_traversable` returns False if `_enemy_lords_at > 0` | `test_errata_audit.py::test_winter_bounty_path_blocked_by_enemy_lord` | +TEST |
| E5 | 1071 (Manzikert) PSILOI is an ALL Capability under the board edge, not on Andronikos Doukas (Rulebook p34) | `data/scenarios/manzikert.json`: R25 (Psiloi) in `board_edge_capabilities.roman`; Andronikos has R13 (Syndosis) | `test_errata_audit.py::test_manzikert_psiloi_under_board_edge_not_on_andronikos` | +TEST |
| E6 | Shock Tactics: half (round up) of Turkic Horse do x1/2 (Playbook p14) | `battle.py` `_lord_step_hits_caps` `ceil(turkic/2)*0.5`; D-002 | `test_phase4b_combat_caps.py::test_shock_tactics_grants_turkic_melee_s4_q002` (pins the Playbook 3->2->1 number) | OK |
| E7 | Attacker cannot Withdraw into the battle site; only Defender/Sallying may (Playbook p17) | `battle.py` `_lord_fate` `can_withdraw = (loser_role == "defender" ...)`; relief-Sally withdraw handled in `campaign.h_respond_approach` | `test_errata_audit.py::test_attacker_cannot_withdraw_into_battle_site_defender_can` | +TEST |

## Clarifications

| # | Clarification | Implementation | Test | Status |
|---|---------------|----------------|------|--------|
| C1 | Seljuk may use LAMELLAR ARMOR or Evade for Protection on a melee Strike (Playbook p17) | `capabilities.py` `protection_range`: Turkic melee returns 1-3 (Evade) when Lamellar inactive, 1-3 (Armor) when active | `test_phase4b_combat_caps.py::test_turkic_evade_vs_melee_unarmored_vs_missile_default` | OK |
| C2 | Themata on the Roman Commander's mat return to their Thema box if he Disbands | `actions.py` `_return_themata_home`, called from both Disband paths (`_disband_beyond`, `_disband_at_limit`) | `test_errata_audit.py::test_themata_return_to_box_when_commander_disbands` | +TEST |

## Notes
- **E1 Pursuit exemption** is vacuously satisfied: Varangian only Strikes in Round 1, and Pursuit halving only applies in a Conceding Round (Round >= 2, since there is no Conceding in Round 1), so the two never overlap. No separate test is required.
- **E3** was the only true correctness gap. `_switch_side` previously set the Lord to `offboard` with a comment that re-placement was "handled by the Pay phase in later phases" — but no Levy step ever re-placed him, so a Treachery-switched Lord was lost from the game permanently. Now closed.
