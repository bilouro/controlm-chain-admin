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
from controlm_chain_admin.core import graph as graph_mod
from controlm_chain_admin.core import inspect as inspect_mod
from controlm_chain_admin.core import ops
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.links import NodeRef
from controlm_chain_admin.core.repo import init_repo, load_repo
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
    imp.add_argument("--format", choices=("text", "json"), default="text", help="report format")
    imp.set_defaults(func=cmd_import)

    exp = commands.add_parser("export", help="regenerate the Control-M XML from the repository")
    exp.add_argument(
        "--repo", type=Path, default=Path("."), help="repository directory (default: .)"
    )
    exp.add_argument("--env", help="target environment (needed with the letter rule)")
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
    report = ops.import_xml(repo, args.xml.read_bytes(), env=args.env)
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
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    repo = load_repo(args.repo)
    data = ops.export_xml(repo, env=args.env)
    args.output.write_bytes(data)
    print(f"Wrote {args.output} ({len(data)} bytes)")
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
    else:
        document = inspect_mod.load_document(load_repo(args.repo))
    result = inspect_mod.distinct_values(document, args.specs)
    if args.format == "json":
        payload = {spec: [v.to_json() for v in values] for spec, values in result.items()}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_OK
    for spec, values in result.items():
        print(f"{spec} ({_plural(len(values), 'distinct value')})")
        for value in values:
            print(f"  {value.count:6}  {value.value}  <- {', '.join(value.samples)}")
    return EXIT_OK


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
        print(f"{link.kind:11} {link.name}  {producers} -> {consumers}")
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
