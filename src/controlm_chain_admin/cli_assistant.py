"""``ctmchain menu``, ``ctmchain mcp`` and ``ctmchain kilo init``: asking in plain words.

Part of the command-line adapter (see :mod:`controlm_chain_admin.cli`); the same exit codes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.capabilities import load_catalogue, render_menu
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.kilo import (
    AGENT,
    VOCABULARY_FILE,
    kilo_files,
    project_dir,
    write_files,
)
from controlm_chain_admin.core.repo import load_repo

EXIT_OK = 0  # the codes of cli.py
EXIT_USAGE = 2
KILO_USAGE = "usage: ctmchain kilo init [--repo DIR] [--dir DIR] [--force]"


def add_commands(commands: Any) -> None:
    """Register the commands on the ``ctmchain`` subparsers."""
    menu = commands.add_parser("menu", help="what can be asked in plain words, and how")
    menu.add_argument("capability", nargs="?", help="one capability in detail")
    menu.add_argument("--format", choices=("text", "json"), default="text")
    menu.set_defaults(func=cmd_menu)

    mcp = commands.add_parser(
        "mcp", help="serve the repository to an assistant over MCP (stdio; the [mcp] extra)"
    )
    _repo_option(mcp)
    mcp.set_defaults(func=cmd_mcp)

    kilo = commands.add_parser("kilo", help="set Kilo up to work on this repository")
    kilo.set_defaults(func=cmd_kilo_help)
    kilo_commands = kilo.add_subparsers(dest="kilo_command", metavar="<command>")
    init = kilo_commands.add_parser(
        "init", help="write .kilo/: the ctmchain MCP server, the controlm agent, the skill"
    )
    _repo_option(init)
    init.add_argument(
        "--dir", type=Path, help="where Kilo is opened (default: the top of the git repository)"
    )
    init.add_argument("--force", action="store_true", help="rewrite the files that are there")
    init.set_defaults(func=cmd_kilo_init)


def _repo_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )


def cmd_menu(args: argparse.Namespace) -> int:
    catalogue = load_catalogue()
    if args.format == "json":
        data = catalogue.to_json()
        if args.capability:
            data = catalogue.get(args.capability).to_json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return EXIT_OK
    print(render_menu(catalogue, args.capability), end="")
    return EXIT_OK


def cmd_mcp(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    try:
        from controlm_chain_admin.mcpserver import run
    except ImportError as exc:
        raise ChainError(
            "the MCP server needs the [mcp] extra: pip install 'controlm-chain-admin[mcp]'"
        ) from exc
    run(repo.root)  # pragma: no cover - serves stdin until the client goes
    return EXIT_OK  # pragma: no cover


def cmd_kilo_help(args: argparse.Namespace) -> int:
    print(KILO_USAGE)
    return EXIT_USAGE


def cmd_kilo_init(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    target = (args.dir or project_dir(repo.root)).resolve()
    files = kilo_files(repo.root, sys.executable)
    for written in write_files(target, files, force=args.force):
        note = ""
        if written.action == "kept":
            vocabulary = written.path == VOCABULARY_FILE
            note = " (the team's words: kept)" if vocabulary else " (--force rewrites it)"
        print(f"{written.action} {written.path}{note}")
    print(f"Kilo project: {target}")
    print(f"Open Kilo there with the agent: kilo --agent {AGENT}")
    print("Changes are asked before they are written (ctmchain_apply: ask in .kilo/kilo.json).")
    return EXIT_OK
