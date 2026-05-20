"""Command-line interface for the Seljuk harness.

Wraps the library API (BRIEF.md, "LLM-Consumer Interface"). Phase 1 implements
``new`` (initialize a state file from a scenario) and ``state`` (render).
``legal-moves`` / ``do`` / ``pending`` / ``history`` are registered but report
that they arrive in later phases.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, render, scenarios
from .state import GameState


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seljuk", description="Seljuk rules harness.")
    parser.add_argument("--version", action="version", version=f"seljuk {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_new = sub.add_parser("new", help="Initialize a state file from a scenario.")
    p_new.add_argument("scenario", choices=scenarios.SCENARIOS)
    p_new.add_argument("--seed", type=int, default=1)
    p_new.add_argument("--out", type=str, default="game.state.json")

    p_state = sub.add_parser("state", help="Render current state.")
    p_state.add_argument("--file", type=str, default="game.state.json")
    p_state.add_argument("--mode", choices=["summary", "verbose"], default="summary")
    p_state.add_argument("--lord", type=str, help="Focused view of one Lord.")
    p_state.add_argument("--locale", type=str, help="Focused view of one Locale.")
    p_state.add_argument("--calendar", action="store_true", help="Calendar view.")
    p_state.add_argument("--themata", action="store_true", help="Thema-box view.")

    for name, help_text in (
        ("legal-moves", "Enumerate legal actions (Phase 2+)."),
        ("do", "Execute a submitted action (Phase 2+)."),
        ("pending", "Show pending sub-decisions (Phase 2+)."),
        ("history", "Show the last N actions (Phase 2+)."),
    ):
        sub.add_parser(name, help=help_text)
    return parser


def _load(path: str) -> GameState:
    return GameState.from_json(Path(path).read_text(encoding="utf-8"))


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

    if args.command == "state":
        try:
            gs = _load(args.file)
        except FileNotFoundError:
            print(f"No state file at {args.file}; run 'seljuk new <scenario>' first.", file=sys.stderr)
            return 1
        if args.lord:
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

    print(
        f"seljuk {__version__}: '{args.command}' is not implemented yet "
        f"(see BRIEF.md phase plan).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
