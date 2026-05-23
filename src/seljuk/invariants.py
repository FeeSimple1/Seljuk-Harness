"""State invariants that must hold in EVERY reachable game state.

`check_invariants(gs)` returns a list of human-readable violation strings (empty
when the state is sound). Used by the property-fuzzing test and available to the
round-trip sweep as a second safety net beyond enumerator/handler agreement.
"""
from __future__ import annotations

from .state import GameState
from . import static_data as sd

ASSET_CAP = 8                  # 1.7.3 Asset 8-cap
OFF_RIGHT = 13                 # Calendar off-right edge
_SPECIAL_CYL = {"calendar", "offboard", "removed"}


def _valid_cylinders() -> set[str]:
    return set(sd.all_locale_ids()) | _SPECIAL_CYL


def check_invariants(gs: GameState) -> list[str]:
    bad: list[str] = []
    valid_cyl = _valid_cylinders()

    # Calendar bounds (may sit one past final_box at game end).
    if not (1 <= gs.meta.calendar_box <= gs.meta.final_box + 1):
        bad.append(f"calendar_box {gs.meta.calendar_box} out of 1..{gs.meta.final_box + 1}")

    # Holding-box counters are never negative.
    hb = gs.holding_boxes
    for name in ("mosul_baghdad_loot", "constantinople_roman_vp_markers"):
        v = getattr(hb, name, 0)
        if v < 0:
            bad.append(f"holding_box {name} negative: {v}")

    # VP is never negative (advisory §3: cheap always-on bound). It is a derived
    # sum of non-negative contributions; a negative value signals corruption.
    for side in ("roman", "seljuk"):
        v = gs.meta.vp.get(side, 0)
        if v < 0:
            bad.append(f"vp[{side}] negative: {v}")

    # Seljuk Unity targets never go negative.
    for box, val in gs.meta.seljuk_unity_targets.items():
        if val < 0:
            bad.append(f"seljuk_unity_targets[{box}] negative: {val}")

    # Plan pointers never run past the plan.
    for side in ("seljuk", "roman"):
        d = gs.side_decks(side)
        if d.plan_pointer > len(d.command_plan):
            bad.append(f"{side} plan_pointer {d.plan_pointer} > plan len {len(d.command_plan)}")

    # Per-Lord invariants.
    for lid, l in gs.lords.items():
        for asset in ("carts", "provender", "coin", "loot"):
            v = getattr(l.assets, asset)
            if not (0 <= v <= ASSET_CAP):
                bad.append(f"{lid}.{asset}={v} out of 0..{ASSET_CAP}")
        for u, n in l.forces.items():
            if n < 0:
                bad.append(f"{lid}.forces[{u}]={n} negative")
        for u, n in l.routed.items():
            if n < 0:
                bad.append(f"{lid}.routed[{u}]={n} negative")
        if l.service_box is not None and not (0 <= l.service_box <= OFF_RIGHT):
            bad.append(f"{lid}.service_box={l.service_box} out of 0..{OFF_RIGHT}")
        if l.cylinder_calendar_box is not None and not (0 <= l.cylinder_calendar_box <= OFF_RIGHT):
            bad.append(f"{lid}.cylinder_calendar_box={l.cylinder_calendar_box} out of range")
        if l.cylinder not in valid_cyl:
            bad.append(f"{lid}.cylinder={l.cylinder!r} is not a valid Locale/token")
        # An off-map / removed Lord must not also be flagged Mustered-on-map.
        if l.cylinder in ("offboard", "removed") and l.mustered:
            bad.append(f"{lid} is {l.cylinder} but still mustered")

    # Per-Locale invariants.
    for locid, st in gs.locales.items():
        if not (0 <= st.siege_markers <= 4):
            bad.append(f"{locid}.siege_markers out of 0..4: {st.siege_markers}")
        if st.conquered_count < 0:
            bad.append(f"{locid}.conquered_count negative: {st.conquered_count}")

    # No two opposing Lords, both "in the open" (neither Besieged-inside nor
    # Bypassing), may share a Locale. Cheap class-closing guard (Inferno-Harness
    # Retreat advisory): a post-combat Retreat/Sally that applied a Service
    # penalty but forgot to relocate the loser would strand opposing Lords
    # together and trip this check. Three states are legal co-locations and are
    # excluded:
    #   * Besieged-inside vs. besiegers-outside (keyed on `besieged`, not on a
    #     Siege marker).
    #   * A Bypassing Lord sharing the Locale with an enemy: the Approach trigger
    #     fires only on an "Unbesieged, Unbypassed Enemy Lord" (4.3.4/4.3.5), so
    #     a `bypassed` Lord legitimately coexists with an enemy.
    #   * Mid-contact: right after a March into an enemy-occupied Locale an
    #     `approach_response` is owed and both Lords are momentarily co-located
    #     until the defender Avoids/Withdraws/Stands.
    contact_pending = {p.get("locale") for p in gs.meta.pending
                       if p.get("type") == "approach_response"}
    open_sides: dict[str, set[str]] = {}
    for lid, l in gs.lords.items():
        if not l.mustered or l.cylinder in _SPECIAL_CYL or l.besieged or l.bypassed:
            continue
        if l.cylinder in contact_pending:
            continue
        open_sides.setdefault(l.cylinder, set()).add(l.side)
    for loc, sides in open_sides.items():
        if len(sides) > 1:
            bad.append(f"opposing in-the-open Lords share Locale {loc}: {sorted(sides)}")

    return bad
