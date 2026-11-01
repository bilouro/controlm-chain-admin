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

from controlm_chain_admin import __version__
from controlm_chain_admin.core import constants as constants_mod
from controlm_chain_admin.core import graph as graph_mod
from controlm_chain_admin.core import inspect as inspect_mod
from controlm_chain_admin.core import ops
from controlm_chain_admin.core import refactor as refactor_mod
from controlm_chain_admin.core.errors import ChainError, NotAChainRepo
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
        choices=("deduped", "original"),
        default="deduped",
        help="JOBNAMEs as stored (default) or restored to the originals before deduplication",
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
    show.set_defaults(func=cmd_show)

    gr = commands.add_parser("graph", help="chain graph of one folder")
    gr.add_argument("folder")
    gr.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
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
    envp.set_defaults(func=cmd_env_help)

    _add_refactorings(commands)

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
    repo = init_repo(args.repo, args.application, environments, letters=letters, prefixes=prefixes)
    print(
        f"Initialized chain repository at {repo.root} for application {repo.config.application} "
        f"with environments {', '.join(repo.config.environments)}"
    )
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
    return EXIT_USAGE


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
    data = inspect_mod.show_node(load_repo(args.repo), args.node)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return EXIT_OK


def cmd_graph(args: argparse.Namespace) -> int:
    graph = graph_mod.folder_graph(load_repo(args.repo), args.folder)
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
        repo=repo.root,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        token=secrets.token_urlsafe(18),
    )
    assert settings.token is not None
    folders = len(folder_names(repo))
    print(f"Serving {repo.config.application} ({_plural(folders, 'folder')}) at {settings.url}")
    print(f"Editing enabled at {settings.editor_url(settings.token)}")
    if args.check:
        return EXIT_OK
    run(settings)  # pragma: no cover - blocks until interrupted
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


def cmd_refactor(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
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
