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
from contextlib import contextmanager
from contextvars import ContextVar
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

    def shuffle(self, seq: list) -> None:
        """Shuffle a list in place using the seeded RNG (deterministic)."""
        self._rng.shuffle(seq)

    def get_state(self) -> tuple:
        """Opaque RNG state for serialization into ``state.meta.rng_state``."""
        return self._rng.getstate()

    def set_state(self, state: tuple) -> None:
        """Restore RNG state loaded from a game file."""
        self._rng.setstate(state)


_active_roller: ContextVar[tuple | None] = ContextVar("seljuk_active_roller", default=None)


def roller_for_state(gs) -> DiceRoller:
    """Get the current action's stream, or reconstruct a standalone stream."""
    active = _active_roller.get()
    if active is not None and active[0] is gs:
        return active[1]
    roller = DiceRoller(seed=gs.meta.seed)
    if gs.meta.rng_state is not None:
        st = gs.meta.rng_state
        roller.set_state((st[0], tuple(st[1]), st[2]))
    return roller


@contextmanager
def action_roller(gs):
    """Share one stream through nested battle, card, and campaign effects."""
    roller = roller_for_state(gs)
    token = _active_roller.set((gs, roller))
    try:
        yield roller
        st = roller.get_state()
        gs.meta.rng_state = [st[0], list(st[1]), st[2]]
    finally:
        _active_roller.reset(token)
