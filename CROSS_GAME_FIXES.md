# Cross-game audit repairs

The November 4, 2026 cross-game audit identified seven Seljuk defect groups.
This first repair batch addresses audit ID **R3**:

- **R3 — Rejected compound actions:** the public dispatcher restores the
  board, RNG and appended history when resolution raises an exception. A
  multi-Lord Approach response with an invalid later choice no longer leaves
  an earlier Lord moved or Assets transferred to the enemy.

Regression tests submit the original mixed valid/invalid Avoid response
through `LLMSession.apply`, verify retained board references, then compare a
corrected retry against a pristine position. A second test checks rollback
following dice use and partial history changes. Existing history entries are
not copied or traversed on each action.

The other six Seljuk findings remain open.
