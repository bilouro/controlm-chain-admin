"""``ctmchain refresh`` and ``ctmchain envmap``: one branch per environment, and the map of
what varies between them.

Part of the command-line adapter (see :mod:`controlm_chain_admin.cli`); the same exit codes.
"""

from __future__ import annotations

import argparse
import json
import sys
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
EXIT_USAGE = 2


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
        help="the export holds some folders only (a package imported into the environment): "
        "its folders replace the branch's, the others stay",
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
        "make the jobs that follow one entry follow another, in every environment where the "
        "two differ (one commit on the branch of each; production gets an import file)",
    )  # fmt: skip
    follow.add_argument("entry", help="the entry the jobs follow now")
    follow.add_argument("other", help="the entry of the same key they should follow")
    follow.add_argument(
        "--apply", action="store_true", help="commit on each branch (default: preview)"
    )
    follow.add_argument(
        "--here", action="store_true",
        help="on the branch checked out only, left to review and commit",
    )  # fmt: skip
    follow.add_argument("--stat", action="store_true", help="with --here: the files, not the diff")
    action(
        "new-values", cmd_envmap_new_values,
        "the values the branch checked out has and no entry of the map has for its environment "
        "(after a refresh: a user renamed, a machine replaced)",
    )  # fmt: skip
    adopt = action(
        "adopt", cmd_envmap_adopt,
        "put a new value of the branch checked out into an entry, or into a new one",
    )  # fmt: skip
    adopt.add_argument("key", help="the key, as new-values lists it (RUN_AS, DOMAIL/@SUBJECT)")
    adopt.add_argument("value", help="the new value (for a word inside a text: the word)")
    into = adopt.add_mutually_exclusive_group(required=True)
    into.add_argument("--entry", help="the entry that gets it, instead of its value there")
    into.add_argument(
        "--new", action="store_true", help="a new entry; the other environments to fill"
    )
    adopt.add_argument("--text", action="store_true", help="a word inside a text")
    setter = action("set", cmd_envmap_set, "the value of one environment in an entry")
    setter.add_argument("name", help="the entry")
    setter.add_argument("env", help="the environment")
    setter.add_argument("value", nargs="?", help="its value")
    setter.add_argument("--clear", action="store_true", help="leave it to fill")


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
    if not args.here:
        return _follow_everywhere(args)
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


def cmd_envmap_new_values(args: argparse.Namespace) -> int:
    env, found = mapcheck_mod.new_values(load_repo(args.repo))
    if args.format == "json":
        _dump({"env": env, "new_values": [new.to_json() for new in found]})
        return EXIT_OK
    if env is None:
        print("The branch checked out holds no environment: nothing to look for.")
        return EXIT_OK
    if not found:
        print(f"No new value: every value of {env} is in the map.")
        return EXIT_OK
    for new in found:
        word = " (a word inside the text)" if new.inline else ""
        hint = f"suggested: {new.suggested}" if new.suggested else "no entry fits: --new"
        print(f"  {new.key} {new.value}{word}  {new.places} place(s)  {hint}")
        print(f"      e.g. {', '.join(new.nodes)}")
    print(
        f"ctmchain envmap adopt KEY VALUE --entry NAME puts one into an entry of {env}; --new "
        "makes a new entry, the other environments to fill (ctmchain envmap set)."
    )
    return EXIT_OK


def cmd_envmap_adopt(args: argparse.Namespace) -> int:
    done = mapcheck_mod.adopt_value(
        load_repo(args.repo), args.key, args.value,
        entry=None if args.new else args.entry, inline=args.text,
    )  # fmt: skip
    if args.format == "json":
        _dump(done)
        return EXIT_OK
    was = done["old"] if done["old"] is not None else "nothing"
    print(f"{done['entry']}: {done['env']} {was} -> {done['new']}")
    if done["to_fill"]:
        print(f"  to fill: {', '.join(done['to_fill'])} (ctmchain envmap set)")
    if done["left"]:
        print(f"  warning: {done['left']} place(s) of {done['env']} still have {was}, now "
              "in no entry")  # fmt: skip
    return EXIT_OK


def cmd_envmap_set(args: argparse.Namespace) -> int:
    if args.clear == (args.value is not None):
        print("give the value, or --clear to leave it to fill", file=sys.stderr)
        return EXIT_USAGE
    envmap = mapcheck_mod.set_entry_value(
        load_repo(args.repo), args.name, args.env, None if args.clear else args.value
    )
    said = "to fill" if args.clear else args.value
    return _written(args, envmap, f"{args.name}: {args.env} {said}")


def _follow_everywhere(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    if args.apply:
        done = mapcheck_mod.apply_follow_everywhere(repo, args.entry, args.other)
        if args.format == "json":
            _dump({"follows": done})
            return EXIT_OK
        for row in done:
            if row["commit"]:
                print(f"Committed on {row['branch']}: follow({row['env']}): {args.entry} -> "
                      f"{args.other} ({row['places']} place(s))")  # fmt: skip
            elif row["protected"] and row["places"]:
                print(f"{row['env']} ({row['branch']}): not edited here; production gets "
                      "the change with an import file (Compare, package)")  # fmt: skip
        return EXIT_OK
    plan = mapcheck_mod.follow_everywhere(repo, args.entry, args.other)
    if args.format == "json":
        _dump({"follows": [follow.to_json() for follow in plan]})
        return EXIT_OK
    for follow in plan:
        note = " (not edited here: production gets an import file)" if follow.protected else ""
        print(f"  {follow.env} ({follow.branch}): {follow.places} place(s), {follow.key} "
              f"{follow.old} -> {follow.new}{note}")  # fmt: skip
    print("Preview only: --apply commits on the branch of each environment.")
    return EXIT_OK


def cmd_envmap_rename(args: argparse.Namespace) -> int:
    envmap = envmap_mod.rename_in_map(load_repo(args.repo), args.old, args.new)
    return _written(args, envmap, f"{args.old} is now {args.new}")
