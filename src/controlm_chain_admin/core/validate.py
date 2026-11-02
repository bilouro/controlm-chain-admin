"""Validation of a chain repository: graph consistency, naming, duplicates.

Severities: ``error`` (a chain is broken inside the repository), ``warning`` (something is
inconsistent and probably unintended), ``info`` (worth knowing, no action implied, e.g. a link
whose other end lives outside this repository).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
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
    link: str = ""  # id of the link the finding is about, "" when it is not about a link

    def to_json(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "node": self.node,
            "name": self.name,
            "message": self.message,
            "link": self.link,
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


def embeds_endpoints(
    parsed: tuple[str, str], producers: Iterable[NodeRef], consumers: Iterable[NodeRef]
) -> bool:
    """Whether a parsed condition name names the link's producer and consumer.

    The producer may carry its folder as a prefix (``F_A-B_OK``): that is the standard name
    when two links would otherwise collide.
    """
    producer_names: set[str] = set()
    for node in producers:
        producer_names |= {_node_name(node), f"{node.folder}_{_node_name(node)}"}
    return parsed[0] in producer_names and parsed[1] in {_node_name(n) for n in consumers}


def _first(*groups: tuple[NodeRef, ...]) -> str:
    for group in groups:
        if group:
            return str(group[0])
    return ""


def _check_link(link: Link, known_names: set[str], found: list[Finding]) -> None:
    out: list[Finding] = []
    _check_link_findings(link, known_names, out)
    found.extend(replace(f, link=link.id) for f in out)


def _check_link_findings(link: Link, known_names: set[str], out: list[Finding]) -> None:
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
    elif parsed is not None and not embeds_endpoints(parsed, producers, link.consumers):
        producer_names = ", ".join(sorted({_node_name(n) for n in producers}))
        consumer_names = ", ".join(sorted({_node_name(n) for n in link.consumers}))
        out.append(
            Finding(
                "warning",
                "stale-name",
                _first(producers),
                link.name,
                f"name embeds {parsed[0]} -> {parsed[1]} but the link is "
                f"{producer_names} -> {consumer_names}",
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
    rules = NameRules.of(repo)
    if rules is not None:
        _check_names(repo, links, rules, findings)
    findings.sort(key=lambda f: (_RANK[f.severity], f.code, f.name, f.node))
    return ValidateReport(tuple(findings), links=len(links), nodes=nodes)


# ---------------------------------------------------------------- dirty names

_RESOURCE_TAGS = ("QUANTITATIVE", "CONTROL")
_WORD = re.compile(r"[-_]")
_MIN_WORD = 3


@dataclass(frozen=True)
class NameRules:
    """The environment letters and prefixes, to find names an environment left its mark on."""

    letters: dict[str, str]  # letter -> environment
    foreign: re.Pattern[str]  # a letter in front of a prefix (none is left after the import)
    in_place: re.Pattern[str] | None  # a letter in place of the first character of the prefix
    prefix: str  # the application prefix that in_place is about, e.g. P54

    @classmethod
    def of(cls, repo: ChainRepo) -> NameRules | None:
        rule = repo.config.letter_rule
        if not rule.enabled:
            return None
        letters = {
            letter: env
            for env in repo.config.environments
            if repo.env_file(env).is_file()
            for letter in (repo.load_env(env).letter,)
        }
        if not letters:
            return None
        prefixes = "|".join(re.escape(p) for p in sorted(rule.prefixes, key=len, reverse=True))
        chars = "".join(sorted(letters))
        foreign = re.compile(rf"(?<![A-Za-z0-9])(?P<letter>[{chars}])(?={prefixes})")
        codes = [p for p in rule.prefixes if p[:1].isalpha() and p[1:].isdigit()]
        in_place = None
        prefix = codes[0] if codes else ""
        if prefix:
            others = "".join(sorted(set(letters) - {prefix[0]}))
            if others:
                in_place = re.compile(
                    rf"(?<![A-Za-z0-9])(?P<letter>[{others}])(?={re.escape(prefix[1:])})"
                )
        return cls(letters, foreign, in_place, prefix)

    def neutral(self, value: str) -> str:
        """The value without the environment letters in front of its prefixes."""
        return self.foreign.sub("", value)

    def with_prefix(self, value: str) -> str:
        """The value with the application prefix where a letter replaced its first character."""
        if self.in_place is None:
            return value
        return self.in_place.sub(self.prefix[0], value)


def replaced_words(name: str, link: Link, rules: NameRules) -> list[tuple[str, str]]:
    """(word in the name, word of an endpoint) where the name has the endpoint's word with its
    first letter replaced by an environment letter (``PIRIUS`` for ``SIRIUS``)."""
    words = {
        w
        for node in (*link.all_producers, *link.consumers)
        for w in _WORD.split(_node_name(node))
        if len(w) >= _MIN_WORD
    }
    found: list[tuple[str, str]] = []
    for token in _WORD.split(name):
        if len(token) < _MIN_WORD or token in words or token[0] not in rules.letters:
            continue
        if rules.in_place is not None and rules.in_place.match(token):
            continue  # a letter in place of the prefix's first character: letter-for-p
        match = next((w for w in sorted(words) if w[1:] == token[1:] and w[0] != token[0]), None)
        if match and (token, match) not in found:
            found.append((token, match))
    return found


def _first_user(link: Link) -> str:
    users = (*link.all_producers, *link.consumers, *link.deleters)
    return str(users[0]) if users else ""


def _check_names(
    repo: ChainRepo, links: dict[str, Link], rules: NameRules, found: list[Finding]
) -> None:
    for link in links.values():
        name = link.name.removeprefix("literal:")
        node = _first_user(link)
        letter = rules.foreign.search(name)
        if letter:
            env = rules.letters[letter["letter"]]
            found.append(
                Finding(
                    "warning", "foreign-letter", node, link.name,
                    f"the condition name carries the letter {letter['letter']} of {env}: names "
                    "have no letter in the repository, and a wrong one can join the chains of "
                    "two environments",
                    link.id,
                )
            )  # fmt: skip
        place = rules.in_place.search(name) if rules.in_place else None
        if place:
            env = rules.letters[place["letter"]]
            found.append(
                Finding(
                    "warning", "letter-for-p", node, link.name,
                    f"the letter {place['letter']} of {env} replaces the {rules.prefix[0]} of "
                    f"{rules.prefix} in the condition name",
                    link.id,
                )
            )  # fmt: skip
        for token, word in replaced_words(name, link, rules):
            found.append(
                Finding(
                    "warning", "replaced-first-letter", node, link.name,
                    f"{token} looks like {word} of the jobs it links, with its first letter "
                    f"replaced by {token[0]} (the letter of {rules.letters[token[0]]})",
                    link.id,
                )
            )  # fmt: skip
    for folder in folder_names(repo):
        data = read_json(repo.folder_file(folder))
        nodes = [(f"{folder}/", data)] + [
            (f"{folder}/{j}", read_json(repo.job_file(folder, str(j))))
            for j in data.get("jobs", [])
        ]
        for node, body in nodes:
            _check_node_names(node, body, rules, found)


def resources(body: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(tag, element) of the QUANTITATIVE and CONTROL children, grouped or in an ordered list."""
    found: list[tuple[str, dict[str, Any]]] = []
    for tag in _RESOURCE_TAGS:
        items = body.get(tag)
        found += (
            [(tag, item) for item in items if isinstance(item, dict)]
            if isinstance(items, list)
            else []
        )
    for item in body.get("children", []) if isinstance(body.get("children"), list) else []:
        if isinstance(item, dict) and item.get("tag") in _RESOURCE_TAGS:
            found.append((str(item["tag"]), item))
    return found


def _check_node_names(
    node: str, body: dict[str, Any], rules: NameRules, found: list[Finding]
) -> None:
    for tag, item in resources(body):
        value = str(item.get("NAME", "")).removeprefix("literal:")
        letter = rules.foreign.search(value)
        if letter:
            env = rules.letters[letter["letter"]]
            found.append(
                Finding(
                    "error", "foreign-resource", node, value,
                    f"the job uses the resource {value} of {env} ({tag}): it waits for, or "
                    "holds, another environment's resource",
                )
            )  # fmt: skip
    memname = str(body.get("MEMNAME", "")).removeprefix("literal:")
    place = rules.in_place.search(memname) if rules.in_place and memname else None
    if place:
        env = rules.letters[place["letter"]]
        found.append(
            Finding(
                "warning", "letter-for-p", node, memname,
                f"MEMNAME: the letter {place['letter']} of {env} replaces the "
                f"{rules.prefix[0]} of {rules.prefix}",
            )
        )  # fmt: skip


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
