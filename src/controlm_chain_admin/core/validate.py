"""Validation of a chain repository: graph consistency, naming, duplicates.

Severities: ``error`` (a chain is broken inside the repository), ``warning`` (something is
inconsistent and probably unintended), ``info`` (worth knowing, no action implied, e.g. a link
whose other end lives outside this repository).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from controlm_chain_admin.core.links import (
    Link,
    NodeRef,
    folder_names,
    load_links,
    rebuild_links,
)
from controlm_chain_admin.core.ops import DUPLICATE_SEPARATOR
from controlm_chain_admin.core.repo import ChainRepo, read_json

SEVERITIES = ("error", "warning", "info")
_RANK = {severity: index for index, severity in enumerate(SEVERITIES)}

_NAME_PATTERNS = (
    re.compile(r"^(?P<a>[^-]+)-(?P<b>[^-]+)_OK$", re.IGNORECASE),
    re.compile(r"^(?P<a>[^-]+)-TO-(?P<b>[^-]+)$"),
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    node: str  # "FOLDER/JOB", "FOLDER/" or "" when not tied to a node
    name: str  # condition or job name the finding is about
    message: str

    def to_json(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "node": self.node,
            "name": self.name,
            "message": self.message,
        }


@dataclass(frozen=True)
class ValidateReport:
    findings: tuple[Finding, ...]
    links: int
    nodes: int

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def worst(self) -> str | None:
        for severity in SEVERITIES:
            if self.count(severity):
                return severity
        return None

    def to_json(self) -> dict[str, Any]:
        return {
            "links": self.links,
            "nodes": self.nodes,
            "counts": {s: self.count(s) for s in SEVERITIES},
            "findings": [f.to_json() for f in self.findings],
        }


def parse_condition_name(name: str) -> tuple[str, str] | None:
    """Split ``A-B_OK`` or ``A-TO-B`` into (producer name, consumer name); None otherwise."""
    for pattern in _NAME_PATTERNS:
        match = pattern.match(name)
        if match:
            return match.group("a"), match.group("b")
    return None


def _node_name(node: NodeRef) -> str:
    """The name a condition would embed for this node: the job name, or the folder name."""
    base = node.job if node.job is not None else node.folder
    return base.split(DUPLICATE_SEPARATOR)[0]


def _first(*groups: tuple[NodeRef, ...]) -> str:
    for group in groups:
        if group:
            return str(group[0])
    return ""


def _check_link(link: Link, known_names: set[str], out: list[Finding]) -> None:
    parsed = parse_condition_name(link.name)
    producers = link.all_producers
    if parsed is None:
        out.append(
            Finding(
                "info",
                "non-standard-name",
                _first(link.consumers, producers),
                link.name,
                "name does not follow <PRODUCER>-<CONSUMER>_OK or <PRODUCER>-TO-<CONSUMER>",
            )
        )
    kind = link.kind
    if kind == "dangling":
        producer_name = parsed[0] if parsed else None
        node = _first(link.consumers)
        if producer_name is None:
            out.append(
                Finding(
                    "warning", "dangling-unknown", node, link.name, "waited for, never produced"
                )
            )
        elif producer_name in known_names:
            out.append(
                Finding(
                    "error",
                    "dangling",
                    node,
                    link.name,
                    f"{producer_name} exists in the repository but never emits this condition",
                )
            )
        else:
            out.append(
                Finding(
                    "info",
                    "dangling-external",
                    node,
                    link.name,
                    f"producer {producer_name} is not in this repository",
                )
            )
    elif kind == "unconsumed":
        consumer_name = parsed[1] if parsed else None
        node = _first(producers)
        if consumer_name is not None and consumer_name not in known_names:
            out.append(
                Finding(
                    "info",
                    "unconsumed-external",
                    node,
                    link.name,
                    f"consumer {consumer_name} is not in this repository",
                )
            )
        else:
            who = f"{consumer_name} exists but" if consumer_name else "nobody"
            out.append(
                Finding("warning", "unconsumed", node, link.name, f"{who} never waits for it")
            )
    elif parsed is not None:
        producer_names = {_node_name(n) for n in producers}
        consumer_names = {_node_name(n) for n in link.consumers}
        if parsed[0] not in producer_names or parsed[1] not in consumer_names:
            out.append(
                Finding(
                    "warning",
                    "stale-name",
                    _first(producers),
                    link.name,
                    f"name embeds {parsed[0]} -> {parsed[1]} but the link is "
                    f"{', '.join(sorted(producer_names))} -> {', '.join(sorted(consumer_names))}",
                )
            )
    cleaners = set(link.deleters) | {node for node, _ in link.docond_delete}
    for consumer in link.consumers:
        if consumer not in cleaners:
            out.append(
                Finding(
                    "warning",
                    "never-cleaned",
                    str(consumer),
                    link.name,
                    'waited for but never deleted by the consumer (no OUTCOND SIGN="-")',
                )
            )


def validate(repo: ChainRepo, *, write_index: bool = True) -> ValidateReport:
    """Rebuild the links index (unless told not to) and check the repository.

    Never raises on findings.
    """
    links = rebuild_links(repo) if write_index else load_links(repo)
    findings: list[Finding] = []
    known_names: set[str] = set()
    nodes = 0
    for folder in folder_names(repo):
        data = read_json(repo.folder_file(folder))
        known_names.add(folder)
        nodes += 1
        duplicates: list[str] = []
        for job_id in (str(j) for j in data.get("jobs", [])):
            nodes += 1
            name = job_id.split(DUPLICATE_SEPARATOR)[0]
            known_names.add(name)
            if DUPLICATE_SEPARATOR in job_id and name not in duplicates:
                duplicates.append(name)
        for name in duplicates:
            findings.append(
                Finding(
                    "warning",
                    "duplicate-jobname",
                    f"{folder}/",
                    name,
                    "JOBNAME used by more than one job in the folder",
                )
            )
    for link in links.values():
        _check_link(link, known_names, findings)
    findings.sort(key=lambda f: (_RANK[f.severity], f.code, f.name, f.node))
    return ValidateReport(tuple(findings), links=len(links), nodes=nodes)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def render_text(report: ValidateReport) -> str:
    lines = [
        f"Validation: {_plural(report.links, 'link')}, {_plural(report.nodes, 'node')} — "
        f"{_plural(report.count('error'), 'error')}, "
        f"{_plural(report.count('warning'), 'warning')}, {report.count('info')} info"
    ]
    for finding in report.findings:
        lines.append(
            f"[{finding.severity.upper():7}] {finding.code:20} {finding.node:40} "
            f"{finding.name} — {finding.message}"
        )
    return "\n".join(lines) + "\n"


def render_markdown(report: ValidateReport) -> str:
    lines = [
        "# Validation report",
        "",
        f"{_plural(report.links, 'link')}, {_plural(report.nodes, 'node')}.",
        "",
        "| severity | count |",
        "|---|---|",
        *(f"| {s} | {report.count(s)} |" for s in SEVERITIES),
        "",
        "| severity | code | node | name | message |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {f.severity} | {f.code} | {f.node} | {f.name} | {f.message} |" for f in report.findings
    )
    return "\n".join(lines) + "\n"
