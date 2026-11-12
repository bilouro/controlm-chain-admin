"""Validation of a chain repository: graph consistency, naming, duplicates.

Severities: ``error`` (a chain is broken inside the repository), ``warning`` (something is
inconsistent and probably unintended), ``info`` (worth knowing, no action implied, e.g. a link
whose other end lives outside this repository).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from controlm_chain_admin.core.links import (
    Link,
    NodeRef,
    folder_names,
    load_links,
    rebuild_links,
)
from controlm_chain_admin.core.ops import DUPLICATE_SEPARATOR, ORIGINALS_KEY
from controlm_chain_admin.core.repo import ChainRepo, read_json

SEVERITIES = ("error", "warning", "info")
_RANK = {severity: index for index, severity in enumerate(SEVERITIES)}

_NAME_PATTERNS = (
    re.compile(r"^(?P<a>[^-]+)-(?P<b>[^-]+)_OK\d*$", re.IGNORECASE),  # A-B_OK2: numbered
    re.compile(r"^(?P<a>[^-]+)-TO-(?P<b>[^-]+)$"),
)


@dataclass(frozen=True)
class Explanation:
    """What a code of the report means, in three sentences for whoever reads a finding."""

    looks_for: str  # what the check looks for
    why: str  # why it matters
    fix: str  # what its fix does, and what follows from it

    def to_json(self) -> dict[str, str]:
        return {"looks_for": self.looks_for, "why": self.why, "fix": self.fix}


EXPLANATIONS: dict[str, Explanation] = {
    "dangling": Explanation(
        "A job waits for a condition that nobody emits, and the name of the condition names a "
        "job that is in the repository.",
        "The job that waits never starts by itself: the job it names does not release it.",
        "Either the named job starts emitting the condition (one line added to that job), or "
        "the waiting job stops waiting for it.",
    ),
    "dangling-unknown": Explanation(
        "A job waits for a condition that nobody emits, and the name does not say who should.",
        "The job that waits never starts by itself, and nothing here tells where the "
        "condition should come from.",
        "The waiting job stops waiting for it; when it comes from another application, leave "
        "it as it is.",
    ),
    "dangling-external": Explanation(
        "A job waits for a condition that nobody here emits, named after a job that is not in "
        "this repository.",
        "Usually nothing is wrong: another application emits it. It is listed so that a "
        "mistyped name does not hide among them.",
        "None is needed when the other application exists; the waiting job can stop waiting "
        "for it otherwise.",
    ),
    "unconsumed": Explanation(
        "A job emits a condition that nobody waits for, though the name names a job that is "
        "in the repository, or nobody at all.",
        "The link the name promises does not exist: the named job runs without waiting for "
        "this one.",
        "Either the named job starts waiting for the condition, or the emitting job stops "
        "emitting it.",
    ),
    "unconsumed-external": Explanation(
        "A job emits a condition that nobody here waits for, named after a job that is not in "
        "this repository.",
        "Usually nothing is wrong: another application waits for it.",
        "None is needed when the other application exists; the job can stop emitting it "
        "otherwise.",
    ),
    "stale-name": Explanation(
        "The name of a condition names two jobs, and the condition links two others.",
        "It works, and it misleads whoever reads it: the name tells of a chain that is not "
        "the one that runs. A job renamed or a condition reused leaves it so.",
        "The condition is renamed after the jobs it really links, in every job that uses it, "
        "other folders included.",
    ),
    "non-standard-name": Explanation(
        "The name of a condition is not made of the two jobs it links (PRODUCER-CONSUMER_OK "
        "or PRODUCER-TO-CONSUMER).",
        "Nothing fails. The names alone do not tell who releases whom.",
        "The condition is renamed to the standard name, in every job that uses it.",
    ),
    "never-cleaned": Explanation(
        "A job waits for a condition and never deletes it once it ran.",
        "The condition stays in Control-M and can release the next run of the job before its "
        "predecessor ran again.",
        "The waiting job gets one line that deletes the condition after use.",
    ),
    "duplicate-jobname": Explanation(
        "Two or more jobs of one folder have the same JOBNAME, and the repository was told "
        "not to number them.",
        "The name does not tell them apart: a condition named after it could be of either.",
        "The second and later ones get a number at the end (NAME2, NAME3); the conditions "
        "that carry the name and belong to them follow.",
    ),
    "repeated-jobname": Explanation(
        "A JOBNAME used by more than one job anywhere in the repository, in one folder or in "
        "several. The import gave the later ones a number (NAME2, NAME3) to tell them apart; "
        "Control-M still has the one name for all of them.",
        "A name tells which job is meant only when one job has it: in a condition name, in a "
        "search, in what somebody says on the phone at night.",
        "The numbered name becomes the job's JOBNAME in Control-M too; the conditions that "
        "carry the old name and belong to this job follow, in every job that uses them.",
    ),
    "similar-names": Explanation(
        "Several conditions whose names differ only by a suffix a copy appended, or by upper "
        "and lower case.",
        "They are different conditions in Control-M and look like one: a job is easily made "
        "to wait for the wrong one.",
        "Each one gets the common name with a number at the end, in every job that uses it. "
        "A name a job outside the repository may use is kept.",
    ),
    "foreign-letter": Explanation(
        "The name of a condition carries the letter of an environment.",
        "Names have no letter in the repository: each environment's is put in at the export. "
        "A letter left in a name can join the chains of two environments.",
        "The letter is taken out of the name, in every job that uses the condition.",
    ),
    "letter-for-p": Explanation(
        "The letter of an environment took the place of the first letter of the application "
        "prefix, in a condition name or in a MEMNAME.",
        "The name is of no environment any more: the export cannot put the right letter in "
        "front of it.",
        "The prefix is put back as it should be.",
    ),
    "replaced-first-letter": Explanation(
        "A word of a condition name looks like a word of the jobs it links, with its first "
        "letter replaced by the letter of an environment.",
        "Somebody adapted the name to an environment by hand, once; the other environments "
        "have another name for the same link.",
        "The word gets its own first letter back, in every job that uses the condition.",
    ),
    "foreign-resource": Explanation(
        "A job uses a resource whose name carries the letter of another environment.",
        "The job waits for, or holds, the resource of another environment: it can stop that "
        "environment's jobs, or never get the resource here.",
        "The letter is taken out of the resource name of that job.",
    ),
}
#: Every code a finding can have, in the order the report explains them.
CODES: tuple[str, ...] = tuple(EXPLANATIONS)

#: What a copy of a chain gets appended to its condition names to keep them apart (``-U26``).
_COPY_SUFFIX = re.compile(r"(?:-[A-Z]\d+)+$", re.IGNORECASE)


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
            "explanations": self.explanations(),
        }

    def explanations(self) -> dict[str, dict[str, str]]:
        """What each code of this report means, in the order the report explains them."""
        present = {f.code for f in self.findings}
        return {code: EXPLANATIONS[code].to_json() for code in CODES if code in present}


def parse_condition_name(name: str) -> tuple[str, str] | None:
    """Split ``A-B_OK`` or ``A-TO-B`` into (producer name, consumer name); None otherwise.

    A number after ``_OK`` (``A-B_OK2``, how similar names are told apart) is not part of B.
    """
    for pattern in _NAME_PATTERNS:
        match = pattern.match(name)
        if match:
            return match.group("a"), match.group("b")
    return None


def _node_name(node: NodeRef) -> str:
    """The name a condition would embed for this node: the job name, or the folder name."""
    base = node.job if node.job is not None else node.folder
    return base.split(DUPLICATE_SEPARATOR)[0]


def _names(node: NodeRef, originals: Mapping[NodeRef, str]) -> set[str]:
    """The names a condition may embed for this node: its own, and the JOBNAME it has in
    Control-M when the import numbered it."""
    names = {_node_name(node)}
    if node in originals:
        names.add(originals[node])
    return names


def embeds_endpoints(
    parsed: tuple[str, str],
    producers: Iterable[NodeRef],
    consumers: Iterable[NodeRef],
    originals: Mapping[NodeRef, str] | None = None,
) -> bool:
    """Whether a parsed condition name names the link's producer and consumer.

    The producer may carry its folder as a prefix (``F_A-B_OK``): that is the standard name
    when two links would otherwise collide. ``originals`` gives the JOBNAME a numbered job
    has in Control-M: a condition named after it names that job.
    """
    originals = originals or {}
    producer_names: set[str] = set()
    for node in producers:
        for name in _names(node, originals):
            producer_names |= {name, f"{node.folder}_{name}"}
    consumer = parsed[1]
    consumer_names = {name for n in consumers for name in _names(n, originals)}
    numbered = any(  # A-TO-B2: B numbered among similar names
        consumer.startswith(c) and consumer[len(c) :].isdigit() for c in consumer_names
    )
    return parsed[0] in producer_names and (consumer in consumer_names or numbered)


def describes(link: Link) -> bool:
    """Whether the name is made of the link's own producer and consumer, in any case."""
    producers = link.all_producers
    if len(producers) != 1 or len(link.consumers) != 1:
        return False
    producer, consumer = _node_name(producers[0]), _node_name(link.consumers[0])
    own = (
        f"{producer}-{consumer}_OK",
        f"{producers[0].folder}_{producer}-{consumer}_OK",
        f"{producer}-TO-{consumer}",
    )
    return link.name.upper() in {name.upper() for name in own}


def copy_stem(name: str) -> str:
    """The name without the suffixes a copy appended to it (``A-B_OK-U26-U31`` -> ``A-B_OK``)."""
    return _COPY_SUFFIX.sub("", name)


def similar_names(links: Mapping[str, Link]) -> dict[str, list[Link]]:
    """Conditions whose names differ only by copy suffixes or by case, by their common stem.

    The members are sorted shortest name first (the original before its copies) and the stem is
    the first one's. A family whose every name is made of its own jobs is left out: those names
    only look alike because the jobs do (``A-TO-LOAD-S1`` and ``A-TO-LOAD-S2``).
    """
    groups: dict[str, list[Link]] = {}
    for link in links.values():
        groups.setdefault(copy_stem(link.name).upper(), []).append(link)
    families: dict[str, list[Link]] = {}
    for same in groups.values():
        if len(same) < 2 or all(describes(link) for link in same):
            continue
        same.sort(key=lambda link: (len(link.name), link.name))
        families[copy_stem(same[0].name)] = same
    return families


def _first(*groups: tuple[NodeRef, ...]) -> str:
    for group in groups:
        if group:
            return str(group[0])
    return ""


def _check_link(
    link: Link, known_names: set[str], found: list[Finding], originals: Mapping[NodeRef, str]
) -> None:
    out: list[Finding] = []
    _check_link_findings(link, known_names, out, originals)
    found.extend(replace(f, link=link.id) for f in out)


def _check_link_findings(
    link: Link, known_names: set[str], out: list[Finding], originals: Mapping[NodeRef, str]
) -> None:
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
    elif parsed is not None and not embeds_endpoints(parsed, producers, link.consumers, originals):
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


def numbered_jobs(repo: ChainRepo) -> dict[NodeRef, str]:
    """The jobs the import numbered because their JOBNAME is repeated: job -> the JOBNAME it
    has in Control-M (and in the export, unless asked for the numbered names)."""
    found: dict[NodeRef, str] = {}
    for folder in folder_names(repo):
        meta = repo.folder_meta_file(folder)
        if not meta.is_file():
            continue
        for job_id, original in read_json(meta).get(ORIGINALS_KEY, {}).items():
            if job_id != original:
                found[NodeRef(folder, str(job_id))] = str(original)
    return found


def _repeated(
    originals: Mapping[NodeRef, str], holders: Mapping[str, Sequence[NodeRef]]
) -> list[Finding]:
    """One finding per numbered job: who else has its JOBNAME."""
    families: dict[str, list[NodeRef]] = {}
    for node, original in originals.items():
        families.setdefault(original, list(holders.get(original, []))).append(node)
    findings = []
    for node, original in originals.items():
        family = families[original]
        findings.append(
            Finding(
                "warning",
                "repeated-jobname",
                str(node),
                original,
                f"JOBNAME {original} is the name of {len(family)} jobs "
                f"({', '.join(str(n) for n in family)}): the repository calls this one "
                f"{node.job} to tell them apart, Control-M still calls it {original}",
            )
        )
    return findings


def validate(repo: ChainRepo, *, write_index: bool = True) -> ValidateReport:
    """Rebuild the links index (unless told not to) and check the repository.

    Never raises on findings.
    """
    links = rebuild_links(repo) if write_index else load_links(repo)
    findings: list[Finding] = []
    known_names: set[str] = set()
    holders: dict[str, list[NodeRef]] = {}  # job id -> the jobs called so, by folder
    nodes = 0
    for folder in folder_names(repo):
        data = read_json(repo.folder_file(folder))
        known_names.add(folder)
        nodes += 1
        duplicates: list[str] = []
        for job_id in (str(j) for j in data.get("jobs", [])):
            nodes += 1
            holders.setdefault(job_id, []).append(NodeRef(folder, job_id))
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
    originals = numbered_jobs(repo)
    known_names.update(originals.values())
    findings.extend(_repeated(originals, holders))
    for link in links.values():
        _check_link(link, known_names, findings, originals)
    for stem, family in similar_names(links).items():
        findings.append(
            Finding(
                "warning",
                "similar-names",
                _first_user(family[0]),
                stem,
                f"{len(family)} conditions differ only by a suffix or by case: "
                f"{', '.join(link.name for link in family)}; a job is easily made to wait for "
                "the wrong one",
                family[0].id,
            )
        )
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
