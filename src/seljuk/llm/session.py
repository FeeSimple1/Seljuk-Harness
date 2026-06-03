"""LLMSession: the consumer-facing wrapper around the harness (Phase 5).

Holds one GameState and routes every action through the same engine handlers as
the CLI/tests. Manages phase transitions (Levy <-> Campaign) so a consumer can
drive a whole game. Exposes hidden-info-filtered state, a briefing, the legal
move palette, pending sub-decisions, lookups, and save/load.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .. import engine, campaign, scenarios, options as _options
from ..state import GameState
from . import view, briefing as _briefing, tools


class LLMSession:
    def __init__(self, gs: GameState) -> None:
        self.gs = gs
        # over-enumeration diagnostics from the last validated legal_actions() call
        self.palette_diagnostics: list[dict[str, Any]] = []

    @classmethod
    def start_new(cls, scenario: str, seed: int = 1,
                  options: dict[str, Any] | None = None) -> "LLMSession":
        """Begin a scenario. ``options`` selects Optional Rules (6.0); if omitted,
        standard rules apply. A driver should present :meth:`optional_rules` to
        the player at the outset and pass back their choices here."""
        s = cls(scenarios.load_scenario(scenario, seed, options=options))
        s.ensure_phase_started()
        return s

    @staticmethod
    def optional_rules() -> list[dict[str, Any]]:
        """The Optional Rules (6.0) a player may enable at the outset, for a
        chooser UI. Pass selections to :meth:`start_new` as ``options=``."""
        return _options.OPTIONAL_RULES

    def active_options(self) -> list[str]:
        """Human-readable list of Optional Rules currently in effect (empty =
        standard rules)."""
        return _options.describe(self.gs.meta.options)

    def ensure_phase_started(self) -> None:
        """Begin the current phase's step machine if it hasn't started, and roll
        Levy <-> Campaign transitions when a phase completes."""
        m = self.gs.meta
        if m.phase == "levy" and m.subphase is None:
            engine.start_levy(self.gs)
        elif m.phase == "levy" and m.subphase == "levy.complete":
            campaign.start_campaign(self.gs)
        elif m.phase == "campaign" and m.subphase is None:
            campaign.start_campaign(self.gs)

    # --- consumer API ---
    def state(self, side: Optional[str] = None) -> dict[str, Any]:
        return view.filtered_state(self.gs, side or self.gs.meta.active_player)

    def briefing(self) -> str:
        return _briefing.briefing(self.gs)

    def legal_actions(self, validated: bool = False) -> list[dict[str, Any]]:
        """Legal-move palette. With ``validated=True`` (the agent-facing path),
        probe-and-drop handler-rejected moves and record any drops on
        ``self.palette_diagnostics`` (Nevsky advisory §2)."""
        if not validated:
            return engine.legal_moves(self.gs)
        moves, self.palette_diagnostics = engine.validated_legal_moves(self.gs)
        return moves

    def pending(self) -> list[dict[str, Any]]:
        return list(self.gs.meta.pending)

    def apply(self, action: dict[str, Any]) -> dict[str, Any]:
        res = engine.apply_action(self.gs, action)
        self.ensure_phase_started()
        return res

    def lookup_card(self, card_id: str) -> dict[str, Any]:
        return tools.lookup_card(card_id)

    def lookup_lord(self, lord_id: str) -> dict[str, Any]:
        return tools.lookup_lord(lord_id)

    def is_over(self) -> bool:
        return self.gs.meta.phase == "game_over"

    def winner(self) -> Optional[str]:
        return self.gs.meta.notes.get("winner")

    def save(self, path: str) -> None:
        Path(path).write_text(self.gs.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> "LLMSession":
        return cls(GameState.from_json(Path(path).read_text(encoding="utf-8")))
