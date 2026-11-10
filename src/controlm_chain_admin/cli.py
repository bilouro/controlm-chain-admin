"""``ctmchain`` command-line entry point (thin adapter over :mod:`controlm_chain_admin.core`).

The CLI only parses arguments, calls one core operation, renders its result and maps typed
errors to exit codes: 0 success, 1 findings reported, 2 usage error, 3 error.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from controlm_chain_admin import __version__, cli_assistant, cli_env
from controlm_chain_admin.core import check as check_mod
from controlm_chain_admin.core import commit as commit_mod
from controlm_chain_admin.core import compare as compare_mod
from controlm_chain_admin.core import constants as constants_mod
from controlm_chain_admin.core import environments as environments_mod
from controlm_chain_admin.core import fixes as fixes_mod
from controlm_chain_admin.core import graph as graph_mod
from controlm_chain_admin.core import guide as guide_mod
from controlm_chain_admin.core import inspect as inspect_mod
from controlm_chain_admin.core import intake as intake_mod
from controlm_chain_admin.core import ops
from controlm_chain_admin.core import package as package_mod
from controlm_chain_admin.core import refactor as refactor_mod
from controlm_chain_admin.core import take as take_mod
from controlm_chain_admin.core import workspace as workspace_mod
from controlm_chain_admin.core.errors import ChainError, NotAChainRepo, TakeConflict
from controlm_chain_admin.core.history import WORKTREE
from controlm_chain_admin.core.links import NodeRef, folder_names
from controlm_chain_admin.core.repo import init_repo, load_repo, read_json, write_json
from controlm_chain_admin.core.validate import render_markdown, render_text, validate
from controlm_chain_admin.core.xmlio import parse_xml

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
        "--envs",
        required=True,
        help="comma-separated environments with optional letter, e.g. test=T,uat=U,bench=B,prod=P",
    )
    init.add_argument(
        "--prefixes",
        default="",
        help="comma-separated bare prefixes of the letter rule, e.g. P77,RQ_,RC_ (default: none)",
    )
    init.add_argument(
        "--leading-only",
        default="",
        help="prefixes whose names carry the letter on the first token only, e.g. RQ_,RC_ "
        "(resources such as URQ_P77_X)",
    )
    init.add_argument(
        "--dedupe-jobnames",
        action="store_true",
        help="every import and refresh gives a JOBNAME repeated in its folder a numeric suffix "
        "(X, X2, X3); package and export give the original names back",
    )
    init.set_defaults(func=cmd_init)

    imp = commands.add_parser("import", help="import a Control-M XML export into the repository")
    imp.add_argument("xml", type=Path, help="Control-M export (DEFTABLE XML)")
    imp.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    imp.add_argument(
        "--env", help="environment the export comes from (needed with the letter rule)"
    )
    imp.add_argument(
        "--mappings",
        type=Path,
        help="mapping draft (from distinct --write) to apply before importing",
    )
    imp.add_argument(
        "--dedupe-jobnames",
        action="store_true",
        help="give repeated JOBNAMEs a numeric suffix (X, X2, X3); kept as the repo policy",
    )
    imp.add_argument("--format", choices=("text", "json"), default="text", help="report format")
    imp.set_defaults(func=cmd_import)

    exp = commands.add_parser("export", help="regenerate the Control-M XML from the repository")
    exp.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    exp.add_argument("--env", help="target environment (needed with the letter rule)")
    exp.add_argument(
        "--jobnames",
        choices=("original", "deduped"),
        default="original",
        help="JOBNAMEs as in Control-M (default) or as stored after deduplication",
    )
    exp.add_argument(
        "--names",
        choices=("original", "standard"),
        default="original",
        help="condition names: as imported (default) or derived from the endpoints",
    )
    exp.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="leave @{name} placeholders without a value in the XML instead of failing",
    )
    exp.add_argument("-o", "--output", type=Path, required=True, help="XML file to write")
    exp.set_defaults(func=cmd_export)

    val = commands.add_parser(
        "validate", help="check links, names and duplicates; exit 1 on findings"
    )
    val.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    val.add_argument(
        "--format", choices=("text", "md", "json"), default="text", help="report format"
    )
    val.add_argument("--strict", action="store_true", help="exit 1 on info findings too")
    val.set_defaults(func=cmd_validate)

    dis = commands.add_parser(
        "distinct", help="distinct values of attributes, with counts and sample nodes"
    )
    dis.add_argument(
        "specs", nargs="+", metavar="ATTR|TAG/@ATTR", help="e.g. NODEID RUN_AS DOMAIL/@DEST"
    )
    dis.add_argument("--xml", type=Path, help="read a Control-M export instead of the repository")
    dis.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    dis.add_argument("--format", choices=("text", "json"), default="text")
    dis.add_argument("--env", help="environment the values come from (prefills the draft)")
    dis.add_argument("--write", type=Path, help="write a mapping draft to this JSON file")
    dis.set_defaults(func=cmd_distinct)

    show = commands.add_parser("show", help="print one node (FOLDER/JOB or FOLDER/) as JSON")
    show.add_argument("node")
    show.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    show.add_argument(
        "--env", help="as this environment has it: its exception, its values of the constants"
    )
    show.set_defaults(func=cmd_show)

    gr = commands.add_parser("graph", help="chain graph of one folder")
    gr.add_argument("folder")
    gr.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    gr.add_argument("--env", help="without the jobs this environment does not have")
    gr.add_argument("--format", choices=("text", "mermaid", "dot", "json"), default="text")
    gr.set_defaults(func=cmd_graph)

    ln = commands.add_parser(
        "links", help="links of a node, or the link with a given condition name"
    )
    ln.add_argument("node", nargs="?", help="FOLDER/JOB or FOLDER/")
    ln.add_argument("--name", help="condition name")
    ln.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    ln.add_argument("--format", choices=("text", "json"), default="text")
    ln.set_defaults(func=cmd_links)

    mp = commands.add_parser(
        "map", help="bind a value to a constant with one value per environment"
    )
    mp.add_argument("spec", metavar="ATTR|TAG/@ATTR", help="e.g. NODEID or DOMAIL/@DEST")
    mp.add_argument("value", help="the value as seen in the export")
    mp.add_argument("--as", dest="name", required=True, help="constant name, e.g. node.batch")
    mp.add_argument("--pattern", help="template with {L}/{l} for the letter, e.g. {L}P77_BATCH")
    mp.add_argument(
        "--value",
        dest="values",
        action="append",
        default=[],
        metavar="ENV=VALUE",
        help="explicit value for one environment (repeatable)",
    )
    mp.add_argument("--env", help="environment the given value belongs to")
    mp.add_argument("--inline", action="store_true", help="the value is a token inside free text")
    mp.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    mp.set_defaults(func=cmd_map)

    envp = commands.add_parser("env", help="environment helpers")
    env_sub = envp.add_subparsers(dest="env_command", metavar="<subcommand>")
    envc = env_sub.add_parser(
        "constants", help="constants table; --missing lists the gaps and exits 1"
    )
    envc.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    envc.add_argument("--env", help="only this environment")
    envc.add_argument("--missing", action="store_true", help="only constants without a value")
    envc.add_argument("--format", choices=("text", "json"), default="text")
    envc.set_defaults(func=cmd_env_constants)
    envl = env_sub.add_parser(
        "learn", help="the values of the constants in an environment, from one of its exports"
    )
    envl.add_argument("xml", type=Path, help="an export of that environment")
    envl.add_argument("--env", help="the environment (default: told by the letter of the names)")
    envl.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="PREFIX",
        help="only the constants whose name starts with it, e.g. user. (repeatable)",
    )
    _refactor_options(envl)
    envl.set_defaults(func=cmd_env_learn)
    envp.set_defaults(func=cmd_env_help)

    rec = commands.add_parser(
        "receive",
        help="take an export of one environment (some folders, e.g. a delivery) into the release",
    )
    rec.add_argument("xml", type=Path, help="the export")
    rec.add_argument("--env", help="its environment (default: told by the letter of the names)")
    scope = rec.add_mutually_exclusive_group()
    scope.add_argument(
        "--full",
        action="store_const",
        const=True,
        dest="full",
        help="every folder of the environment (default: when it has more than half of them)",
    )
    scope.add_argument(
        "--partial",
        action="store_const",
        const=False,
        dest="full",
        help="some folders only, e.g. a delivery",
    )
    rec.add_argument(
        "--choose",
        action="append",
        default=[],
        metavar="ID=OPTION",
        help="another option than the default for one decision (repeatable)",
    )
    _refactor_options(rec)
    rec.set_defaults(func=cmd_receive)

    chk = commands.add_parser(
        "check",
        help="an environment's export against the repository's export of it, field by field; "
        "exit 1 if anything but volatile attributes differs",
    )
    chk.add_argument("xml", type=Path, help="the full export of the environment")
    chk.add_argument("--env", help="its environment (default: told by the letter of the names)")
    chk.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    chk.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="text: counts only; json: also the nodes of each field",
    )
    chk.set_defaults(func=cmd_check)

    cmp_ = commands.add_parser("compare", help="what changed in the chains between two git refs")
    cmp_.add_argument("base", help="base ref, e.g. develop")
    cmp_.add_argument("head", nargs="?", default="HEAD", help="head ref (default: HEAD)")
    cmp_.add_argument(
        "--worktree", action="store_true", help="compare base with the uncommitted working tree"
    )
    cmp_.add_argument(
        "--no-merge-base",
        action="store_true",
        help="compare the two tips directly; by default the base side is the merge base, "
        "so only the changes made on head are shown, as in a pull request",
    )
    _commit_option(cmp_)
    cmp_.add_argument(
        "--real-only",
        action="store_true",
        help="leave out what only calls a condition another name (the same jobs, the same "
        "ODATE and signs); by default it is shown, marked [name only]",
    )
    cmp_.add_argument(
        "--raw",
        action="store_true",
        help="two environments' branches as they are stored; by default the head is read in "
        "the terms of the base's environment (the map), so only real differences show",
    )
    cmp_.add_argument(
        "--prefer",
        action="append",
        default=[],
        metavar="ENTRY",
        help="between two environments: the entry of the map that wins where the map gives "
        "several answers for a value (repeatable; ctmchain envmap show lists them)",
    )
    cmp_.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    cmp_.add_argument("--format", choices=("text", "md", "json"), default="text")
    cmp_.set_defaults(func=cmd_compare)

    tk = commands.add_parser(
        "take", help="take changes of another branch into the checked-out one, item by item"
    )
    tk.add_argument("head", help="the branch (tag, sha) to take from")
    tk.add_argument("--base", default="HEAD", help="the checked-out branch (default: HEAD)")
    tk.add_argument(
        "--item",
        action="append",
        default=[],
        metavar="ID",
        help="an item of the comparison, e.g. subapp:S, folder:F, job:F/J, var:F/J@%%%%NAME or "
        "attr:F/J@TIMEFROM (repeatable); --list shows them",
    )
    tk.add_argument(
        "--theirs",
        action="append",
        default=[],
        metavar="ID",
        help="a conflicting item to take anyway (repeatable)",
    )
    tk.add_argument(
        "--prefer",
        action="append",
        default=[],
        metavar="ENTRY",
        help="between two environments: the entry of the map that wins where the map gives "
        "several answers for a value (repeatable; ctmchain envmap show lists them)",
    )
    tk.add_argument("--list", action="store_true", help="list the items that can be taken")
    tk.add_argument(
        "--no-merge-base",
        action="store_true",
        help="take differences of the two tips, not only what head changed since they parted",
    )
    _commit_option(tk)
    _refactor_options(tk)
    tk.set_defaults(func=cmd_take)

    pkg = commands.add_parser(
        "package",
        help="the Control-M import file with every folder changed between two git refs",
    )
    pkg.add_argument("base", help="base ref, e.g. develop")
    pkg.add_argument("head", nargs="?", default="HEAD", help="head ref (default: HEAD)")
    pkg.add_argument(
        "--env",
        help="target environment, e.g. uat; not needed between two environments' branches "
        "(it is the base's)",
    )
    pkg.add_argument(
        "--take",
        action="append",
        metavar="ID",
        help="package only this item of the comparison (repeatable; ctmchain take --list "
        "shows them): the base with the item on it, no branch is changed",
    )
    pkg.add_argument(
        "--prefer",
        action="append",
        default=[],
        metavar="ENTRY",
        help="between two environments: the entry of the map that wins where the map gives "
        "several answers for a value (repeatable; ctmchain envmap show lists them)",
    )
    pkg.add_argument(
        "--worktree", action="store_true", help="package the uncommitted working tree"
    )
    pkg.add_argument(
        "--no-merge-base",
        action="store_true",
        help="compare the two tips directly instead of from the merge base",
    )
    _commit_option(pkg)
    pkg.add_argument(
        "--jobnames",
        choices=("original", "deduped"),
        default="original",
        help="JOBNAMEs as in Control-M (default) or as stored after deduplication",
    )
    pkg.add_argument(
        "--names",
        choices=("original", "standard"),
        default="original",
        help="condition names: as imported (default) or derived from the endpoints",
    )
    pkg.add_argument(
        "-o", "--output", type=Path, help="XML file to write (default: a name like deploy_uat_...)"
    )
    pkg.add_argument(
        "--dry-run", action="store_true", help="list the folders and why, write nothing"
    )
    pkg.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    pkg.add_argument("--format", choices=("text", "json"), default="text")
    pkg.set_defaults(func=cmd_package)

    res = commands.add_parser(
        "resolve",
        help="fix validation findings: list the fixes per code, or preview/apply CODE=KIND",
    )
    res.add_argument(
        "choices",
        nargs="*",
        metavar="CODE=KIND",
        help="the fix kind to use for every finding of a code, e.g. never-cleaned=add-cleanup",
    )
    _refactor_options(res)
    res.set_defaults(func=cmd_resolve)

    com = commands.add_parser(
        "commit", help="commit the chain files, with a message written from what changed"
    )
    com.add_argument("-m", "--message", help="commit message (default: the suggested one)")
    com.add_argument("--branch", help="create this branch and commit there")
    com.add_argument(
        "--dry-run", action="store_true", help="show the files and the message, commit nothing"
    )
    com.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    com.set_defaults(func=cmd_commit)

    _add_release(commands)
    _add_refactorings(commands)
    cli_env.add_commands(commands)
    cli_assistant.add_commands(commands)

    srv = commands.add_parser(
        "serve", help="serve the local web UI and API (needs the [web] extra)"
    )
    srv.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    srv.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    srv.add_argument("--port", type=int, default=8765, help="port (default: 8765)")
    srv.add_argument("--no-browser", action="store_true", help="do not open the browser")
    srv.add_argument(
        "--check", action="store_true", help="build the app and print the URL, do not listen"
    )
    cli_assistant.serve_options(srv)
    srv.set_defaults(func=cmd_serve)
    return parser


# ---------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> int:
    environments: list[str] = []
    letters: dict[str, str] = {}
    for item in (e.strip() for e in args.envs.split(",") if e.strip()):
        name, _, letter = item.partition("=")
        environments.append(name)
        if letter:
            letters[name] = letter
    if not environments:
        raise ChainError("--envs needs at least one environment name")
    prefixes = [p.strip() for p in args.prefixes.split(",") if p.strip()]
    leading = [p.strip() for p in args.leading_only.split(",") if p.strip()]
    repo = init_repo(
        args.repo, args.application, environments, letters=letters, prefixes=prefixes,
        leading_only=leading, dedupe_jobnames=args.dedupe_jobnames,
    )  # fmt: skip
    print(
        f"Initialized chain repository at {repo.root} for application {repo.config.application} "
        f"with environments {', '.join(repo.config.environments)}"
    )
    if guide_mod.write_guide(repo):
        print(f"Wrote {guide_mod.GUIDE_FILE}: the rules of this repository, for people and agents")
    return EXIT_OK


def cmd_import(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    defined: tuple[str, ...] = ()
    if args.mappings is not None:
        repo, defined = constants_mod.apply_draft(repo, read_json(args.mappings))
    report = ops.import_xml(
        repo,
        args.xml.read_bytes(),
        env=args.env,
        dedupe_jobnames=True if args.dedupe_jobnames else None,
    )
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
    if report.jobnames_deduped:
        print(f"Deduplicated JOBNAMEs: {len(report.jobnames_deduped)}")
        for rename in report.jobnames_deduped:
            print(f"  {rename}")
    if report.duplicate_job_names:
        print(f"Repeated JOBNAME inside a folder: {', '.join(report.duplicate_job_names)}")
    if report.literal_marks:
        print(f"Literal marks (bare prefix, no letter): {len(report.literal_marks)}")
        for mark in report.literal_marks:
            print(f"  {mark}")
    if report.suspicious_values:
        print(f"Values carrying another environment's letter: {len(report.suspicious_values)}")
        for value in report.suspicious_values:
            print(f"  {value}")
    if defined:
        print(f"Constants defined from the mappings: {len(defined)} ({', '.join(defined)})")
    if report.constants_replaced or report.unmapped:
        print(f"Constants replaced: {report.constants_replaced}")
    for spec, values in report.unmapped.items():
        print(f"Unmapped {spec} ({len(values)}): {', '.join(values)}")
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    data, report = ops.export_document(
        repo,
        env=args.env,
        allow_unresolved=args.allow_unresolved,
        names=args.names,
        jobnames=args.jobnames,
    )
    args.output.write_bytes(data)
    for name in report.constants.unresolved:
        print(
            f"warning: constant {name} has no value in {args.env}; placeholder left in the XML",
            file=sys.stderr,
        )
    print(f"Wrote {args.output} ({len(data)} bytes)")
    if report.renamed:
        print(f"Standard names applied: {report.renamed} link(s) renamed")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    report = validate(load_repo(args.repo))
    if args.format == "json":
        print(json.dumps(report.to_json(), indent=2, ensure_ascii=False))
    elif args.format == "md":
        print(render_markdown(report), end="")
    else:
        print(render_text(report), end="")
    threshold = ("error", "warning", "info") if args.strict else ("error", "warning")
    return EXIT_FINDINGS if any(report.count(s) for s in threshold) else EXIT_OK


def cmd_distinct(args: argparse.Namespace) -> int:
    if args.xml is not None:
        document = parse_xml(args.xml.read_bytes())
        # inside a chain repository only the repository's application is relevant
        with contextlib.suppress(NotAChainRepo):
            document = ops.only_application(document, load_repo(args.repo).config.application)
    else:
        document = inspect_mod.load_document(load_repo(args.repo))
    result = inspect_mod.distinct_values(document, args.specs)
    if args.write is not None:
        draft = constants_mod.build_draft(load_repo(args.repo), document, args.specs, args.env)
        write_json(args.write, draft)
        print(
            f"Wrote mapping draft {args.write} ({_plural(len(args.specs), 'attribute')}); "
            "fill 'as' and 'values' or 'pattern', then import --mappings"
        )
        return EXIT_OK
    if args.format == "json":
        payload = {spec: [v.to_json() for v in values] for spec, values in result.items()}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_OK
    for spec, values in result.items():
        print(f"{spec} ({_plural(len(values), 'distinct value')})")
        for value in values:
            print(f"  {value.count:6}  {value.value}  <- {', '.join(value.samples)}")
    return EXIT_OK


def cmd_map(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    selector = constants_mod.parse_spec(args.spec, inline=args.inline)
    values: dict[str, str | None] = {}
    if args.pattern:
        values.update(constants_mod.values_from_pattern(args.pattern, repo.env_letters()))
    for item in args.values:
        env, sep, value = item.partition("=")
        if not sep or not env:
            raise ChainError(f"--value expects ENV=VALUE, got {item!r}")
        values[env] = value
    if args.env:
        values[args.env] = args.value
    if not values:
        raise ChainError("map needs --pattern, --value ENV=VALUE or --env to know the values")
    repo = constants_mod.define_constant(repo, args.name, selector, values)
    table = constants_mod.constants_table(repo)[args.name]
    cells = ", ".join(
        f"{env}={value if value is not None else '?'}" for env, value in table.items()
    )
    print(f"{args.name} ({selector.spec}): {cells}")
    return EXIT_OK


def cmd_env_help(args: argparse.Namespace) -> int:
    print(
        "usage: ctmchain env constants [--repo DIR] [--env ENV] [--missing] [--format text|json]"
    )
    print("       ctmchain env learn XML [--env ENV] [--repo DIR] [--apply] [--stat]")
    return EXIT_USAGE


_SHOWN_PER_KIND = 20
_DECISION_ORDER = (
    "learn", "set-value", "adopt", "group", "constant", "unmatched", "value", "element",
    "removed", "added", "absent",
)  # fmt: skip


def _decision_line(decision: intake_mod.Decision) -> str:
    options = "|".join(decision.options)
    head = f"  {decision.id}  {decision.default} [{options}]"
    uses = (
        f" ({_plural(decision.count, 'use')})" if decision.kind in ("learn", "set-value") else ""
    )
    if decision.kind == "learn":
        return f"{head}  {decision.constant} = {decision.incoming}{uses}"
    if decision.kind == "set-value":
        return f"{head}  {decision.constant}: {decision.expected} -> {decision.incoming}{uses}"
    if decision.kind in ("value", "constant"):
        return f"{head}  {decision.current} -> {decision.incoming}"
    if decision.kind == "element":
        if decision.incoming is None:
            return f"{head}  the repository alone has it ({decision.current})".rstrip(" ()")
        return f"{head}  the export alone has it ({decision.incoming})".rstrip(" ()")
    if decision.kind == "adopt":
        uses = _plural(decision.count, "use")
        return f"{head}  {decision.incoming} where the repository has {decision.current} ({uses})"
    if decision.kind == "unmatched":
        uses = _plural(decision.count, "use")
        return (
            f"{head}  {decision.field} = {decision.incoming} ({uses}); new: {decision.suggested}"
        )
    if decision.kind == "group":
        uses = _plural(decision.count, "use")
        values = ", ".join(f"{env} {value}" for env, value in (decision.values or {}).items())
        if decision.inline:
            what = f"{decision.field}: the name of the environment inside the text"
            values = f"inline: {values}"
        else:
            what = f"{decision.field} {decision.current} -> {decision.incoming}"
        return f"{head}  {what} ({uses}); new: {decision.suggested} ({values})"
    return head


def _print_intake(intake: intake_mod.Intake) -> None:
    print(f"{intake.env} export: {'; '.join(intake.evidence)}")
    statuses = {
        s: sum(1 for f in intake.folders if f.status == s) for s in ("new", "changed", "same")
    }
    print(
        f"Folders: {len(intake.folders)} ({statuses['new']} new, {statuses['changed']} changed, "
        f"{statuses['same']} unchanged)"
        + (", full export" if intake.full else ", some folders only" if intake.partial else "")
    )
    if intake.decisions:
        print(
            "Decisions (default [options]; another one with --choose ID=OPTION, "
            "a new constant with ID=new:NAME):"
        )
    for kind in _DECISION_ORDER:
        of_kind = [d for d in intake.decisions if d.kind == kind and not d.known]
        for decision in of_kind[:_SHOWN_PER_KIND]:
            print(_decision_line(decision))
        if len(of_kind) > _SHOWN_PER_KIND:
            print(f"  ... {len(of_kind) - _SHOWN_PER_KIND} more {kind} decisions (--format json)")
    known = sum(1 for d in intake.decisions if d.known)
    if known:
        print(
            f"  {_plural(known, 'difference')} already exceptions of {intake.env}: kept "
            "(--choose ID=change: the base takes it; ID=ignore: it goes; --format json lists them)"
        )
    for line in intake.unresolved:
        print(f"unresolved: {line}")
    for warning in intake.warnings:
        print(f"warning: {warning}")
    print()


def cmd_receive(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    data = args.xml.read_bytes()
    choices = _pairs(args.choose, "ID=OPTION", last=True)  # ids may hold "=", options do not
    intake = intake_mod.analyze(repo, data, args.env, args.full)
    if args.format == "text":
        _print_intake(intake)
    if args.apply:
        workspace_mod.ensure_editable(repo)
    change = intake_mod.receive(repo, data, intake.env, choices, intake.full)
    if args.format == "json":
        result = refactor_mod.apply(repo, change) if args.apply and change.edits else None
        body = {"intake": intake.to_json(), "change": change.to_json(), "applied": bool(result)}
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return EXIT_OK
    args.build = lambda _r, _a: change
    return cmd_refactor(args)


def cmd_check(args: argparse.Namespace) -> int:
    check = check_mod.check_export(load_repo(args.repo), args.xml.read_bytes(), args.env)
    if args.format == "json":
        print(json.dumps(check.to_json(), indent=2, ensure_ascii=False))
        return EXIT_OK if check.clean else EXIT_FINDINGS
    env = check.env
    print(f"{env} export: {'; '.join(check.evidence)}")
    for warning in check.warnings:
        print(f"warning: {warning}")
    same = "the same" if check.identical else "not the same"
    print(f"The repository's export of {env} is {same} byte for byte")
    print(
        f"Folders and jobs: {check.nodes} in the export, {check.both} in both, "
        f"{len(check.only_export)} only in the export, "
        f"{len(check.only_repository)} only in the repository"
    )
    print(
        f"Constants: {check.constants} with a value in {env}, {len(check.unresolved)} needed "
        f"without one; exceptions of {env}: {check.exceptions}"
    )
    if not check.fields:
        print("No field differs.")
        return EXIT_OK if check.clean else EXIT_FINDINGS
    width = max(24, *(len(f.field) for f in check.fields))
    columns = [f"{env} vs {check.production}"] if check.production else []
    columns.append(f"repository vs {env}")
    print(f"{'field':<{width}}" + "".join(f"  {c}" for c in columns))
    for f in check.fields:
        counts = [] if f.from_production is None else [f.from_production]
        counts.append(len(f.differs))
        cells = "".join(f"  {n:>{len(c)}}" for n, c in zip(counts, columns, strict=True))
        print(f"{f.field:<{width}}{cells}")
    if not check.clean:
        print("The nodes of each field: --format json")
    return EXIT_OK if check.clean else EXIT_FINDINGS


def cmd_env_learn(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    intake = intake_mod.analyze(repo, args.xml.read_bytes(), args.env)
    wanted = [
        d
        for d in intake.decisions
        if d.kind in ("learn", "set-value")
        and d.constant
        and (not args.only or d.constant.startswith(tuple(args.only)))
    ]
    values = {d.constant: d.incoming for d in wanted if d.constant}
    print(f"{intake.env} export: {'; '.join(intake.evidence)}")
    for decision in wanted:
        if decision.kind in ("learn", "set-value"):
            before = decision.expected if decision.kind == "set-value" else None
            print(
                f"  {decision.constant}: {before or '?'} -> {decision.incoming} "
                f"({_plural(decision.count, 'use')})"
            )
    disagree = sum(1 for d in intake.decisions if d.kind == "constant")
    if disagree:
        print(f"{_plural(disagree, 'value')} of single jobs disagree: see ctmchain receive")
    if not values:
        print("Nothing to learn.")
        return EXIT_OK
    args.build = lambda r, _a: refactor_mod.run_operation(
        r, "set-values", {"env": intake.env, "values": values}
    )
    return cmd_refactor(args)


def cmd_env_constants(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    if args.env and args.env not in repo.config.environments:
        raise ChainError(f"unknown environment {args.env!r}")
    table = constants_mod.constants_table(repo)
    envs = [args.env] if args.env else list(repo.config.environments)
    rows = {
        name: {env: values[env] for env in envs}
        for name, values in table.items()
        if not args.missing or any(values[env] is None for env in envs)
    }
    if args.format == "json":
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    elif not rows:
        print("every constant has a value" if args.missing else "no constants defined")
    else:
        for name, values in rows.items():
            shown = {e: v for e, v in values.items() if not args.missing or v is None}
            cells = ", ".join(f"{e}={v if v is not None else '?'}" for e, v in shown.items())
            print(f"{name:32} {repo.config.constants[name].spec:28} {cells}")
    missing = any(v is None for values in rows.values() for v in values.values())
    return EXIT_FINDINGS if args.missing and missing else EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    data = inspect_mod.show_node(load_repo(args.repo), args.node, args.env)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return EXIT_OK


def cmd_graph(args: argparse.Namespace) -> int:
    graph = graph_mod.folder_graph(load_repo(args.repo), args.folder, args.env)
    if args.format == "json":
        print(json.dumps(graph.to_json(), indent=2, ensure_ascii=False))
    elif args.format == "mermaid":
        print(graph_mod.render_mermaid(graph), end="")
    elif args.format == "dot":
        print(graph_mod.render_dot(graph), end="")
    else:
        print(graph_mod.render_text(graph), end="")
    return EXIT_OK


def cmd_links(args: argparse.Namespace) -> int:
    if (args.node is None) == (args.name is None):
        raise ChainError("links needs either a node (FOLDER/JOB) or --name <condition>")
    links = graph_mod.load_links(load_repo(args.repo))
    if args.name is not None:
        if args.name not in links:
            raise ChainError(f"no link named {args.name!r}")
        selected = [links[args.name]]
    else:
        ref = NodeRef.parse(args.node)
        selected = [
            link
            for link in links.values()
            if ref in link.consumers
            or ref in link.all_producers
            or ref in link.deleters
            or any(node == ref for node, _ in link.docond_delete)
        ]
    if args.format == "json":
        print(json.dumps([link.to_json() for link in selected], indent=2, ensure_ascii=False))
        return EXIT_OK
    for link in selected:
        producers = ", ".join(str(n) for n in link.all_producers) or "-"
        consumers = ", ".join(str(n) for n in link.consumers) or "-"
        standard = link.standard_name()
        suffix = f"  standard: {standard}" if standard and standard != link.name else ""
        print(f"{link.kind:11} {link.name}  {producers} -> {consumers}{suffix}")
    return EXIT_OK


def _commit_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--commit",
        dest="commits",
        action="append",
        metavar="SHA",
        help="only this commit of head (repeat it); the others are left out, cherry-pick style",
    )


def cmd_take(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    merge_base = not args.no_merge_base
    if args.list:
        result = compare_mod.compare(
            repo.root, args.base, args.head, use_merge_base=merge_base, commits=args.commits
        )
        _print_takeable(repo.root, result, take_mod.items_of(result), args.format)
        return EXIT_OK
    if args.apply:
        workspace_mod.ensure_editable(repo)
    try:
        change = take_mod.take(
            repo, args.base, args.head, args.item, theirs=args.theirs,
            use_merge_base=merge_base, commits=args.commits, prefer=args.prefer,
        )  # fmt: skip
    except TakeConflict as conflict:
        for c in conflict.conflicts:
            print(
                f"conflict {c['item']}: mine {take_mod.shown(c['mine'])}, before "
                f"{take_mod.shown(c['before'])}, theirs {take_mod.shown(c['theirs'])} "
                f"(take it with --theirs {c['item']}, or leave it out)",
                file=sys.stderr,
            )
        raise
    args.build = lambda _r, _a: change
    return cmd_refactor(args)


def cmd_compare(args: argparse.Namespace) -> int:
    head = WORKTREE if args.worktree else args.head
    result = compare_mod.compare(
        load_repo(args.repo).root,
        args.base,
        head,
        use_merge_base=not args.no_merge_base,
        commits=args.commits,
        translate=not args.raw,
        prefer=args.prefer,
    )
    if args.real_only:
        result = result.real_only()
    if args.format == "json":
        print(json.dumps(result.to_json(), indent=2, ensure_ascii=False))
    elif args.format == "md":
        print(compare_mod.render_markdown(result), end="")
    else:
        print(compare_mod.render_text(result), end="")
    return EXIT_OK


def _commit_count(selected: Sequence[str] | None, commits: Sequence[Any]) -> str:
    total = sum(1 for c in commits if not c.merge)
    if selected is None:
        return _plural(len(commits), "commit")
    return f"{len(selected)} of {_plural(total, 'commit')}"


def _print_takeable(
    root: Path, result: compare_mod.Comparison, items: Sequence[tuple[str, str]], fmt: str
) -> None:
    """The items of a comparison that ``take`` accepts, as a list or as JSON."""
    into = result.base.name
    if into == "HEAD":  # the default base: say which branch that is
        into = environments_mod.current_branch(root) or into
    if fmt == "json":
        envs = None if result.environments is None else list(result.environments)
        rows = [{"id": item, "label": label} for item, label in items]
        body = {"into": into, "from": result.head.name, "environments": envs, "items": rows}
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return
    if result.environments is None:
        print(f"Items {result.head.name} changed that can be taken into {into}:")
    else:
        target, source = result.environments
        print(f"Items {result.head.name} ({source}) has that can be taken into {into} ({target}):")
    for item, label in items:
        print(f"  {item}  {label}")


def _package_headline(package: package_mod.Package) -> str:
    folders = _plural(len(package.folders), "folder")
    chosen = None if package.taken is None else f"{_plural(len(package.taken), 'item')} taken"
    if package.source is not None:
        return (
            f"Package {package.head.name} ({package.source}) for {package.env} "
            f"({package.base.name}): {folders}, {chosen or 'everything that differs'}"
        )
    origin = f" (from merge base {package.merge_base[:7]})" if package.merge_base else ""
    line = (
        f"Package {package.base.name}..{package.head.name} for {package.env}: {folders}, "
        f"{_commit_count(package.selected, package.commits)}{origin}"
    )
    return line if chosen is None else f"{line}, {chosen}"


def cmd_package(args: argparse.Namespace) -> int:
    head = WORKTREE if args.worktree else args.head
    package = package_mod.build_package(
        load_repo(args.repo).root,
        args.base,
        head,
        env=args.env,
        commits=args.commits,
        use_merge_base=not args.no_merge_base,
        names=args.names,
        jobnames=args.jobnames,
        take=args.take,
        prefer=args.prefer,
    )
    output = args.output or Path(package.filename)
    if args.format == "json":
        print(json.dumps(package.to_json(), indent=2, ensure_ascii=False))
    else:
        print(_package_headline(package))
        for folder in package.folders:
            print(f"  {folder.name} ({_plural(folder.jobs, 'job')}): {'; '.join(folder.reasons)}")
        for warning in package.warnings:
            print(f"warning: {warning}")
        for finding in package.findings:
            print(
                f"new finding: {finding.severity} {finding.code} {finding.node}: {finding.message}"
            )
    report = sys.stderr if args.format == "json" else sys.stdout
    if package.xml is None:
        print(
            f"Nothing to package: no folder changed between {package.base.name} and "
            f"{package.head.name}.",
            file=report,
        )
    elif not args.dry_run:
        output.write_bytes(package.xml)
        print(f"Wrote {output} ({package.size} bytes)", file=report)
    return EXIT_OK


def cmd_serve(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    try:
        from controlm_chain_admin.web.serve import run
        from controlm_chain_admin.web.settings import Settings
    except ImportError as exc:  # pragma: no cover - depends on the installed extras
        raise ChainError(
            "the web server needs the [web] extra: pip install 'controlm-chain-admin[web]'"
        ) from exc
    settings = Settings(
        repo=repo.root, host=args.host, port=args.port, open_browser=not args.no_browser
    )
    if settings.token is None:  # CTMCHAIN_TOKEN keeps open tabs working across restarts
        settings = settings.model_copy(update={"token": secrets.token_urlsafe(18)})
    assert settings.token is not None
    folders = len(folder_names(repo))
    print(f"Serving {repo.config.application} ({_plural(folders, 'folder')}) at {settings.url}")
    print(f"Editing enabled at {settings.editor_url(settings.token)}")
    kilo = cli_assistant.start_assistant(repo, args.assistant_model) if args.assistant else None
    try:
        if kilo is not None:
            settings = settings.model_copy(update={
                "assistant_url": kilo.url, "assistant_password": kilo.password,
                "assistant_model": args.assistant_model or settings.assistant_model,
            })  # fmt: skip
        if args.check:
            return EXIT_OK
        run(settings)  # pragma: no cover - blocks until interrupted
    finally:
        if kilo is not None:
            kilo.stop()
    return EXIT_OK  # pragma: no cover


# ---------------------------------------------------------------- entry point


def _refactor_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    parser.add_argument("--apply", action="store_true", help="write the change (default: preview)")
    parser.add_argument("--stat", action="store_true", help="list the files instead of the diff")
    parser.add_argument("--format", choices=("text", "json"), default="text")


def _add_refactorings(commands: Any) -> None:
    """Refactoring subcommands: every one previews a change set and writes only with --apply."""
    rj = commands.add_parser("rename-job", help="rename a job; condition names follow")
    rj.add_argument("node", metavar="FOLDER/JOB")
    rj.add_argument("new_name", metavar="NEW_JOBNAME")
    rj.add_argument("--keep-names", action="store_true", help="do not rename condition names")
    rj.add_argument(
        "--with-memname", action="store_true", help="rename MEMNAME when it equals JOBNAME"
    )
    _refactor_options(rj)
    rj.set_defaults(
        func=cmd_refactor,
        build=lambda r, a: refactor_mod.rename_job(
            r, a.node, a.new_name, update_names=not a.keep_names, with_memname=a.with_memname
        ),
    )

    rf = commands.add_parser("rename-folder", help="rename a folder and everything that names it")
    rf.add_argument("folder")
    rf.add_argument("new_name", metavar="NEW_FOLDER_NAME")
    rf.add_argument("--keep-names", action="store_true", help="do not rename condition names")
    _refactor_options(rf)
    rf.set_defaults(
        func=cmd_refactor,
        build=lambda r, a: refactor_mod.rename_folder(
            r, a.folder, a.new_name, update_names=not a.keep_names
        ),
    )

    rs = commands.add_parser("rename-subapp", help="rename a SUB_APPLICATION (one folder or all)")
    rs.add_argument("old")
    rs.add_argument("new")
    rs.add_argument("--folder", help="only this folder")
    _refactor_options(rs)
    rs.set_defaults(
        func=cmd_refactor,
        build=lambda r, a: refactor_mod.rename_subapp(r, a.old, a.new, folder=a.folder),
    )

    mj = commands.add_parser("move-job", help="move a job to another folder")
    mj.add_argument("node", metavar="FOLDER/JOB")
    mj.add_argument("target", metavar="TARGET_FOLDER")
    _refactor_options(mj)
    mj.set_defaults(
        func=cmd_refactor, build=lambda r, a: refactor_mod.move_job(r, a.node, a.target)
    )

    ij = commands.add_parser("insert-job", help="insert a new job between two linked jobs")
    ij.add_argument("node", metavar="FOLDER/NEW_JOB")
    ij.add_argument("--after", required=True, metavar="FOLDER/JOB", help="upstream job")
    ij.add_argument("--before", required=True, metavar="FOLDER/JOB", help="downstream job")
    ij.add_argument("--like", metavar="FOLDER/JOB", help="copy the attributes of this job")
    ij.add_argument("--link", help="link id or name when several links join the two jobs")
    _refactor_options(ij)
    ij.set_defaults(
        func=cmd_refactor,
        build=lambda r, a: refactor_mod.insert_job(
            r, a.node, after=a.after, before=a.before, like=a.like, link=a.link
        ),
    )

    ev = commands.add_parser(
        "extract-variable", help="move a literal of a command into a job variable"
    )
    ev.add_argument("target", metavar="FOLDER/JOB|FOLDER/")
    ev.add_argument("--literal", required=True, help="text to move out of the attribute")
    ev.add_argument(
        "--as", dest="variable", required=True, help="variable name, e.g. %%%%DATASERVER"
    )
    ev.add_argument("--attribute", default="CMDLINE", help="attribute to edit (default: CMDLINE)")
    _refactor_options(ev)
    ev.set_defaults(
        func=cmd_refactor,
        build=lambda r, a: refactor_mod.extract_variable(
            r, a.target, a.literal, a.variable, attribute=a.attribute
        ),
    )

    se = commands.add_parser(
        "set-exception", help="what one environment uses for a job or folder instead of the base"
    )
    se.add_argument("env")
    se.add_argument("node", metavar="FOLDER/JOB|FOLDER/")
    se.add_argument("--set", dest="sets", action="append", default=[], metavar="ATTR=VALUE")
    se.add_argument(
        "--unset", action="append", default=[], metavar="ATTR", help="leave it out there"
    )
    se.add_argument("--var", dest="vars", action="append", default=[], metavar="%%NAME=VALUE")
    se.add_argument(
        "--drop", action="append", default=[], metavar="NAME", help="back to the base value"
    )
    _refactor_options(se)
    se.set_defaults(func=cmd_refactor, build=_build_exception)

    pe = commands.add_parser(
        "promote-exception",
        help="make what one environment has as its exception the base (the exception goes)",
    )
    pe.add_argument("env")
    pe.add_argument("node", metavar="FOLDER/JOB|FOLDER/")
    pe.add_argument("names", nargs="+", metavar="NAME", help="attribute, %%%%variable or line")
    _refactor_options(pe)
    pe.set_defaults(
        func=cmd_refactor,
        build=lambda r, a: refactor_mod.promote_exception(r, a.env, a.node, a.names),
    )

    tech = commands.add_parser(
        "technical",
        help="the technical attributes (kept in meta, never compared, never an exception): "
        "list them, or add and remove names",
    )
    tech.add_argument("--add", action="append", default=[], metavar="NAME")
    tech.add_argument("--remove", action="append", default=[], metavar="NAME")
    _refactor_options(tech)
    tech.set_defaults(func=cmd_technical)

    rc = commands.add_parser("rename-constant", help="rename a constant everywhere it is used")
    rc.add_argument("old")
    rc.add_argument("new")
    _refactor_options(rc)
    rc.set_defaults(
        func=cmd_refactor, build=lambda r, a: refactor_mod.rename_constant(r, a.old, a.new)
    )


def _pairs(items: Sequence[str], what: str, *, last: bool = False) -> dict[str, str]:
    """``KEY=VALUE`` items; split at the last ``=`` when keys may hold one."""
    pairs = {}
    for item in items:
        key, sep, value = item.rpartition("=") if last else item.partition("=")
        if not sep or not key:
            raise ChainError(f"expected {what}, got {item!r}")
        pairs[key] = value
    return pairs


def _build_exception(repo: Any, args: argparse.Namespace) -> Any:
    attributes: dict[str, str | None] = dict(_pairs(args.sets, "ATTR=VALUE"))
    attributes.update(dict.fromkeys(args.unset))
    return refactor_mod.set_exception(
        repo, args.env, args.node, attributes, _pairs(args.vars, "%%NAME=VALUE"), args.drop
    )


def _add_release(commands: Any) -> None:
    """``release``: where edits go, from a release branch to the trunk."""
    rel = commands.add_parser(
        "release", help="releases: start one from the trunk, mark installations, close it"
    )
    sub = rel.add_subparsers(dest="release_command", metavar="<subcommand>")

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        parser: argparse.ArgumentParser = sub.add_parser(name, help=help_text)
        parser.add_argument(
            "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
        )
        return parser

    status = command("status", "the branch, whether it may be edited, releases and stashes")
    status.add_argument("--format", choices=("text", "json"), default="text")
    status.set_defaults(func=cmd_release_status)
    start = command("start", "create release/NAME from the trunk and switch to it")
    start.add_argument("name")
    start.add_argument("--stash", action="store_true", help="stash uncommitted changes first")
    start.set_defaults(func=cmd_release_start)
    switch = command("switch", "switch to another branch (local, or on the remote)")
    switch.add_argument("branch")
    switch.add_argument("--stash", action="store_true", help="stash uncommitted changes first")
    switch.set_defaults(func=cmd_release_switch)
    installed = command("installed", "record that a release is installed in an environment")
    installed.add_argument("env")
    installed.add_argument("--release", help="release name (default: the checked-out one)")
    installed.add_argument("--commit", help="the installed commit (default: the release tip)")
    installed.set_defaults(func=cmd_release_installed)
    update = command("update", "merge the trunk into the checked-out release")
    update.set_defaults(func=cmd_release_update)
    close = command("close", "merge the release into the trunk once installed in production")
    close.set_defaults(func=cmd_release_close)
    rel.set_defaults(func=cmd_release_help)


def cmd_release_help(args: argparse.Namespace) -> int:
    print("usage: ctmchain release {status,start,switch,installed,update,close} [--repo DIR]")
    return EXIT_USAGE


def _release_line(release: workspace_mod.Release, state: workspace_mod.Workspace) -> str:
    parts = [release.branch, f"{release.ahead} ahead of {state.trunk}"]
    if release.trunk_behind:
        parts[-1] += f", {release.trunk_behind} behind"
    installed = {i.env: i for i in release.installed}
    for env in state.environments:
        mark = installed.get(env)
        text = (
            mark.tag + (f" ({mark.behind} behind)" if mark and mark.behind else "")
            if mark
            else "-"
        )
        parts.append(f"{env}: {text}")
    if not release.local:
        parts.append("(on the remote only)")
    if release.closable:
        parts.append("ready to close")
    return "  " + "  ".join(parts)


def cmd_release_status(args: argparse.Namespace) -> int:
    state = workspace_mod.workspace(load_repo(args.repo))
    if args.format == "json":
        print(json.dumps(state.to_json(), indent=2, ensure_ascii=False))
        return EXIT_OK
    where = "editable" if state.editable else f"read-only: {state.reason}"
    changes = _plural(state.changes, "uncommitted chain file")
    print(f"On {state.branch or 'a detached HEAD'} · {where} · {changes}")
    remote = state.remote or "none"
    if state.upstream:
        remote += f" ({state.upstream}: {state.ahead} ahead, {state.behind} behind)"
    print(f"Trunk: {state.trunk} · production: {state.production} · remote: {remote}")
    print("Releases:" if state.releases else "No release.")
    for release in state.releases:
        print(_release_line(release, state))
    if state.stashes:
        print("Stashes:")
    for saved in state.stashes:
        print(f"  {saved.ref} on {saved.branch or '?'}: {saved.message}")
    return EXIT_OK


def cmd_release_start(args: argparse.Namespace) -> int:
    print(workspace_mod.start_release(load_repo(args.repo), args.name, stash=args.stash))
    return EXIT_OK


def cmd_release_switch(args: argparse.Namespace) -> int:
    print(workspace_mod.switch(load_repo(args.repo), args.branch, stash=args.stash))
    return EXIT_OK


def cmd_release_installed(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    done = workspace_mod.mark_installed(repo, args.env, args.release, args.commit)
    branch = repo.config.git_rules.release_prefix + (
        args.release or workspace_mod.workspace(repo).release or "?"
    )
    print(f"Tagged {done.tag} on {done.sha[:7]}: {branch} in {done.env}")
    return EXIT_OK


def cmd_release_update(args: argparse.Namespace) -> int:
    print(workspace_mod.update_from_trunk(load_repo(args.repo)))
    return EXIT_OK


def cmd_release_close(args: argparse.Namespace) -> int:
    print(workspace_mod.close_release(load_repo(args.repo)))
    return EXIT_OK


def cmd_commit(args: argparse.Namespace) -> int:
    root = load_repo(args.repo).root
    state = commit_mod.pending(root)
    if not state.files:
        print("Nothing to commit: the chain files have no change.")
        return EXIT_OK
    message = args.message or state.message
    if args.dry_run:
        print(f"On {state.branch or 'a detached HEAD'}: {_plural(len(state.files), 'file')}")
        for path in state.files:
            print(f"  {path}")
        print()
        print(message)
        print()
        print("Nothing committed (dry run).")
        return EXIT_OK
    done = commit_mod.commit(root, message, state.fingerprint, branch=args.branch)
    print(f"Committed {done.sha[:7]} on {done.branch}: {done.subject}")
    return EXIT_OK


def cmd_resolve(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    findings = validate(repo).findings
    fixes = fixes_mod.fixes_for(repo, findings)
    if not args.choices:
        codes: dict[str, list[tuple[fixes_mod.Fix, ...]]] = {}
        for finding, offered in zip(findings, fixes, strict=True):
            codes.setdefault(finding.code, []).append(offered)
        for code, groups in codes.items():
            kinds: dict[str, tuple[str, int]] = {}
            for offered in groups:
                for fix in offered:
                    title, count = kinds.get(fix.kind, (fix.title, 0))
                    single = sum(1 for f in offered if f.kind == fix.kind) == 1
                    kinds[fix.kind] = (title, count + (1 if single else 0))
            head = f"{code} ({_plural(len(groups), 'finding')})"
            print(head + ("" if kinds else ": no fix"))
            for kind, (title, count) in kinds.items():
                print(f"  {kind}: {title} ({count})")
        return EXIT_OK
    choice: dict[str, str] = {}
    for item in args.choices:
        code, sep, kind = item.partition("=")
        if not sep or not code or not kind:
            print(f"ctmchain: error: expected CODE=KIND, got {item!r}", file=sys.stderr)
            return EXIT_USAGE
        choice[code] = kind
    changes, skipped = fixes_mod.by_kind(findings, fixes, choice)
    if not changes:
        print("Nothing to change.")
        status = EXIT_OK
    else:
        args.build = lambda r, _a: refactor_mod.run_operation(r, "batch", {"changes": changes})
        status = cmd_refactor(args)
    for finding in skipped:
        print(f"skipped: {finding.code} {finding.name} (no single {choice[finding.code]} fix)")
    return status


def cmd_technical(args: argparse.Namespace) -> int:
    if not args.add and not args.remove:
        for name in load_repo(args.repo).config.volatile_attributes:
            print(name)
        return EXIT_OK
    args.build = lambda r, a: refactor_mod.set_technical(r, a.add, a.remove)
    return cmd_refactor(args)


def cmd_refactor(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    if args.apply:
        workspace_mod.ensure_editable(repo)
    change = args.build(repo, args)
    result = refactor_mod.apply(repo, change) if args.apply and change.edits else None
    if args.format == "json":
        print(
            json.dumps(
                {**change.to_json(), "applied": result is not None}, indent=2, ensure_ascii=False
            )
        )
        return EXIT_OK
    print(change.summary)
    for warning in change.warnings:
        print(f"warning: {warning}")
    if not change.edits:
        print("Nothing to change.")
        return EXIT_OK
    print(change.stat() if args.stat else change.diff(), end="")
    if result is not None:
        print(f"Applied: {result.written} written, {result.deleted} deleted")
    else:
        print(f"Preview only: {_plural(len(change.edits), 'file')}; re-run with --apply to write.")
    return EXIT_OK


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
    except BrokenPipeError:  # e.g. `ctmchain validate | head`: the reader went away
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return EXIT_OK
    except OSError as exc:
        print(f"ctmchain: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return result
