"""State rendering: summary, verbose, and focused views (Phase 1).

Summary aims for a compact, LLM-friendly overview; verbose dumps the full
state JSON; focused views render a single Lord's mat, a Locale, the Calendar,
or a Thema box. Rendering is descriptive only — it never recommends an action
(BRIEF.md, "No Agent in the Harness").
"""
from __future__ import annotations

from . import scenarios, static_data as sd
from .state import GameState

_SEASON = {1: "Spring", 2: "Summer", 0: "Autumn"}


def _box_label(box: int) -> str:
    if box < 1 or box > 12:
        return f"box{box}(off-calendar)"
    year = 1068 + (box - 1) // 3
    season = ["Spring", "Summer", "Autumn"][(box - 1) % 3]
    return f"{season} {year}"


def _forces_str(forces: dict[str, int]) -> str:
    parts = [f"{n} {u}" for u, n in forces.items() if n]
    return ", ".join(parts) if parts else "-"


def _assets_str(a) -> str:
    parts = [f"{getattr(a, k)} {k}" for k in ("carts", "provender", "coin", "loot") if getattr(a, k)]
    return ", ".join(parts) if parts else "-"


def summary(gs: GameState) -> str:
    m = gs.meta
    vp = scenarios.score(gs)
    lines = [
        f"Scenario: {m.scenario}  |  {_box_label(m.calendar_box)} (box {m.calendar_box}/{m.final_box})"
        f"  |  Phase: {m.phase}  |  Active: {m.active_player}",
        f"VP — Roman {vp['roman']}  Seljuk {vp['seljuk']}"
        f"   (Mosul&Baghdad Loot {gs.holding_boxes.mosul_baghdad_loot};"
        f" Constantinople VP markers {gs.holding_boxes.constantinople_roman_vp_markers})",
    ]
    for side in ("seljuk", "roman"):
        lines.append(f"\n{side.upper()} Lords:")
        for lid, l in gs.lords.items():
            if l.side != side:
                continue
            if l.mustered:
                loc = sd.locale(l.cylinder)["name"]
                status = f"@ {loc} (Service {_box_label(l.service_box) if l.service_box else '?'})"
                extra = []
                if l.forces:
                    extra.append(_forces_str(l.forces))
                if l.capabilities:
                    extra.append("caps: " + ",".join(l.capabilities))
                detail = "  [" + " | ".join(extra) + "]" if extra else ""
                lines.append(f"  {sd.lord(lid)['name']:22s} {status}{detail}")
            elif l.cylinder == "calendar":
                lines.append(f"  {sd.lord(lid)['name']:22s} Ready {_box_label(l.cylinder_calendar_box)}")
            elif l.cylinder == "removed":
                lines.append(f"  {sd.lord(lid)['name']:22s} (removed from play)")
        capset = gs.side_decks(side).capabilities_in_play
        if capset:
            lines.append(f"  side-wide Capabilities: {', '.join(capset)}")
    # Map markers of note
    marked = []
    for lid, loc in gs.locales.items():
        bits = []
        if loc.conquered_side:
            bits.append(f"{loc.conquered_side[0].upper()}-Conq x{loc.conquered_count}")
        if loc.ruins:
            bits.append("Ruins")
        if loc.ravaged_side:
            bits.append(f"{loc.ravaged_side[0].upper()}-Ravaged")
        if loc.siege_markers:
            bits.append(f"Siege x{loc.siege_markers}")
        if loc.bypass:
            bits.append("Bypass")
        if loc.fort_marker:
            bits.append("Fort marker")
        if loc.strategic_objective:
            bits.append("Strategic Objective")
        if bits:
            marked.append(f"  {sd.locale(lid)['name']}: {', '.join(bits)}")
    if marked:
        lines.append("\nMap markers:")
        lines.extend(marked)
    return "\n".join(lines)


def verbose(gs: GameState) -> str:
    return gs.to_json(indent=2)


def lord_view(gs: GameState, lord_id: str) -> str:
    if lord_id not in gs.lords:
        return f"(no such Lord: {lord_id})"
    l = gs.lords[lord_id]
    info = sd.lord(lord_id)
    r = info["ratings"]
    out = [
        f"{info['name']} — {info['epithet']}  [{l.side}]",
        f"  Fealty {r['fealty']}  Service {r['service']}  Lordship {r['lordship']}  Command {r['command']}",
        f"  Status: {'Mustered' if l.mustered else l.cylinder}"
        + (f" @ {sd.locale(l.cylinder)['name']}" if l.mustered else "")
        + (f"  (Service {_box_label(l.service_box)})" if l.service_box else ""),
        f"  Forces: {_forces_str(l.forces)}",
        f"  Routed: {_forces_str(l.routed)}",
        f"  Assets: {_assets_str(l.assets)}",
    ]
    if l.vassals:
        vs = [
            (v.special_name or "Vassal") + f" ({_forces_str(v.forces)})" + (" [levied]" if v.levied else "")
            + (f" req {v.requires_capability}" if v.requires_capability else "")
            for v in l.vassals
        ]
        out.append("  Vassals: " + "; ".join(vs))
    if l.capabilities:
        out.append("  This-Lord Capabilities: " + ", ".join(l.capabilities))
    if l.themata_on_mat:
        out.append("  Themata on mat: " + ", ".join(f"{t.unit}x{t.symbols}" for t in l.themata_on_mat))
    if l.strategic_objective:
        out.append("  * Roman Strategic Objective marker on this mat")
    return "\n".join(out)


def locale_view(gs: GameState, locale_id: str) -> str:
    if locale_id not in gs.locales:
        return f"(no such Locale: {locale_id})"
    info = sd.locale(locale_id)
    st = gs.locales[locale_id]
    lords_here = [sd.lord(lid)["name"] for lid, l in gs.lords.items() if l.mustered and l.cylinder == locale_id]
    out = [
        f"{info['name']} — {info['type']} ({info['allegiance']}"
        + (f", Thema {info['thema']}" if info["thema"] else "") + ")",
    ]
    prof = sd.stronghold_profile(locale_id)
    if prof:
        out.append(f"  Stronghold value {prof['value']}, Walls {prof['walls']}, Surrender dice {prof['surrender_dice']}"
                   + (", Gardens" if info.get("gardens") else ""))
    bits = []
    if st.conquered_side:
        bits.append(f"{st.conquered_side} Conquered x{st.conquered_count}")
    if st.ruins:
        bits.append("Ruins")
    if st.ravaged_side:
        bits.append(f"{st.ravaged_side} Ravaged")
    if st.siege_markers:
        bits.append(f"Siege x{st.siege_markers}")
    if st.bypass:
        bits.append("Bypass")
    if st.fort_marker:
        bits.append("Fort marker")
    if st.strategic_objective:
        bits.append("Strategic Objective")
    out.append("  Markers: " + (", ".join(bits) if bits else "-"))
    out.append("  Lords here: " + (", ".join(lords_here) if lords_here else "-"))
    return "\n".join(out)


def calendar_view(gs: GameState) -> str:
    rows = []
    for box in range(1, 13):
        ready = [sd.lord(lid)["name"] for lid, l in gs.lords.items()
                 if not l.mustered and l.cylinder == "calendar" and l.cylinder_calendar_box == box]
        svc = [sd.lord(lid)["name"] for lid, l in gs.lords.items() if l.mustered and l.service_box == box]
        tags = []
        if box == gs.meta.calendar_box:
            tags.append(f"<-- {gs.meta.phase}")
        unity = gs.meta.seljuk_unity_targets.get(str(box))
        if unity:
            tags.append(f"Seljuk Unity {unity}")
        line = f"  box {box:2d} {_box_label(box):12s}"
        if ready:
            line += "  Ready: " + ", ".join(ready)
        if svc:
            line += "  Service: " + ", ".join(svc)
        if tags:
            line += "  " + " ".join(tags)
        rows.append(line)
    return "Calendar:\n" + "\n".join(rows)


def thema_view(gs: GameState) -> str:
    out = ["Thema boxes (Garrison reserves):"]
    for thema, markers in gs.themata.items():
        cells = ", ".join(f"{m.unit}x{m.symbols}" for m in markers) if markers else "(empty)"
        out.append(f"  {thema}: {cells}")
    return "\n".join(out)
