# Agents and sweeps (Phase 5)

Not part of the shipped harness (these ARE agents; the harness must not contain
one — BRIEF.md). Planned: `self_play.py` (greedy), a combat-aggressive agent,
`roundtrip_sweep.py` (the enumerator/handler audit from
CROSS_PROJECT_LESSONS.md section 2), `llm_self_play.py`, and `llm_tournament.py`.

## long_play.py

Sustained deep-coverage self-play (companion to `self_play.py` and
`smoke_fuzz.py`). Keeps both sides alive through Levy (Pay → Muster Lords back
from the Calendar → other levies/CtA) and avoids rushing the VP/Unity victory, so
games run to the final calendar box through every Winter and the end-of-game VP
scoring. Checks invariants, round-trips every enumerated move, verifies
serialization stability, and runs `scenarios.score()` after every step.

```
PYTHONPATH=src python3 scripts/long_play.py <scenario|ALL> <seeds csv>
SUSTAIN=1 PYTHONPATH=src python3 scripts/long_play.py emperor_and_the_lion 1,2,3
```
