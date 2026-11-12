"""``ctmchain diagnose``: why a comparison is slow on this machine.

Part of the command-line adapter (see :mod:`controlm_chain_admin.cli`); the same exit codes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from controlm_chain_admin.core import diagnose as diagnose_mod

EXIT_OK = 0  # the codes of cli.py


def add_commands(commands: Any) -> None:
    """Register the command on the ``ctmchain`` subparsers."""
    diag = commands.add_parser(
        "diagnose",
        help="measure this machine and one comparison, to see why it is slow (numbers only)",
    )
    diag.add_argument(
        "base", nargs="?", help="base ref (default: the trunk, with the first other environment)"
    )
    diag.add_argument("head", nargs="?", help="head ref")
    diag.add_argument(
        "--files", type=int, default=2000, help="small files of the machine test (default: 2000)"
    )
    diag.add_argument("--format", choices=("text", "json"), default="text")
    diag.add_argument("-o", "--output", type=Path, help="write the report to this file too")
    diag.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    diag.set_defaults(func=cmd_diagnose)


def cmd_diagnose(args: argparse.Namespace) -> int:
    found = diagnose_mod.diagnose(args.repo, args.base, args.head, files=args.files)
    if args.format == "json":
        report = json.dumps(found.to_json(), indent=2) + "\n"
    else:
        report = diagnose_mod.render_text(found)
    print(report, end="")
    if args.output is not None:
        args.output.write_text(report, encoding="utf-8", newline="\n")
        print(f"Wrote {args.output}", file=sys.stderr)
    return EXIT_OK
