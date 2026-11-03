"""What can be done about each validation finding: named fixes, each one a change-set operation.

A fix is data: an operation of :data:`controlm_chain_admin.core.refactor.OPERATIONS` with its
parameters (several at once through ``batch``), a ``kind`` shared by the same fix of every finding
(to resolve many findings in one go), a ``label`` with this finding's names and an explanation.
Nothing is written here: the fix goes through the usual preview and apply.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
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
from controlm_chain_admin.core.validate import (
    Finding,
    NameRules,
    copy_stem,
    embeds_endpoints,
    parse_condition_name,
    replaced_words,
    resources,
    similar_names,
    validate,
)

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
    repo: ChainRepo | None = None
    names: NameRules | None = None
    similar: dict[str, list[Link]] = field(default_factory=dict)  # stem -> similar conditions


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
    return _Index(
        links,
        standard_names(links),
        used,
        by_name,
        jobs,
        repo,
        NameRules.of(repo),
        similar_names(links),
    )


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
    parsed = parse_condition_name(standard)
    if parsed is None or not embeds_endpoints(parsed, link.all_producers, link.consumers):
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


def _numbering_similar(finding: Finding, index: _Index) -> list[Fix]:
    stem, family = finding.name, index.similar.get(finding.name, [])
    kept = [link for link in family if link.external]
    taken = {name.upper() for name in index.used}
    renames: list[tuple[Link, str]] = []
    number = 1
    for link in (link for link in family if not link.external):
        while True:
            name = f"{stem}{number}"
            if copy_stem(name) != name:  # the stem ends with -<letter>: keep the number apart
                name = f"{stem}_{number}"
            number += 1
            if name.upper() not in taken:
                break
        renames.append((link, name))
    if not renames:
        return []
    op, params = _operation(
        [("rename-link", {"link": link.id, "name": name}) for link, name in renames]
    )
    explanation = (
        f"Gives each condition the common name with a number at the end ({stem}1, {stem}2…), "
        "in every job that uses it, so that no two names differ only by a suffix or by case."
    )
    explanation += "".join(
        f" {link.name} keeps its name: a job outside this repository may use it." for link in kept
    )
    return [
        Fix(
            "number-similar",
            "Number the similar names",
            "; ".join(f"rename {link.name} -> {name}" for link, name in renames),
            explanation,
            op,
            params,
            tuple(
                Effect(str(node), "change", "condition name", link.name, name)
                for link, name in renames
                for node in _users(link)
            ),
        )
    ]


def _rename_to(link: Link, name: str, index: _Index, kind: str, title: str, why: str) -> list[Fix]:
    if name == link.name or index.used.get(name, link.id) != link.id:
        return []  # nothing to do, or the name belongs to another link
    return [
        Fix(
            kind,
            title,
            f"rename {link.name} -> {name}",
            why,
            "rename-link",
            {"link": link.id, "name": name},
            tuple(
                Effect(str(n), "change", "condition name", link.name, name) for n in _users(link)
            ),
        )
    ]


def _name_fixes(finding: Finding, index: _Index) -> list[Fix]:
    rules = index.names
    if rules is None:
        return []
    link = index.links.get(finding.link)
    if finding.code == "foreign-letter" and link is not None:
        return _rename_to(
            link, rules.neutral(link.name), index, "remove-letter",
            "Remove the environment letter",
            "Renames the condition without the letter: on export every environment gets its "
            "own letter, in every job that uses it.",
        )  # fmt: skip
    if finding.code == "letter-for-p" and link is not None:
        return _rename_to(
            link, rules.with_prefix(link.name), index, "restore-prefix",
            f"Put {rules.prefix} back",
            f"Renames the condition with {rules.prefix} where an environment letter replaced its "
            f"first character; on export each environment adds its letter in front.",
        )  # fmt: skip
    if finding.code == "replaced-first-letter" and link is not None:
        name = link.name
        for token, word in replaced_words(name, link, rules):
            name = re.sub(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", word, name)
        return _rename_to(
            link, name, index, "restore-word", "Restore the word",
            "Renames the condition with the words of the jobs it links.",
        )  # fmt: skip
    if finding.code == "letter-for-p" and finding.node and index.repo is not None:
        fixed = rules.with_prefix(finding.name)
        return [
            Fix(
                "restore-prefix",
                f"Put {rules.prefix} back",
                f"MEMNAME {finding.name} -> {fixed}",
                f"Sets MEMNAME to {fixed}; on export each environment adds its letter in front. "
                "MEMNAME is the script Control-M runs: check that the script of that name exists "
                "in every environment first.",
                "set-attributes",
                {"node": finding.node, "changes": {"MEMNAME": fixed}},
                (Effect(finding.node, "change", "MEMNAME", finding.name, fixed),),
            )
        ]
    if finding.code == "foreign-resource" and index.repo is not None:
        rule = index.repo.config.letter_rule
        fixed = rules.neutral(finding.name)
        leading = rule.leading_pattern()
        if not (leading and leading.match(fixed)) and len(rule.bare_pattern().findall(fixed)) > 1:
            return []  # its inner prefix would get a letter too: needs letter_rule.leading_only
        folder, _, job = finding.node.partition("/")
        path = index.repo.job_file(folder, job) if job else index.repo.folder_file(folder)
        data = deepcopy(read_json(path))
        for _, item in resources(data):
            if str(item.get("NAME", "")).removeprefix("literal:") == finding.name:
                item["NAME"] = fixed
        return [
            Fix(
                "remove-letter",
                "Remove the environment letter",
                f"resource {finding.name} -> {fixed}",
                f"Uses {fixed}: on export each environment gets its own resource "
                f"({fixed} with its letter in front).",
                "replace-node",
                {"node": finding.node, "data": data},
                (Effect(finding.node, "change", "resource", finding.name, fixed),),
            )
        ]
    return []


def _fixes(finding: Finding, index: _Index) -> list[Fix]:
    if finding.code == "duplicate-jobname":
        return _numbering(finding, index)
    if finding.code == "similar-names":
        return _numbering_similar(finding, index)
    if finding.code in (
        "foreign-letter",
        "letter-for-p",
        "replaced-first-letter",
        "foreign-resource",
    ):
        return _name_fixes(finding, index)
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
