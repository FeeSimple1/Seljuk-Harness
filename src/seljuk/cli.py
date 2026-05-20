"""Command-line interface for the Seljuk harness.

Wraps the library API (BRIEF.md, "LLM-Consumer Interface"). In Phase 0 the
subcommands are registered but report that they are not yet implemented; they
are filled in as the corresponding phases land. Subcommands:
``new``, ``state``, ``legal-moves``, ``do``, ``pending``, ``history``,
``save``, ``load``.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__

_SUBCOMMANDS = {
    "new": "Initialize a state file from one of the five scenarios.",
    "state": "Render current state (summary / verbose / focused).",
    "legal-moves": "Enumerate legal actions for the active player.",
    "do": "Execute a submitted JSON action.",
    "pending": "Show pending sub-decisions and who owes a response.",
    "history": "Show the last N actions and results.",
    "save": "Write the current state to a file.",
    "load": "Load state from a file.",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seljuk", description="Seljuk rules harness.")
    parser.add_argument("--version", action="version", version=f"seljuk {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, help_text in _SUBCOMMANDS.items():
        sub.add_parser(name, help=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    print(
        f"seljuk {__version__}: '{args.command}' is not implemented in Phase 0 "
        f"(skeleton). See BRIEF.md for the phase plan.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
