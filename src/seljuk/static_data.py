"""Loaders for static reference data (Phase 1).

Reads the JSON under ``data/static/`` derived faithfully from the curated
references in ``reference/``: Lords and ratings, Forces (Strikes / Protection),
Strongholds (Garrison columns / Walls / Surrender dice / Spoils), the Locale +
Way map graph, Themata rosters, and the 50 Arts of War cards as data. Per
CROSS_PROJECT_LESSONS.md section 7, loads in the enumerator are wrapped in
try/except so a data-shape error suppresses an option rather than crashing.
"""
