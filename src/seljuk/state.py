"""Game-state model (Pydantic v2) and the canonical action error.

A single ``GameState`` serializes to one portable JSON file and fully
reconstructs the game (BRIEF.md, "Architecture Requirements"). The model is
deliberately comprehensive enough to represent any of the five scenarios'
initial setups; later phases add the handlers that mutate it.

Determinism: dice come from a seeded RNG whose serialized state lives in
``meta.rng_state`` so a saved game replays bit-for-bit (see rng.py).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class IllegalAction(Exception):
    """Raised when a submitted action violates the rules.

    Carries a machine-readable ``code`` plus a human message that should cite
    the relevant rule section. Every ``IllegalAction`` a handler can raise is a
    candidate gap in the legal-moves enumerator (CROSS_PROJECT_LESSONS.md 1-2).
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}" if message else code)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Assets(_Model):
    carts: int = 0
    provender: int = 0
    coin: int = 0
    loot: int = 0


class VassalSlot(_Model):
    """A Vassal Service Marker on a Lord's mat (1.5.4, 3.4.2).

    ``levied`` True means the Vassal's Forces have been added to the Lord's
    Forces section. Special Vassals carry ``requires_capability``.
    """

    forces: dict[str, int]
    service: Optional[int] = None
    special_name: Optional[str] = None
    requires_capability: Optional[str] = None
    levied: bool = False
    service_box: Optional[int] = None  # 6.2 Vassal Service: Calendar position when Mustered
    unready: bool = False              # 6.2: Coat-of-Arms down (Disbanded this Levy) -> may not Muster


class ThemataMarker(_Model):
    """A Themata Service Marker (1.5.1). ``symbols`` 2 = a 'double' marker.

    ``home_thema`` records the Thema box a Levied/Recruited marker came from, so
    it can be returned there on Commander Disband (3.3.2 errata) or Reset."""

    unit: str
    symbols: int = 1
    home_thema: Optional[str] = None


class LordState(_Model):
    """Per-Lord state. The cylinder is on the map (a Locale), on the Calendar
    (Ready / disbanded-at-limit), off-board, or removed; the Service Marker is
    tracked separately by ``service_box`` (1.5.1, 2.2.3, 3.4.1)."""

    id: str
    side: str  # current allegiance: "roman" | "seljuk"
    mustered: bool = False
    # cylinder: a Locale id, or "calendar" | "offboard" | "removed"
    cylinder: str = "offboard"
    cylinder_calendar_box: Optional[int] = None
    service_box: Optional[int] = None  # Service Marker position (Calendar 1-12; 0/13 = off-edge)

    forces: dict[str, int] = Field(default_factory=dict)
    routed: dict[str, int] = Field(default_factory=dict)
    lost: dict[str, int] = Field(default_factory=dict)  # units permanently Lost in combat (S5/S19 may restore)
    assets: Assets = Field(default_factory=Assets)
    vassals: list[VassalSlot] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)  # "This Lord" card ids (max 2)
    themata_on_mat: list[ThemataMarker] = Field(default_factory=list)  # Roman Commander Levied/Recruited

    # Markers / status
    moved_fought: bool = False
    besieged: bool = False
    bypassed: bool = False
    strategic_objective: bool = False  # a Roman Strategic Objective marker placed on this (Seljuk) Lord's mat
    lieutenant_of: Optional[str] = None
    lower_lord: Optional[str] = None
    flags: dict[str, Any] = Field(default_factory=dict)  # ad-hoc per-Lord flags/marks (later phases)


class LocaleState(_Model):
    """Per-Locale markers (1.3.1). Defaults represent an unmarked Locale."""

    conquered_side: Optional[str] = None  # "roman" | "seljuk"
    conquered_count: int = 0
    ruins: bool = False
    ruins_color: Optional[str] = None  # Seljuk only place Ruins
    ravaged_side: Optional[str] = None
    siege_markers: int = 0
    bypass: bool = False
    fort_marker: bool = False  # from Imperial Fortress Construction (R1)
    strategic_objective: bool = False
    themata_defending: list[ThemataMarker] = Field(default_factory=list)
    flags: dict[str, Any] = Field(default_factory=dict)


class SideDecks(_Model):
    """A side's Arts of War / Command card state."""

    draw_deck: list[str] = Field(default_factory=list)        # Arts of War cards available to draw
    capabilities_in_play: list[str] = Field(default_factory=list)  # side-wide (board edge) card ids
    held_events: list[str] = Field(default_factory=list)
    this_campaign_events: list[str] = Field(default_factory=list)
    command_plan: list[str] = Field(default_factory=list)     # face-down Plan stack (Campaign): lord ids / "no_command"
    plan_pointer: int = 0                                     # how many Plan cards revealed
    capability_coins: dict[str, int] = Field(default_factory=dict)  # Coins resting on a Capability card (card_id -> count), e.g. Marwanid Alliance S8


class HoldingBoxes(_Model):
    constantinople_strategic_objectives_available: int = 0
    constantinople_roman_vp_markers: int = 0  # claimed SO + Roman Conquered VP markers in the box
    mosul_baghdad_loot: int = 0


class Meta(_Model):
    scenario: str
    seed: int = 0
    rng_state: Optional[Any] = None  # serialized DiceRoller state (rng.py)
    calendar_box: int = 1            # current Seasonal Turn (1-12)
    final_box: int = 12              # last Turn of the scenario
    phase: str = "levy"              # "levy" | "campaign" | "winter"
    subphase: Optional[str] = None
    active_player: str = "seljuk"    # Seljuk first (2.2.4)
    vp: dict[str, float] = Field(default_factory=lambda: {"roman": 0.0, "seljuk": 0.0})
    seljuk_unity_targets: dict[str, int] = Field(default_factory=dict)  # {"3": 10, "6": 13, ...}
    aleppo_independence_played: bool = False
    independent_aleppo_on_map: bool = False
    asterisks_used: list[str] = Field(default_factory=list)
    skip_first_levy: bool = False
    special_vp_rules: list[str] = Field(default_factory=list)
    levy_step_passed: dict[str, bool] = Field(default_factory=dict)  # which sides finished the current Levy step
    pending: list[dict[str, Any]] = Field(default_factory=list)      # pending sub-decisions (who owes a response)
    plan_submitted: dict[str, bool] = Field(default_factory=dict)    # which sides have built their Campaign Plan (4.1)
    active_card: Optional[str] = None                                # currently-revealed Command card (lord id / "no_command")
    active_lord: Optional[str] = None                                # Lord activated by the current card
    actions_remaining: int = 0                                       # Command actions left this card (4.2.1)
    notes: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)  # Optional Rules 6.0 (see options.py)



class GameState(_Model):
    """Complete, portable game state."""

    meta: Meta
    lords: dict[str, LordState] = Field(default_factory=dict)
    locales: dict[str, LocaleState] = Field(default_factory=dict)
    themata: dict[str, list[ThemataMarker]] = Field(default_factory=dict)  # Thema box contents
    holding_boxes: HoldingBoxes = Field(default_factory=HoldingBoxes)
    seljuk: SideDecks = Field(default_factory=SideDecks)
    roman: SideDecks = Field(default_factory=SideDecks)
    history: list[dict[str, Any]] = Field(default_factory=list)

    # ---- persistence ----
    def to_json(self, *, indent: int | None = 1) -> str:
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "GameState":
        return cls.model_validate_json(text)

    def side_decks(self, side: str) -> SideDecks:
        return self.seljuk if side == "seljuk" else self.roman


def shift_vassal_service(gs: "GameState", lord: "LordState", delta: int) -> None:
    """6.2 Vassal Service: whenever a Lord's Service Marker shifts for any reason,
    shift each of his Mustered Vassals' Markers the same number of boxes (2.2.3
    off-Calendar clamping 0..13). No-op unless the optional rule is in effect."""
    if not (gs.meta.options or {}).get("vassal_service"):
        return
    for v in lord.vassals:
        if v.levied and v.service_box is not None:
            v.service_box = max(0, min(13, v.service_box + delta))
