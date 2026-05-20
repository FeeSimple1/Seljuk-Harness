"""Scenario loaders and victory math (Phase 1).

Builds an initial game state for each of the five scenarios (The Emperor and
the Lion; Specter of Norman Betrayal; Year of Treacherous Ambition; Showdown in
Anatolia; Manzikert) from ``data/scenarios/``: Mustered Lords and placements,
Calendar markers and Service positions, Themata removals and face-up
placements, pre-placed map markers, Levied Capabilities, per-scenario special
VP rules, and Seljuk Unity targets. Also computes VP totals (5.1) and the
victory checks (5.2, 5.3, and the Aleppo auto-victory).
"""
