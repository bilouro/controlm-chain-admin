"""``ctmchain refresh`` and ``ctmchain envmap``: one branch per environment, and the map of
what varies between them.

Part of the command-line adapter (see :mod:`controlm_chain_admin.cli`); the same exit codes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from controlm_chain_admin.core import envmap as envmap_mod
from controlm_chain_admin.core import mapcheck as mapcheck_mod
from controlm_chain_admin.core import refactor as refactor_mod
from controlm_chain_admin.core import refresh as refresh_mod
from controlm_chain_admin.core.environments import env_branches
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.core.workspace import ensure_editable

EXIT_OK = 0  # the codes of cli.py


def _repo_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )


def add_commands(commands: Any) -> None:
    """Register the commands on the ``ctmchain`` subparsers."""
    ref = commands.add_parser(
        "refresh",
        help="overwrite the branch of an environment with its full export, after showing "
        "what differs",
    )
    ref.add_argument("xml", type=Path, help="the full export of one environment")
    ref.add_argument("--env", help="the environment (default: read from the letter of the names)")
    ref.add_argument(
        "--apply",
        action="store_true",
        help="check the branch out (created from the trunk when missing), overwrite it and "
        "commit; without it nothing is written",
    )
    ref.add_argument(
        "--no-commit", action="store_true", help="with --apply: leave the result uncommitted"
    )
    ref.add_argument(
        "--here",
        action="store_true",
        help="onto the checked-out branch, not the environment's: a branch of your own, "
        "started from an environment's, that can then be compared with it",
    )
    ref.add_argument(
        "--partial",
        action="store_true",
        help="with --here: the export holds some folders only; the others stay",
    )
    ref.add_argument("--stat", action="store_true", help="counts only, not every difference")
    ref.add_argument("--format", choices=("text", "json"), default="text")
    _repo_option(ref)
    ref.set_defaults(func=cmd_refresh)
    _add_envmap(commands)


def _add_envmap(commands: Any) -> None:
    parser = commands.add_parser(
        "envmap",
        help="the map of what varies per environment (machines, users, datacenters): "
        "kept on its own branch, derived from the environments' branches",
    )
    actions = parser.add_subparsers(dest="envmap_command", required=True)

    def action(name: str, func: Any, text: str) -> argparse.ArgumentParser:
        sub: argparse.ArgumentParser = actions.add_parser(name, help=text)
        sub.add_argument("--format", choices=("text", "json"), default="text")
        _repo_option(sub)
        sub.set_defaults(func=func)
        return sub

    action("show", cmd_envmap_show, "the letters and the entries of the map")
    action("suggest", cmd_envmap_suggest, "what else varies between the branches, with counts")
    derive = action("derive", cmd_envmap_derive, "the entries the branches show and the map lacks")
    derive.add_argument(
        "--key", action="append", default=[], metavar="SPEC",
        help="one more attribute whose whole value varies (ATTR, TAG/@ATTR, TAG[K=V]/@ATTR); "
        f"{', '.join(envmap_mod.DEFAULT_KEYS)} are always looked at",
    )  # fmt: skip
    derive.add_argument(
        "--text", action="append", default=[], metavar="SPEC",
        help="an attribute whose texts differ in one word per environment (a mail subject)",
    )  # fmt: skip
    derive.add_argument(
        "--min-nodes", type=int, default=2, metavar="N",
        help="how many folders or jobs must show the same values for them to enter the map "
        "(default: 2; what a single job shows is its own difference)",
    )  # fmt: skip
    derive.add_argument("--apply", action="store_true", help="add the entries to the map")
    add = action("add", cmd_envmap_add, "one entry by hand")
    add.add_argument("key", metavar="KEY", help="ATTR, TAG/@ATTR or TAG[K=V]/@ATTR")
    add.add_argument("values", nargs="+", metavar="ENV=VALUE")
    add.add_argument("--text", action="store_true", help="a word inside a text, not the value")
    add.add_argument("--as", dest="name", help="the name of the entry (default: key.N)")
    remove = action("remove", cmd_envmap_remove, "drop one entry")
    remove.add_argument("name")
    rename = action("rename", cmd_envmap_rename, "give an entry a name that says what it is")
    rename.add_argument("old")
    rename.add_argument("new")
    action("followers", cmd_envmap_followers, "how many places follow each entry")
    follow = action(
        "follow", cmd_envmap_follow,
        "make the jobs that follow one entry follow another, on the branch checked out",
    )  # fmt: skip
    follow.add_argument("entry", help="the entry the jobs follow now")
    follow.add_argument("other", help="the entry of the same key they should follow")
    follow.add_argument("--apply", action="store_true", help="write the change (default: preview)")
    follow.add_argument("--stat", action="store_true", help="list the files, not the diff")


def cmd_refresh(args: argparse.Namespace) -> int:
    result = refresh_mod.refresh(
        load_repo(args.repo),
        args.xml.read_bytes(),
        source=args.xml.name,
        env=args.env,
        apply=args.apply,
        commit=not args.no_commit,
        here=args.here,
        partial=args.partial,
    )
    if args.format == "json":
        print(json.dumps(result.to_json(), indent=2, ensure_ascii=False))
    else:
        print(refresh_mod.render_text(result, stat=args.stat), end="")
    return EXIT_OK


# ---------------------------------------------------------------- envmap


def _values(values: dict[str, str]) -> str:
    return "  ".join(f"{env}={value}" for env, value in values.items())


def _entry_line(entry: envmap_mod.MapEntry, nodes: int | None = None) -> str:
    count = "" if nodes is None else f"  {nodes} nodes"
    word = "  (a word of the text)" if entry.inline else ""
    return f"  {entry.name}  {entry.key}{count}{word}\n      {_values(dict(entry.values))}"


def _dump(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def cmd_envmap_show(args: argparse.Namespace) -> int:
    shown = envmap_mod.show_map(load_repo(args.repo))
    if args.format == "json":
        _dump(shown)
        return EXIT_OK
    branch, entries = shown["branch"], shown["entries"]
    if entries:
        print(f"The map (branch {branch}): {_plural(len(entries), 'entry', 'entries')}")
    else:
        print(f"The map is empty (branch {branch}): ctmchain envmap derive fills it")
    print(f"  letters: {' '.join(f'{env}={letter}' for env, letter in shown['letters'].items())}")
    for entry in entries:
        print(_entry_line(envmap_mod.MapEntry.from_json(entry)))
    return EXIT_OK


def cmd_envmap_derive(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    root, config = repo.root, repo.config
    found, applied = envmap_mod.derive_map(
        repo, keys=args.key, text_keys=args.text, min_nodes=args.min_nodes, apply=args.apply
    )
    count = len(found.entries)
    if args.format == "json":
        _dump({**found.to_json(), "applied": applied})
        return EXIT_OK
    branches = env_branches(root, config)
    sources = ", ".join(f"{branches[env]} ({env})" for env in found.environments)
    if count:
        print(f"{_plural(count, 'new entry', 'new entries')} from {sources}")
        for entry in found.entries:
            print(_entry_line(entry, found.nodes.get(entry.name, 0)))
    else:
        print(f"Nothing new: the map explains what these keys show. ({sources})")
    left = len(found.left_out)
    if left:
        it = "it" if left == 1 else "them"
        print(f"  {_plural(left, 'set of values', 'sets of values')} left out: fewer than "
              f"{args.min_nodes} nodes show {it} (--min-nodes 1 takes {it})")  # fmt: skip
    branch = config.git_rules.map_branch
    if applied:
        print(f"Written on {branch}: {_plural(count, 'entry', 'entries')} added")
    elif count:
        print("Nothing written: --apply adds them to the map.")
    return EXIT_OK


def cmd_envmap_suggest(args: argparse.Namespace) -> int:
    found = envmap_mod.suggest_map(load_repo(args.repo))
    if args.format == "json":
        _dump({"suggestions": [item.to_json() for item in found]})
        return EXIT_OK
    if not found:
        print("Nothing else varies between the environments: the letter and the map explain it.")
        return EXIT_OK
    print("What else varies between the environments (neither the letter nor the map says why):")
    for item in found:
        sets = _plural(item.tuples, "set of values", "sets of values")
        print(f"  {item.key}  {item.nodes} nodes, {sets}")
        if item.text:
            words = _plural(item.words or 0, "word", "words")
            print(f"      the texts differ in one word ({words}): "
                  f"ctmchain envmap derive --text {item.key}")  # fmt: skip
        else:
            print(f"      ctmchain envmap derive --key '{item.key}'")
    print("A key with few sets of values is the environment's (for the map); one with a set "
          "per job is what the jobs have (a real difference).")  # fmt: skip
    return EXIT_OK


def _pairs(values: list[str]) -> dict[str, str]:
    pairs = {}
    for item in values:
        env, sep, value = item.partition("=")
        if not sep or not env:
            raise ChainError(f"{item!r}: give each value as env=value")
        pairs[env] = value
    return pairs


def _written(args: argparse.Namespace, envmap: envmap_mod.EnvMap, done: str) -> int:
    if args.format == "json":
        _dump(envmap.to_json())
    else:
        branch = load_repo(args.repo).config.git_rules.map_branch
        print(f"Written on {branch}: {done}")
    return EXIT_OK


def cmd_envmap_add(args: argparse.Namespace) -> int:
    envmap, name = envmap_mod.add_to_map(
        load_repo(args.repo), args.key, _pairs(args.values), name=args.name, inline=args.text
    )
    return _written(args, envmap, name)


def cmd_envmap_remove(args: argparse.Namespace) -> int:
    envmap = envmap_mod.remove_from_map(load_repo(args.repo), args.name)
    return _written(args, envmap, f"{args.name} removed")


def cmd_envmap_followers(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    seen = mapcheck_mod.survey(repo.root)
    counts = seen.counts()
    if args.format == "json":
        _dump(seen.to_json())
        return EXIT_OK
    for entry in envmap_mod.read_map(repo.root, repo.config).entries:
        print(f"  {entry.name}  {counts.get(entry.name, 0)} place(s)  {entry.key}")
    print(f"{len(seen.unmapped)} place(s) of these keys follow no entry (ctmchain validate).")
    return EXIT_OK


def cmd_envmap_follow(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    if args.apply:
        ensure_editable(repo)
    change = mapcheck_mod.follow_entry(repo, args.entry, args.other)
    applied = refactor_mod.apply(repo, change) if args.apply and change.edits else None
    if args.format == "json":
        _dump({**change.to_json(), "applied": applied is not None})
        return EXIT_OK
    print(change.summary)
    for warning in change.warnings:
        print(f"warning: {warning}")
    if not change.edits:
        print("Nothing to change.")
        return EXIT_OK
    print(change.stat() if args.stat else change.diff(), end="")
    if applied is not None:
        print(f"Applied: {applied.written} written, {applied.deleted} deleted")
    else:
        print("Preview only; re-run with --apply to write.")
    return EXIT_OK


def cmd_envmap_rename(args: argparse.Namespace) -> int:
    envmap = envmap_mod.rename_in_map(load_repo(args.repo), args.old, args.new)
    return _written(args, envmap, f"{args.old} is now {args.new}")
