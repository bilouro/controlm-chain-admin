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
from controlm_chain_admin.core import refresh as refresh_mod
from controlm_chain_admin.core.environments import env_branches
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.repo import load_repo

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


def cmd_refresh(args: argparse.Namespace) -> int:
    result = refresh_mod.refresh(
        load_repo(args.repo),
        args.xml.read_bytes(),
        source=args.xml.name,
        env=args.env,
        apply=args.apply,
        commit=not args.no_commit,
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
    repo = load_repo(args.repo)
    envmap = envmap_mod.read_map(repo.root, repo.config)
    letters = repo.env_letters()
    if args.format == "json":
        _dump({"branch": repo.config.git_rules.map_branch, "letters": letters,
               **envmap.to_json()})  # fmt: skip
        return EXIT_OK
    branch = repo.config.git_rules.map_branch
    if envmap.entries:
        print(f"The map (branch {branch}): {_plural(len(envmap.entries), 'entry', 'entries')}")
    else:
        print(f"The map is empty (branch {branch}): ctmchain envmap derive fills it")
    print(f"  letters: {' '.join(f'{env}={letter}' for env, letter in letters.items())}")
    for entry in envmap.entries:
        print(_entry_line(entry))
    return EXIT_OK


def cmd_envmap_derive(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    root, config = repo.root, repo.config
    known = envmap_mod.read_map(root, config)
    keys = tuple(dict.fromkeys((*envmap_mod.DEFAULT_KEYS, *args.key)))
    found = envmap_mod.derive(root, config, known, keys=keys, text_keys=tuple(args.text),
                              min_nodes=args.min_nodes)  # fmt: skip
    count = len(found.entries)
    applied = bool(args.apply and count)
    if applied:
        message = f"map: {_plural(count, 'entry', 'entries')} derived"
        envmap_mod.write_map(root, config, found.envmap, message)
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
    repo = load_repo(args.repo)
    known = envmap_mod.read_map(repo.root, repo.config)
    found = envmap_mod.suggest(repo.root, repo.config, known)
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


def _change_map(args: argparse.Namespace, change: Any) -> int:
    """Read the map, change it (``change`` gives the new map, the commit message and what to
    say) and write it on its branch."""
    repo = load_repo(args.repo)
    envmap, message, done = change(envmap_mod.read_map(repo.root, repo.config), repo)
    envmap_mod.write_map(repo.root, repo.config, envmap, message)
    if args.format == "json":
        _dump(envmap.to_json())
    else:
        print(f"Written on {repo.config.git_rules.map_branch}: {done}")
    return EXIT_OK


def cmd_envmap_add(args: argparse.Namespace) -> int:
    values = _pairs(args.values)

    def change(envmap: envmap_mod.EnvMap, repo: Any) -> tuple[envmap_mod.EnvMap, str, str]:
        result = envmap_mod.add_entry(envmap, args.key, values, name=args.name, inline=args.text,
                                      environments=tuple(repo.config.environments))  # fmt: skip
        name = result.entries[-1].name
        return result, f"map: add {name}", name

    return _change_map(args, change)


def cmd_envmap_remove(args: argparse.Namespace) -> int:
    return _change_map(
        args,
        lambda envmap, _repo: (
            envmap_mod.remove_entry(envmap, args.name),
            f"map: remove {args.name}",
            f"{args.name} removed",
        ),
    )


def cmd_envmap_rename(args: argparse.Namespace) -> int:
    return _change_map(
        args,
        lambda envmap, _repo: (
            envmap_mod.rename_entry(envmap, args.old, args.new),
            f"map: rename {args.old} to {args.new}",
            f"{args.old} is now {args.new}",
        ),
    )
