"""``ctmchain`` command-line entry point (thin adapter over :mod:`controlm_chain_admin.core`).

The CLI only parses arguments, calls one core operation, renders its result and maps typed
errors to exit codes: 0 success, 1 findings reported, 2 usage error, 3 error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from controlm_chain_admin import __version__
from controlm_chain_admin.core import ops
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.repo import init_repo, load_repo

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_ERROR = 3

DESCRIPTION = (
    "Manage BMC Control-M job chains as a git-friendly JSON repository: import and export the "
    "Control-M XML, keep links between jobs explicit, validate chains and refactor safely."
)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def build_parser() -> argparse.ArgumentParser:
    """Build the parser with every subcommand."""
    parser = argparse.ArgumentParser(prog="ctmchain", description=DESCRIPTION)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    init = commands.add_parser("init", help="turn an existing directory into a chain repository")
    init.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    init.add_argument(
        "--application", required=True, help="Control-M APPLICATION managed by this repo"
    )
    init.add_argument(
        "--envs", required=True, help="comma-separated environments, e.g. test,uat,bench,prod"
    )
    init.set_defaults(func=cmd_init)

    imp = commands.add_parser("import", help="import a Control-M XML export into the repository")
    imp.add_argument("xml", type=Path, help="Control-M export (DEFTABLE XML)")
    imp.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    imp.add_argument("--format", choices=("text", "json"), default="text", help="report format")
    imp.set_defaults(func=cmd_import)

    exp = commands.add_parser("export", help="regenerate the Control-M XML from the repository")
    exp.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    exp.add_argument("-o", "--output", type=Path, required=True, help="XML file to write")
    exp.set_defaults(func=cmd_export)
    return parser


# ---------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> int:
    environments = [e.strip() for e in args.envs.split(",") if e.strip()]
    if not environments:
        raise ChainError("--envs needs at least one environment name")
    repo = init_repo(args.repo, args.application, environments)
    print(
        f"Initialized chain repository at {repo.root} for application {repo.config.application} "
        f"with environments {', '.join(repo.config.environments)}"
    )
    return EXIT_OK


def cmd_import(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    report = ops.import_xml(repo, args.xml.read_bytes())
    if args.format == "json":
        print(json.dumps(report.to_json(), indent=2, ensure_ascii=False))
        return EXIT_OK
    print(
        f"Imported {_plural(len(report.folders), 'folder')}, {_plural(report.jobs, 'job')} "
        f"(application {report.application}); {_plural(report.files_written, 'file')} written."
    )
    if report.skipped:
        names = ", ".join(f"{s.folder} ({s.application})" for s in report.skipped)
        print(f"Skipped {_plural(len(report.skipped), 'folder')} of other applications: {names}")
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    data = ops.export_xml(repo)
    args.output.write_bytes(data)
    print(f"Wrote {args.output} ({len(data)} bytes)")
    return EXIT_OK


# ---------------------------------------------------------------- entry point


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and dispatch to one core operation. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        result: int = args.func(args)
    except ChainError as exc:
        print(f"ctmchain: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"ctmchain: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return result
