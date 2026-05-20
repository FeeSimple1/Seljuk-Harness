"""Game-state model (Pydantic) and the canonical action error.

Phase 1 fills in the full Pydantic model: meta (scenario, calendar position,
active player, RNG state, victory totals), per-side state, Lords (cylinders,
mats, Forces, Assets, Vassals, Capabilities, Service Markers), Locales
(Strongholds, markers, Siege/Bypass/Conquered/Ruins/Ravaged), Themata boxes,
Holding Boxes (Constantinople, Mosul & Baghdad), and both card decks. The state
serializes to a single portable JSON file (BRIEF.md, "Architecture
Requirements").

Only the error type is defined in Phase 0 so handlers across the codebase can
import a stable symbol.
"""
from __future__ import annotations


class IllegalAction(Exception):
    """Raised when a submitted action violates the rules.

    Carries a machine-readable ``code`` plus a human message that should cite
    the relevant rule section. The legal-moves enumerator and its handlers must
    stay in agreement; every ``IllegalAction`` raised by a handler is a
    candidate gap in the enumerator (CROSS_PROJECT_LESSONS.md sections 1-2).
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}" if message else code)
