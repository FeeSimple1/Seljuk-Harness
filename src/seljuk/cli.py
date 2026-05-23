"""Command-line interface for the Seljuk harness.

Wraps the LLM-consumer API (``LLMSession``) so a person — or another agent —
can drive a whole game against a save file:

    seljuk new <scenario> --out game.json     # start a game
    seljuk briefing --file game.json          # human-readable situation report
    seljuk state    --file game.json --side seljuk --json   # machine-readable, hidden-info-filtered
    seljuk legal-moves --file game.json        # the palette of legal actions (JSON)
    seljuk do  --file game.json --action '{"type": "pass_step"}'   # apply + save
    seljuk pending --file game.json            # owed sub-decisions
    seljuk history --file game.json --n 10     # recent actions

See LLM_PLAY_GUIDE.md for the full turn loop and the two-chat protocol.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, render, scenarios
from .state import GameState, IllegalAction
from .llm import LLMSession, view


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seljuk", description="Seljuk rules harness.")
    parser.add_argument("--version", action="version", version=f"seljuk {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_new = sub.add_parser("new", help="Initialize a state file from a scenario.")
    p_new.add_argument("scenario", choices=scenarios.SCENARIOS)
    p_new.add_argument("--seed", type=int, default=1)
    p_new.add_argument("--out", type=str, default="game.state.json")

    p_state = sub.add_parser("state", help="Render current state (human) or dump filtered JSON.")
    p_state.add_argument("--file", type=str, default="game.state.json")
    p_state.add_argument("--mode", choices=["summary", "verbose"], default="summary")
    p_state.add_argument("--lord", type=str, help="Focused view of one Lord.")
    p_state.add_argument("--locale", type=str, help="Focused view of one Locale.")
    p_state.add_argument("--calendar", action="store_true", help="Calendar view.")
    p_state.add_argument("--themata", action="store_true", help="Thema-box view.")
    p_state.add_argument("--side", choices=["seljuk", "roman"],
                         help="Hidden-info-filtered view for this side (use with --json).")
    p_state.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    p_brief = sub.add_parser("briefing", help="Human-readable situation report for the active side.")
    p_brief.add_argument("--file", type=str, default="game.state.json")

    p_legal = sub.add_parser("legal-moves", help="Enumerate the active side's legal actions (JSON).")
    p_legal.add_argument("--file", type=str, default="game.state.json")
    p_legal.add_argument("--validate", action="store_true",
                         help="Probe each candidate and drop handler-rejected moves (Nevsky advisory §2)")

    p_do = sub.add_parser("do", help="Apply a submitted action and save the result.")
    p_do.add_argument("--file", type=str, default="game.state.json")
    p_do.add_argument("--action", type=str, required=True, help="Action as a JSON object.")

    p_pend = sub.add_parser("pending", help="Show pending sub-decisions owed before play continues.")
    p_pend.add_argument("--file", type=str, default="game.state.json")

    p_hist = sub.add_parser("history", help="Show the last N applied actions.")
    p_hist.add_argument("--file", type=str, default="game.state.json")
    p_hist.add_argument("--n", type=int, default=10)
    return parser


def _load(path: str) -> GameState:
    return GameState.from_json(Path(path).read_text(encoding="utf-8"))


def _load_session(path: str) -> LLMSession:
    s = LLMSession.load(path)
    s.ensure_phase_started()
    return s


def _terminal_line(s: LLMSession) -> str:
    if s.is_over():
        return f"GAME OVER - winner: {s.winner()}"
    m = s.gs.meta
    return (f"phase={m.phase}/{m.subphase}  active={m.active_player}  "
            f"actions_left={m.actions_remaining}  box={m.calendar_box}/{m.final_box}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "new":
        gs = scenarios.load_scenario(args.scenario, seed=args.seed)
        Path(args.out).write_text(gs.to_json(), encoding="utf-8")
        print(f"Initialized '{args.scenario}' (seed {args.seed}) -> {args.out}")
        print()
        print(render.summary(gs))
        return 0

    file = getattr(args, "file", None)
    try:
        if args.command == "state":
            gs = _load(file)
            if args.json:
                print(json.dumps(view.filtered_state(gs, args.side or gs.meta.active_player), indent=2))
            elif args.lord:
                print(render.lord_view(gs, args.lord))
            elif args.locale:
                print(render.locale_view(gs, args.locale))
            elif args.calendar:
                print(render.calendar_view(gs))
            elif args.themata:
                print(render.thema_view(gs))
            elif args.mode == "verbose":
                print(render.verbose(gs))
            else:
                print(render.summary(gs))
            return 0

        if args.command == "briefing":
            s = _load_session(file)
            print(s.briefing())
            print()
            print(_terminal_line(s))
            return 0

        if args.command == "legal-moves":
            s = _load_session(file)
            if getattr(args, "validate", False):
                moves = s.legal_actions(validated=True)
                print(json.dumps(moves, indent=2))
                note = f"{len(moves)} legal action(s)"
                if s.palette_diagnostics:
                    note += f"; dropped {len(s.palette_diagnostics)} over-enumerated"
                    print("DROPPED (over-enumeration diagnostics):", file=sys.stderr)
                    for d in s.palette_diagnostics:
                        print(f"  {d['action']} -> {d['code']}: {d['reason']}", file=sys.stderr)
                print(f"\n{note}.  {_terminal_line(s)}", file=sys.stderr)
                return 0
            moves = s.legal_actions()
            print(json.dumps(moves, indent=2))
            print(f"\n{len(moves)} legal action(s).  {_terminal_line(s)}", file=sys.stderr)
            return 0

        if args.command == "do":
            s = _load_session(file)
            try:
                action = json.loads(args.action)
            except json.JSONDecodeError as e:
                print(f"--action is not valid JSON: {e}", file=sys.stderr)
                return 2
            try:
                result = s.apply(action)
            except IllegalAction as e:
                print(f"IllegalAction: {e}", file=sys.stderr)
                return 1
            s.save(file)
            print(json.dumps(result, indent=2))
            print(f"\n{_terminal_line(s)}", file=sys.stderr)
            return 0

        if args.command == "pending":
            s = _load_session(file)
            print(json.dumps(s.pending(), indent=2))
            return 0

        if args.command == "history":
            gs = _load(file)
            for h in gs.history[-args.n:]:
                print(json.dumps(h.get("action", h)))
            return 0
    except FileNotFoundError:
        print(f"No state file at {file}; run 'seljuk new <scenario>' first.", file=sys.stderr)
        return 1

    print(f"seljuk {__version__}: unknown command '{args.command}'.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
