"""What can be done about each validation finding: named fixes, each one a change-set operation.

A fix is data: an operation of :data:`controlm_chain_admin.core.refactor.OPERATIONS` with its
parameters (several at once through ``batch``), a ``kind`` shared by the same fix of every finding
(to resolve many findings in one go), a ``label`` with this finding's names and an explanation.
Nothing is written here: the fix goes through the usual preview and apply.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from controlm_chain_admin.core.links import (
    DUPLICATE_SEPARATOR,
    Link,
    NodeRef,
    folder_names,
    load_links,
    standard_names,
)
from controlm_chain_admin.core.repo import ChainRepo, read_json
from controlm_chain_admin.core.validate import Finding, parse_condition_name, validate

_EXTERNAL = ("dangling-external", "unconsumed-external")


@dataclass(frozen=True)
class Effect:
    """One line of a job that a fix adds, removes or changes: what the job will look like."""

    node: str
    action: str  # add | remove | change
    element: str  # e.g. 'OUTCOND A-B_OK SIGN="+"', "INCOND A-B_OK", "condition name", "JOBNAME"
    before: str | None = None  # for a change
    after: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "action": self.action,
            "element": self.element,
            "before": self.before,
            "after": self.after,
        }


def _emission(name: str, sign: str) -> str:
    return f'OUTCOND {name} SIGN="{sign}"'


@dataclass(frozen=True)
class Fix:
    kind: str  # emit | stop-waiting | wait | stop-emitting | add-cleanup | standard-name | ...
    title: str  # the same for every finding of a kind, to choose a fix for many at once
    label: str  # what this fix does to this finding, with the names
    explanation: str
    op: str
    params: dict[str, Any] = field(default_factory=dict)
    effects: tuple[Effect, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "label": self.label,
            "explanation": self.explanation,
            "op": self.op,
            "params": self.params,
            "effects": [e.to_json() for e in self.effects],
        }


def _operation(changes: Sequence[tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any]]:
    if len(changes) == 1:
        return changes[0]
    return "batch", {"changes": [{"op": op, "params": params} for op, params in changes]}


def _nodes(nodes: Sequence[NodeRef]) -> str:
    return ", ".join(str(n) for n in nodes) if len(nodes) <= 2 else f"{len(nodes)} jobs"


@dataclass
class _Index:
    links: dict[str, Link]
    standards: dict[str, str]
    used: dict[str, str]  # export name -> link id
    by_name: dict[str, list[NodeRef]]  # job name (without ~n) or folder name -> nodes
    jobs: dict[str, list[str]]  # folder -> job ids


def _index(repo: ChainRepo) -> _Index:
    links = load_links(repo)
    by_name: dict[str, list[NodeRef]] = {}
    jobs: dict[str, list[str]] = {}
    for folder in folder_names(repo):
        by_name.setdefault(folder, []).append(NodeRef(folder))
        ids = [str(j) for j in read_json(repo.folder_file(folder)).get("jobs", [])]
        jobs[folder] = ids
        for job in ids:
            by_name.setdefault(job.split(DUPLICATE_SEPARATOR)[0], []).append(NodeRef(folder, job))
    used = {link.name: link.id for link in links.values()}
    return _Index(links, standard_names(links), used, by_name, jobs)


def _waiting(finding: Finding, link: Link, index: _Index) -> list[Fix]:
    fixes = []
    parsed = parse_condition_name(link.name)
    if finding.code == "dangling" and parsed:
        for producer in index.by_name.get(parsed[0], []):
            if producer in link.consumers:
                continue
            fixes.append(
                Fix(
                    "emit",
                    "Make the named producer emit it",
                    f"{producer} emits {link.name}",
                    f"Adds OUTCOND + {link.name} to {producer}, the job the condition name "
                    "points to: the waiting job then runs after it.",
                    "emit",
                    {"link": link.id, "producer": str(producer)},
                    (Effect(str(producer), "add", _emission(link.name, "+")),),
                )
            )
    if link.consumers:
        op, params = _operation(
            [("unlink", {"link": link.id, "consumer": str(c)}) for c in link.consumers]
        )
        explanation = (
            f"Removes INCOND {link.name} (and its cleanup, OUTCOND -) from the waiting job: it no "
            "longer waits for a condition nobody emits."
        )
        if finding.code in _EXTERNAL:
            explanation += (
                " Only if the producer outside this repository no longer exists: otherwise the "
                "job would start without waiting for it."
            )
        effects: list[Effect] = []
        for consumer in link.consumers:
            effects.append(Effect(str(consumer), "remove", f"INCOND {link.name}"))
            if consumer in link.deleters:
                effects.append(Effect(str(consumer), "remove", _emission(link.name, "-")))
        effects += [Effect(str(p), "remove", _emission(link.name, "+")) for p in link.producers]
        fixes.append(
            Fix(
                "stop-waiting",
                "Stop waiting for it",
                f"{_nodes(link.consumers)} stops waiting for {link.name}",
                explanation,
                op,
                params,
                tuple(effects),
            )
        )
    return fixes


def _emitting(finding: Finding, link: Link, index: _Index) -> list[Fix]:
    fixes = []
    parsed = parse_condition_name(link.name)
    producers = ", ".join(str(p) for p in link.all_producers)
    if finding.code == "unconsumed" and parsed:
        for consumer in index.by_name.get(parsed[1], []):
            if consumer in link.all_producers:
                continue
            fixes.append(
                Fix(
                    "wait",
                    "Make the named consumer wait for it",
                    f"{consumer} waits for {link.name}",
                    f"Adds INCOND {link.name} to {consumer}, the job the condition name points "
                    f"to, and the cleanup (OUTCOND -): it then runs after {producers}.",
                    "link",
                    {"consumer": str(consumer), "link": link.id},
                    (
                        Effect(str(consumer), "add", f"INCOND {link.name}"),
                        Effect(str(consumer), "add", _emission(link.name, "-")),
                    ),
                )
            )
    if link.producers:
        op, params = _operation(
            [("stop-emitting", {"link": link.id, "producer": str(p)}) for p in link.producers]
        )
        explanation = f"Removes OUTCOND + {link.name} from {producers}: no job waits for it."
        if finding.code in _EXTERNAL:
            explanation += " Only if no job outside this repository waits for it."
        fixes.append(
            Fix(
                "stop-emitting",
                "Stop emitting it",
                f"{_nodes(link.producers)} stops emitting {link.name}",
                explanation,
                op,
                params,
                tuple(Effect(str(p), "remove", _emission(link.name, "+")) for p in link.producers),
            )
        )
    return fixes


def _users(link: Link) -> list[NodeRef]:
    """Every node with an element that refers to the link."""
    nodes = {*link.all_producers, *link.consumers, *link.deleters}
    nodes |= {n for n, _ in link.docond_delete}
    return sorted(nodes, key=str)


def _renaming(link: Link, index: _Index) -> list[Fix]:
    standard = index.standards.get(link.id)
    if not standard or standard == link.name or index.used.get(standard, link.id) != link.id:
        return []
    if parse_condition_name(standard) != (
        link.all_producers[0].name,
        link.consumers[0].name,
    ):  # a folder-prefixed name (two links would collide) would still be reported as stale
        return []
    return [
        Fix(
            "standard-name",
            "Rename to the standard name",
            f"rename {link.name} -> {standard}",
            "Renames the condition to <PRODUCER>-<CONSUMER>_OK from the jobs it really links, in "
            "every job that uses it.",
            "rename-link",
            {"link": link.id, "name": standard},
            tuple(
                Effect(str(node), "change", "condition name", link.name, standard)
                for node in _users(link)
            ),
        )
    ]


def _numbering(finding: Finding, index: _Index) -> list[Fix]:
    folder, name = finding.node.rstrip("/"), finding.name
    ids = index.jobs.get(folder, [])
    copies = sorted(
        (j for j in ids if j.startswith(name + DUPLICATE_SEPARATOR)),
        key=lambda j: int(j.rpartition(DUPLICATE_SEPARATOR)[2] or 0),
    )
    taken = {j.split(DUPLICATE_SEPARATOR)[0] for j in ids} | set(ids)
    renames: list[tuple[str, str]] = []
    number = 2
    for copy in copies:
        while f"{name}{number}" in taken:
            number += 1
        renames.append((f"{folder}/{copy}", f"{name}{number}"))
        taken.add(f"{name}{number}")
        number += 1
    if not renames:
        return []
    op, params = _operation([("rename-job", {"node": n, "new_name": new}) for n, new in renames])
    return [
        Fix(
            "number-copies",
            "Number the repeated JOBNAMEs",
            "; ".join(f"rename {n} -> {new}" for n, new in renames),
            f"Gives the second and later jobs called {name} in the folder a numeric suffix "
            f"({name}2, {name}3…); the JOBNAME changes in Control-M too.",
            op,
            params,
            tuple(Effect(n, "change", "JOBNAME", name, new) for n, new in renames),
        )
    ]


def _fixes(finding: Finding, index: _Index) -> list[Fix]:
    if finding.code == "duplicate-jobname":
        return _numbering(finding, index)
    link = index.links.get(finding.link)
    if link is None:
        return []
    if finding.code in ("dangling", "dangling-unknown", "dangling-external"):
        return _waiting(finding, link, index)
    if finding.code in ("unconsumed", "unconsumed-external"):
        return _emitting(finding, link, index)
    if finding.code == "never-cleaned":
        node = finding.node
        return [
            Fix(
                "add-cleanup",
                "Delete it after use",
                f"{node} deletes {link.name} once it ran",
                f"Adds the cleanup OUTCOND - {link.name} to {node}: the condition is removed "
                "after use, so it cannot release the next run by mistake.",
                "update-relation",
                {"link": link.id, "consumer": node, "cleanup": True},
                (Effect(node, "add", _emission(link.name, "-")),),
            )
        ]
    if finding.code in ("stale-name", "non-standard-name"):
        return _renaming(link, index)
    return []


def fixes_for(repo: ChainRepo, findings: Sequence[Finding]) -> list[tuple[Fix, ...]]:
    """The fixes of each finding, in the same order (an empty tuple when there is none)."""
    index = _index(repo)
    return [tuple(_fixes(finding, index)) for finding in findings]


def report_with_fixes(repo: ChainRepo) -> dict[str, Any]:
    """The validation report as JSON, each finding with its fixes."""
    report = validate(repo)
    data = report.to_json()
    for finding, offered in zip(data["findings"], fixes_for(repo, report.findings), strict=True):
        finding["fixes"] = [fix.to_json() for fix in offered]
    return data


def by_kind(
    findings: Sequence[Finding], fixes: Sequence[tuple[Fix, ...]], choice: Mapping[str, str]
) -> tuple[list[dict[str, Any]], list[Finding]]:
    """Changes for ``choice`` (code -> fix kind), and the findings that had no single such fix."""
    changes: list[dict[str, Any]] = []
    skipped: list[Finding] = []
    for finding, offered in zip(findings, fixes, strict=True):
        kind = choice.get(finding.code)
        if kind is None:
            continue
        matching = [f for f in offered if f.kind == kind]
        if len(matching) == 1:
            changes.append({"op": matching[0].op, "params": matching[0].params})
        else:
            skipped.append(finding)
    return changes, skipped
