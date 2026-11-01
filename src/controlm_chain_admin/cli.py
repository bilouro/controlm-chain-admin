"""``ctmchain`` command-line entry point (thin adapter over :mod:`controlm_chain_admin.core`).

The CLI only parses arguments, calls one core operation, renders its result and maps typed
errors to exit codes: 0 success, 1 findings reported, 2 usage error, 3 unexpected error.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from controlm_chain_admin import __version__

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_ERROR = 3

DESCRIPTION = (
    "Manage BMC Control-M job chains as a git-friendly JSON repository: import and export the "
    "Control-M XML, keep links between jobs explicit, validate chains and refactor safely."
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser. Subcommands register themselves here as they are added."""
    parser = argparse.ArgumentParser(prog="ctmchain", description=DESCRIPTION)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_subparsers(dest="command", metavar="<command>")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and dispatch to one core operation. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    return EXIT_OK  # pragma: no cover - unreachable until the first subcommand exists
