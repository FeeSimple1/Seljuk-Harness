"""Seedable dice for deterministic, auditable play.

All Seljuk rolls are standard d6 (Rules of Play 1.2). The harness rolls every
die; the consumer never rolls (BRIEF.md, "Dice and Mechanical Resolution").
The RNG state is serialized into the game-state file so a saved game replays
bit-for-bit, and every roll is meant to be logged with its context.

This module is pure infrastructure (no game rules) and is intentionally usable
from Phase 0.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class DiceRoller:
    """A deterministic d6 source whose state round-trips through a game file."""

    seed: int

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def d6(self) -> int:
        """Roll a single standard six-sided die (1-6)."""
        return self._rng.randint(1, 6)

    def roll(self, n: int) -> list[int]:
        """Roll ``n`` d6 and return the results in order."""
        return [self.d6() for _ in range(n)]

    def get_state(self) -> tuple:
        """Opaque RNG state for serialization into ``state.meta.rng_state``."""
        return self._rng.getstate()

    def set_state(self, state: tuple) -> None:
        """Restore RNG state loaded from a game file."""
        self._rng.setstate(state)
