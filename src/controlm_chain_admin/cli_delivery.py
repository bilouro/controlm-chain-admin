"""``ctmchain delivery``: items kept under a name, and one import file from several of them.

Part of the command-line adapter (see :mod:`controlm_chain_admin.cli`); the same exit codes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from controlm_chain_admin.core import deliveries as deliveries_mod
from controlm_chain_admin.core.package import save
from controlm_chain_admin.core.repo import load_repo

EXIT_OK = 0  # the codes of cli.py


def add_commands(commands: Any) -> None:
    """Register the command on the ``ctmchain`` subparsers."""
    parser = commands.add_parser(
        "delivery",
        help="keep items for later under a name, and make one import file from several",
    )
    actions = parser.add_subparsers(dest="delivery_command", required=True)

    def action(name: str, func: Any, text: str) -> argparse.ArgumentParser:
        sub: argparse.ArgumentParser = actions.add_parser(name, help=text)
        sub.add_argument("--format", choices=("text", "json"), default="text")
        sub.add_argument(
            "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
        )
        sub.set_defaults(func=func)
        return sub

    keep = action("save", cmd_save, "keep items of a branch under a name")
    keep.add_argument("name")
    keep.add_argument("head", help="the branch (tag, commit) the items come from")
    keep.add_argument(
        "--item", action="append", default=[], metavar="ID", required=True,
        help="job:F/J, attr:F/J@NAME, var:F/J@%%%%NAME, folder:F ... (repeatable); "
        "ctmchain take HEAD --list gives the ids of what differs",
    )  # fmt: skip
    keep.add_argument("--base", help="the ref the items were chosen against (a comparison)")
    keep.add_argument("--prefer", action="append", default=[], metavar="ENTRY")
    keep.add_argument("--note", default="", help="what it is for")
    action("list", cmd_list, "the deliveries kept")
    remove = action("remove", cmd_remove, "forget one delivery")
    remove.add_argument("name")
    package = action(
        "package", cmd_package, "the import file of a target with one or several deliveries"
    )
    package.add_argument("target", help="the branch that receives: main, env/bench ...")
    package.add_argument("names", nargs="+", metavar="NAME")
    package.add_argument("--env", help="the environment, where the branches do not tell it")
    package.add_argument("-o", "--output", type=Path, help="the file to write")
    package.add_argument("--dry-run", action="store_true", help="say what it holds, write none")


def _dump(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_save(args: argparse.Namespace) -> int:
    kept = deliveries_mod.save_delivery(
        load_repo(args.repo), args.name, args.head, args.item, base=args.base,
        prefer=args.prefer, note=args.note,
    )  # fmt: skip
    if args.format == "json":
        _dump(kept.to_json())
    else:
        print(f"Kept {kept.name!r}: {len(kept.items)} item(s) of {kept.head} ({kept.sha[:7]})")
    return EXIT_OK


def cmd_list(args: argparse.Namespace) -> int:
    rows = deliveries_mod.listed(load_repo(args.repo))
    if args.format == "json":
        _dump({"deliveries": rows})
        return EXIT_OK
    if not rows:
        print("No delivery is kept.")
        return EXIT_OK
    for row in rows:
        moved = "  (its branch moved since)" if row["moved"] else ""
        origin = f"{row['head']} ({row['environment'] or 'no environment'}, {row['sha'][:7]})"
        print(f"  {row['name']}  {row['count']} item(s) of {origin}  {row['saved']}{moved}")
        if row["note"]:
            print(f"      {row['note']}")
        for commit in row["commits"]:
            print(f"      commit {_commit(commit)}")
        for commit in row["commits_after"]:
            print(f"      after it was kept, not in it: {_commit(commit)}")
    return EXIT_OK


def _commit(commit: dict[str, str]) -> str:
    return f"{commit['sha'][:7]} {commit['subject']} ({commit['date'][:10]}, {commit['author']})"


def cmd_remove(args: argparse.Namespace) -> int:
    left = deliveries_mod.remove_delivery(load_repo(args.repo), args.name)
    if args.format == "json":
        _dump({"deliveries": [delivery.to_json() for delivery in left]})
    else:
        print(f"{args.name!r} removed; {len(left)} kept.")
    return EXIT_OK


def cmd_package(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    package = deliveries_mod.build_delivery(repo.root, args.target, args.names, env=args.env)
    report = sys.stderr if args.format == "json" else sys.stdout
    if args.format == "json":
        _dump(package.to_json())
    else:
        print(
            f"Deliveries {', '.join(args.names)} for {package.env} ({args.target}): "
            f"{len(package.folders)} folder(s), {len(package.taken or ())} item(s)"
        )
        for folder in package.folders:
            print(f"  {folder.name} ({folder.jobs} job(s)): {'; '.join(folder.reasons)}")
        for warning in package.warnings:
            print(f"warning: {warning}")
    if package.xml is None:
        print("Nothing to package.", file=report)
    elif args.dry_run:
        print(f"Dry run: {package.filename} not written.", file=report)
    else:
        path = save(package, args.output or Path(package.filename))
        print(f"Wrote {path} ({package.size} bytes)", file=report)
    return EXIT_OK
