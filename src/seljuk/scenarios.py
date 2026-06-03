"""Scenario loaders and victory math (Phase 1).

Builds an initial ``GameState`` for each of the five scenarios from
``data/scenarios/*.json`` (themselves validated against the Rules of Play
section 7 setups), and computes Victory Points (5.1) and the victory checks
(5.2, 5.3, plus the Aleppo auto-victory).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import static_data as sd
from .rng import DiceRoller
from .state import (
    Assets,
    GameState,
    HoldingBoxes,
    LocaleState,
    LordState,
    Meta,
    ThemataMarker,
    VassalSlot,
    SideDecks,
)

_SCEN_DIR = Path(__file__).resolve().parent / "data" / "scenarios"

SCENARIOS = [
    "emperor_and_the_lion",
    "specter_of_norman_betrayal",
    "year_of_treacherous_ambition",
    "showdown_in_anatolia",
    "manzikert",
]


def _scenario_data(name: str) -> dict[str, Any]:
    path = _SCEN_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"unknown scenario {name!r}; choices: {SCENARIOS}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _stronghold_value(locale_id: str) -> int:
    t = sd.locale(locale_id)["type"]
    return {"fort": 1, "town": 2, "city": 3}.get(t, 0)


def _themata_box_contents(themata_key: str) -> dict[str, list[ThemataMarker]]:
    data = sd.themata()
    baseline = data["baseline_1068"]
    removals = data["scenario_removals"].get(themata_key, {})
    out: dict[str, list[ThemataMarker]] = {}
    for thema, markers in baseline.items():
        pool = [dict(m) for m in markers]
        for rem in removals.get(thema, []):
            # remove one marker matching (unit, symbols)
            for i, mk in enumerate(pool):
                if mk["unit"] == rem["unit"] and mk["symbols"] == rem["symbols"]:
                    pool.pop(i)
                    break
            else:  # pragma: no cover - validated at data-build time
                raise ValueError(f"{themata_key}: cannot remove {rem} from {thema}")
        out[thema] = [ThemataMarker(**m) for m in pool]
    return out


def _lord_side(lord_id: str, override: str | None) -> str:
    if override:
        return override
    return sd.lord(lord_id)["side"]


def _build_vassals(lord_id: str, levied_forces: list[dict[str, int]]) -> tuple[list[VassalSlot], dict[str, int]]:
    """Return (vassal slots, extra forces from any pre-levied Vassals)."""
    info = sd.lord(lord_id)
    slots: list[VassalSlot] = []
    extra: dict[str, int] = {}
    pending = [dict(f) for f in (levied_forces or [])]
    for v in info.get("vassals", []):
        slot = VassalSlot(forces=dict(v["forces"]), service=v.get("service"))
        # match a pre-levied request to this slot
        for i, want in enumerate(pending):
            if want == v["forces"]:
                slot.levied = True
                for u, n in v["forces"].items():
                    extra[u] = extra.get(u, 0) + n
                pending.pop(i)
                break
        slots.append(slot)
    if pending:  # pragma: no cover - validated at data-build time
        raise ValueError(f"{lord_id}: could not match levied vassals {pending}")
    for sv in info.get("special_vassals", []):
        slots.append(
            VassalSlot(
                forces=dict(sv["forces"]),
                service=sv.get("service"),
                special_name=sv.get("name"),
                requires_capability=sv.get("requires_capability"),
            )
        )
    return slots, extra


def load_scenario(name: str, seed: int = 1) -> GameState:
    s = _scenario_data(name)
    roller = DiceRoller(seed=seed)

    meta = Meta(
        scenario=name,
        seed=seed,
        rng_state=list(roller.get_state()),
        calendar_box=s["start_box"],
        final_box=s["final_box"],
        phase="campaign" if s.get("skip_first_levy") else "levy",
        active_player="seljuk",
        vp=dict(s["starting_vp"]),
        seljuk_unity_targets=dict(s.get("seljuk_unity_targets", {})),
        aleppo_independence_played=bool(s.get("aleppo_independence_played", False)),
        skip_first_levy=bool(s.get("skip_first_levy", False)),
        special_vp_rules=list(s.get("special_vp_rules", [])),
        notes={
            "calendar_reminders": s.get("calendar_reminders", []),
            "first_turn_plan_size": s.get("first_turn_plan_size"),
            "nomisma_debased_used": s.get("nomisma_debased_used", False),
            "strategic_objectives_removed_from_play": s.get("strategic_objectives_removed_from_play", 0),
            # SMOKE-003: a skip_first_levy scenario starts mid-campaign with its
            # Capabilities already deployed by setup (board_edge_capabilities +
            # per-Lord). That pre-placement IS the scenario's First Levy Arts of
            # War (A.1.2 / 3.1.2), so the first PLAYED Levy must draw Events
            # (A.1.3 / 3.1.3), not deploy Capabilities again. Mark it done here;
            # non-skip scenarios run the opening Arts of War at start_new, which
            # sets this flag itself.
            "first_aow_done": bool(s.get("skip_first_levy", False)),
        },
    )

    gs = GameState(meta=meta)

    # Locales (all 44, default unmarked) ------------------------------------
    for lid in sd.all_locale_ids():
        gs.locales[lid] = LocaleState()
    mk = s["markers"]
    for r in mk.get("ruins", []):
        gs.locales[r["locale"]].ruins = True
        gs.locales[r["locale"]].ruins_color = r.get("color", "seljuk")
    for c in mk.get("conquered", []):
        loc = gs.locales[c["locale"]]
        loc.conquered_side = c["side"]
        loc.conquered_count = _stronghold_value(c["locale"])
    for r in mk.get("ravaged", []):
        gs.locales[r["locale"]].ravaged_side = r["side"]
    for sg in mk.get("siege", []):
        gs.locales[sg["locale"]].siege_markers = sg.get("count", 1)
    for loc in mk.get("bypass", []):
        gs.locales[loc].bypass = True
    for loc in mk.get("fort", []):
        gs.locales[loc].fort_marker = True
    for loc in mk.get("strategic_objective_locale", []):
        gs.locales[loc].strategic_objective = True

    # Themata boxes ----------------------------------------------------------
    gs.themata = _themata_box_contents(s["themata_key"])

    # Lords ------------------------------------------------------------------
    mustered = {e["lord"]: e for e in s["mustered"]}
    on_cal = {e["lord"]: e for e in s["on_calendar"]}
    removed = set(s.get("removed_lords", []))
    for lord_id in sd.all_lord_ids():
        info = sd.lord(lord_id)
        if lord_id in mustered:
            e = mustered[lord_id]
            side = _lord_side(lord_id, e.get("side"))
            assets = dict(info["starting_assets"])
            assets.update(e.get("assets_override", {}))
            slots, extra = _build_vassals(lord_id, e.get("vassals_levied", []))
            forces = dict(info["starting_forces"])
            for u, n in extra.items():
                forces[u] = forces.get(u, 0) + n
            gs.lords[lord_id] = LordState(
                id=lord_id, side=side, mustered=True, cylinder=e["locale"],
                service_box=s["service"].get(lord_id),
                forces=forces,
                assets=Assets(**{k: assets.get(k, 0) for k in ("carts", "provender", "coin", "loot")}),
                vassals=slots,
                capabilities=list(e.get("capabilities", [])),
            )
        elif lord_id in on_cal:
            e = on_cal[lord_id]
            gs.lords[lord_id] = LordState(
                id=lord_id, side=_lord_side(lord_id, e.get("side")), mustered=False,
                cylinder="calendar", cylinder_calendar_box=e["box"],
            )
        elif lord_id in removed:
            gs.lords[lord_id] = LordState(
                id=lord_id, side=info["side"], mustered=False, cylinder="removed",
                flags={"setup_removed": True},
            )
        else:  # pragma: no cover - validated at data-build time
            raise ValueError(f"{name}: lord {lord_id} not accounted for")

    # Strategic Objective marker placed on a Seljuk Lord's mat? (none at setup
    # in the published scenarios; SO-on-mat is created in play.)

    # Card decks -------------------------------------------------------------
    levied: set[str] = set()
    for side in ("roman", "seljuk"):
        for cid in s["board_edge_capabilities"].get(side, []):
            levied.add(cid)
    for e in s["mustered"]:
        for cid in e.get("capabilities", []):
            levied.add(cid)
    for side in ("roman", "seljuk"):
        deck = [c for c in sd.card_ids_for_side(side) if c not in levied]
        board_edge = list(s["board_edge_capabilities"].get(side, []))
        cap_coins = {cid: int(n) for cid, n in s.get("capability_coins", {}).items()
                     if cid in sd.card_ids_for_side(side)}
        gs_side = SideDecks(draw_deck=deck, capabilities_in_play=board_edge,
                            capability_coins=cap_coins)
        if side == "roman":
            gs.roman = gs_side
        else:
            gs.seljuk = gs_side

    # Holding boxes ----------------------------------------------------------
    hb = s["holding_boxes"]
    gs.holding_boxes = HoldingBoxes(
        mosul_baghdad_loot=hb.get("mosul_baghdad_loot", 0),
        constantinople_strategic_objectives_available=hb.get("constantinople_strategic_objectives_available", 0),
        constantinople_roman_vp_markers=hb.get("constantinople_roman_vp_markers", 0),
    )
    return gs


# --- Victory math (5.1-5.3) -------------------------------------------------

def score(gs: GameState) -> dict[str, float]:
    """Recompute VP totals from markers (Rules 5.1).

    Each side: 1/2 VP per its Ruins and per its Ravaged markers. Roman: +1 VP
    per Roman Conquered marker on the map (Seljuk Conquered = 0 VP), plus 1 VP
    per Strategic Objective / Conquered VP marker in the Constantinople box.
    Seljuk: +1 VP per Loot in the Mosul & Baghdad box.
    """
    roman = 0.0
    seljuk = 0.0
    for loc in gs.locales.values():
        if loc.ruins and loc.ruins_color == "roman":
            roman += 0.5
        if loc.ruins and (loc.ruins_color or "seljuk") == "seljuk":
            seljuk += 0.5
        if loc.ravaged_side == "roman":
            roman += 0.5
        elif loc.ravaged_side == "seljuk":
            seljuk += 0.5
        if loc.conquered_side == "roman":
            roman += float(loc.conquered_count)
        # Seljuk Conquered markers are worth 0 VP.
    roman += float(gs.holding_boxes.constantinople_roman_vp_markers)
    seljuk += float(gs.holding_boxes.mosul_baghdad_loot)
    sr, ss = _scenario_special_vp(gs)
    roman += sr
    seljuk += ss
    return {"roman": round(roman, 1), "seljuk": round(seljuk, 1)}


def _locale_control(gs: GameState, locale_id: str) -> str:
    """Side a Locale is currently Friendly to (Conquered flips it; Fatimid ->
    Roman). Inlined to avoid importing actions (circular)."""
    loc = gs.locales[locale_id]
    if loc.conquered_side:
        return loc.conquered_side
    return "seljuk" if sd.locale(locale_id)["allegiance"] == "seljuk" else "roman"


def _scenario_special_vp(gs: GameState) -> tuple[float, float]:
    """Scenario-setup VP rules beyond the standard marker VPs (transcribed in
    each scenario's `special_vp_rules`), keyed on the scenario id."""
    roman = 0.0
    seljuk = 0.0
    scen = gs.meta.scenario
    if scen == "manzikert":
        # "Both sides score 1 VP for each permanently Disbanded enemy Lord."
        for lid, l in gs.lords.items():
            if l.cylinder == "removed" and not l.flags.get("setup_removed"):
                if sd.lord(lid)["side"] == "seljuk":
                    roman += 1.0   # a permanently Disbanded Seljuk Lord -> Roman scores
                else:
                    seljuk += 1.0
    elif scen == "year_of_treacherous_ambition":
        # "Romans +1 VP if Arisighi switches sides" (he starts Seljuk).
        ar = gs.lords.get("arisighi")
        if ar is not None and ar.side == "roman":
            roman += 1.0
        # "Seljuks +1 VP each for reaching Ikonion and/or Western Anatolia with a
        # Lord" (latched in campaign.h_cmd_march when a Seljuk Lord arrives).
        if gs.meta.notes.get("reached_ikonion"):
            seljuk += 1.0
        if gs.meta.notes.get("reached_western_anatolia"):
            seljuk += 1.0
        # "End of Winter 1070: both sides +1 VP each for control of Manbij,
        # Edessa, Khliat, and Manzikert." Scored once the scenario reaches its
        # final turn (Autumn 1070 -> Winter 1070 is the conclusion).
        if (gs.meta.calendar_box >= gs.meta.final_box
                and (gs.meta.subphase == "campaign.end" or gs.meta.phase in ("winter", "game_over"))):
            for locid in ("manbij", "edessa", "khliat", "manzikert"):
                ctrl = _locale_control(gs, locid)
                if ctrl == "roman":
                    roman += 1.0
                elif ctrl == "seljuk":
                    seljuk += 1.0
    return roman, seljuk


def mustered_lords(gs: GameState, side: str) -> list[str]:
    return [lid for lid, l in gs.lords.items() if l.mustered and l.side == side]


def campaign_victory(gs: GameState) -> str | None:
    """Immediate (5.2) victory check; returns the winning side or None.

    - If a side has no Mustered Lords on the map during Campaign, the other
      side wins.
    - Seljuk wins in the first Winter phase if Aleppo is Seljuk-Conquered and
      Aleppo Independence has been played for effect (checked by the Winter
      handler in a later phase; surfaced here for completeness).
    """
    if gs.meta.phase == "campaign":
        if not mustered_lords(gs, "seljuk"):
            return "roman"
        if not mustered_lords(gs, "roman"):
            return "seljuk"
    return None


def end_of_scenario_winner(gs: GameState) -> str:
    """Final victory (5.3): higher VP wins; equal = draw.

    Manzikert has no Winter Phase, so its end-of-Autumn-1071 special conditions
    are evaluated here: Aleppo Seljuk-Conquered -> Seljuks; else Manzikert AND
    Khliat both Roman-Conquered (and Aleppo not Seljuk) -> Romans."""
    if gs.meta.scenario == "manzikert":
        aleppo_seljuk = gs.locales["aleppo"].conquered_side == "seljuk"
        if aleppo_seljuk:
            return "seljuk"
        if (gs.locales["manzikert"].conquered_side == "roman"
                and gs.locales["khliat"].conquered_side == "roman"):
            return "roman"
    vp = score(gs)
    if vp["roman"] > vp["seljuk"]:
        return "roman"
    if vp["seljuk"] > vp["roman"]:
        return "seljuk"
    return "draw"
