"""What an export of one environment brings, compared with the neutral repository.

The export is imported into a copy of the repository (letter rule, the known values of the
environment, deduplicated names as the full export gave them) and the copy is compared with the
repository, folder by folder and job by job. What still differs is a decision:

* ``learn``: the repository has ``@{c}`` where the export has a value and ``c`` has no value in
  that environment yet: it is its value there (one decision for every job that agrees);
* ``constant``: the value differs from the one ``c`` has (or is learning) there: an exception for
  this job, the new value of ``c``, or ignore;
* ``value``: a plain attribute or variable differs: a change of the base (every environment),
  an exception for this environment, or ignore;
* ``children``: conditions, ON blocks, resources... differ: change or ignore;
* ``removed``: a job of the repository is not in the export: remove it or keep it.

New folders and jobs come as they are; a value of theirs that no constant explains in that
environment is *unresolved*.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from controlm_chain_admin.core.constants import PLACEHOLDER, Selector
from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.model import XmlDocument
from controlm_chain_admin.core.ops import JOB_TAG, JOBS_KEY, TAG_KEY, import_xml, only_application
from controlm_chain_admin.core.overrides import Override, load_overrides
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.core.xmlio import parse_xml

VARIABLE_TAG = "VARIABLE"
_KNOWN_OPTIONS = ("exception", "set-value", "ignore")
_NAME_ATTRIBUTES = ("FOLDER_NAME", "JOBNAME")


@dataclass(frozen=True)
class Decision:
    id: str
    kind: str  # learn | constant | value | children | removed
    options: tuple[str, ...]
    default: str
    node: str | None = None  # FOLDER/JOB or FOLDER/
    field: str | None = None  # attribute, %%variable, or path inside the children
    constant: str | None = None
    current: str | None = None  # the repository (neutral)
    expected: str | None = None  # the value of the constant in the environment
    incoming: str | None = None  # the export (neutral)
    count: int = 1
    path: tuple[Any, ...] = ()  # inside the children (learnable leaves)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "options": list(self.options),
            "default": self.default,
            "node": self.node,
            "field": self.field,
            "constant": self.constant,
            "current": self.current,
            "expected": self.expected,
            "incoming": self.incoming,
            "count": self.count,
        }


@dataclass(frozen=True)
class FolderIntake:
    name: str
    status: str  # new | changed | same
    jobs_added: tuple[str, ...] = ()
    jobs_removed: tuple[str, ...] = ()
    jobs_changed: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "jobs_added": list(self.jobs_added),
            "jobs_removed": list(self.jobs_removed),
            "jobs_changed": list(self.jobs_changed),
        }


@dataclass(frozen=True)
class Intake:
    env: str
    evidence: tuple[str, ...]
    partial: bool  # some folders of the repository are not in the export
    folders: tuple[FolderIntake, ...]
    decisions: tuple[Decision, ...]
    unresolved: tuple[str, ...]
    warnings: tuple[str, ...]
    skipped: tuple[str, ...]  # folders of other applications

    def to_json(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "evidence": list(self.evidence),
            "partial": self.partial,
            "folders": [f.to_json() for f in self.folders],
            "decisions": [d.to_json() for d in self.decisions],
            "unresolved": list(self.unresolved),
            "warnings": list(self.warnings),
            "skipped": list(self.skipped),
        }


# ---------------------------------------------------------------- environment


def detect_env(repo: ChainRepo, document: XmlDocument) -> tuple[str | None, tuple[str, ...]]:
    """The environment whose letter every folder and job name carries, and the evidence."""
    rule = repo.config.letter_rule
    if not rule.enabled:
        return None, ("the letter rule is off: names do not tell the environment",)
    letters = repo.env_letters()
    by_letter = {letter: env for env, letter in letters.items()}
    prefixes = "|".join(re.escape(p) for p in sorted(rule.prefixes, key=len, reverse=True))
    pattern = re.compile(rf"([A-Z])(?:{prefixes})")
    counts: Counter[str] = Counter()
    for folder in only_application(document, repo.config.application).root.elements():
        for element in (folder, *folder.find_all(JOB_TAG)):
            for attribute in _NAME_ATTRIBUTES:
                match = pattern.match(element.get(attribute) or "")
                if match and match[1] in by_letter:
                    counts[by_letter[match[1]]] += 1
    if not counts:
        return None, ("no folder or job name carries an environment letter",)
    evidence = tuple(
        f"{n} folder and job names carry the letter {letters[env]} of {env}"
        for env, n in counts.most_common()
    )
    return (next(iter(counts)) if len(counts) == 1 else None), evidence


# ---------------------------------------------------------------- comparison


def _strings(data: Mapping[str, Any], volatile: frozenset[str]) -> dict[str, str]:
    return {
        k: v for k, v in data.items() if isinstance(v, str) and k != TAG_KEY and k not in volatile
    }


def _children(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in data.items()
        if not isinstance(v, str) and k not in (JOBS_KEY, VARIABLE_TAG)
    }


def _variables(data: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(v.get("NAME")): str(v.get("VALUE", ""))
        for v in data.get(VARIABLE_TAG, [])
        if isinstance(v, dict)
    }


def _leaves(before: Any, after: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    """Paths where two JSON trees differ; ``("shape",)`` when they are not the same shape."""
    if isinstance(before, dict) and isinstance(after, dict):
        if set(before) != set(after):
            yield ("shape", *path)
            return
        for key in before:
            yield from _leaves(before[key], after[key], (*path, key))
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            yield ("shape", *path)
            return
        for index, (b, a) in enumerate(zip(before, after, strict=True)):
            yield from _leaves(b, a, (*path, index))
    elif before != after:
        yield path if isinstance(before, str) and isinstance(after, str) else ("shape", *path)


def _get(tree: Any, path: tuple[Any, ...]) -> Any:
    for key in path:
        tree = tree[key]
    return tree


def _path_text(path: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for key in path:
        if isinstance(key, int):
            parts[-1] += f"[{key}]"
        elif parts and parts[-1].endswith("]") and key[:1].isupper() and key != key.upper():
            parts.append(key)
        else:
            parts.append(str(key))
    return "/".join(parts)


@dataclass
class _Collector:
    env: str
    known: Mapping[str, str | None]
    overrides: Mapping[str, Override]
    volatile: frozenset[str] = frozenset()
    decisions: list[Decision] = field(default_factory=list)
    contradicted: dict[str, dict[str, list[tuple[str, str, str, tuple[Any, ...], bool]]]] = field(
        default_factory=dict
    )
    learning: dict[str, dict[str, list[tuple[str, str, tuple[Any, ...], bool]]]] = field(
        default_factory=dict
    )

    def classify(
        self,
        node: str,
        name: str,
        current: str | None,
        incoming: str | None,
        *,
        variable: bool = False,
        path: tuple[Any, ...] = (),
    ) -> None:
        exception = self.overrides.get(node)
        if exception is not None:
            values: Mapping[str, Any] = exception.variables if variable else exception.attributes
            if name in values and values[name] == incoming:
                return  # this environment already has it as an exception
        can_except = not path and not (variable and incoming is None)
        whole = PLACEHOLDER.fullmatch(current or "")
        if whole and incoming is not None and not PLACEHOLDER.fullmatch(incoming):
            constant = whole[1]
            if self.known.get(constant) is None:
                learning = self.learning.setdefault(constant, {}).setdefault(incoming, [])
                learning.append((node, name, path, can_except))
                return
            contradicted = self.contradicted.setdefault(constant, {}).setdefault(incoming, [])
            contradicted.append((node, name, current or "", path, can_except))
            return
        self.decisions.append(
            Decision(
                f"{node}@{name}", "value",
                ("change", "exception", "ignore") if can_except else ("change", "ignore"),
                "change", node, name, None, current, None, incoming, path=path,
            )
        )  # fmt: skip

    def compare(self, node: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
        size = self._size()
        b, a = _strings(before, self.volatile), _strings(after, self.volatile)
        for key in [*b, *(k for k in a if k not in b)]:
            if b.get(key) != a.get(key):
                self.classify(node, key, b.get(key), a.get(key))
        bv, av = _variables(before), _variables(after)
        for key in [*bv, *(k for k in av if k not in bv)]:
            if bv.get(key) != av.get(key):
                self.classify(node, key, bv.get(key), av.get(key), variable=True)
        bc, ac = _children(before), _children(after)
        structural = False
        for path in _leaves(bc, ac):
            if path[:1] == ("shape",):
                structural = True
                continue
            current, incoming = _get(bc, path), _get(ac, path)
            if PLACEHOLDER.fullmatch(current) and not PLACEHOLDER.fullmatch(incoming):
                self.classify(node, _path_text(path), current, incoming, path=path)
            else:
                structural = True
        if structural:
            self.decisions.append(
                Decision(f"{node}#children", "children", ("change", "ignore"), "change", node)
            )
        return size != self._size()

    def _size(self) -> int:
        learning = sum(len(s) for by in self.learning.values() for s in by.values())
        contradicted = sum(len(s) for by in self.contradicted.values() for s in by.values())
        return len(self.decisions) + learning + contradicted

    def finish(self, agreeing: Mapping[str, int]) -> list[Decision]:
        """Learn decisions (one per constant), values the whole export contradicts (one per
        constant), then the sites that disagree; ``agreeing`` counts the uses of each constant
        whose value the export confirms."""
        learned: list[Decision] = []
        disagree: list[Decision] = []
        for constant, by_value in self.contradicted.items():
            known = self.known[constant]
            if not agreeing.get(constant) and len(by_value) == 1:
                [(value, sites)] = by_value.items()
                learned.append(
                    Decision(
                        f"value:{constant}", "set-value", ("set-value", "exceptions", "ignore"),
                        "set-value", constant=constant, current="@{" + constant + "}",
                        expected=known, incoming=value, count=len(sites),
                    )
                )  # fmt: skip
                continue
            for value, sites in by_value.items():
                for node, name, current, path, can_except in sites:
                    disagree.append(
                        Decision(
                            f"{node}@{name}", "constant",
                            _KNOWN_OPTIONS if can_except else ("set-value", "ignore"),
                            "exception" if can_except else "ignore",
                            node, name, constant, current, known, value, path=path,
                        )
                    )  # fmt: skip
        for constant, learning in self.learning.items():
            ranked = sorted(learning.items(), key=lambda item: -len(item[1]))
            value, agreeing_sites = ranked[0]
            learned.append(
                Decision(
                    f"learn:{constant}", "learn", ("learn", "ignore"), "learn",
                    constant=constant, current="@{" + constant + "}", incoming=value,
                    count=len(agreeing_sites),
                )
            )  # fmt: skip
            for other, other_sites in ranked[1:]:
                for node, name, path, can_except in other_sites:
                    disagree.append(
                        Decision(
                            f"{node}@{name}", "constant",
                            ("exception", "ignore") if can_except else ("ignore",),
                            "exception" if can_except else "ignore",
                            node, name, constant, "@{" + constant + "}", value, other,
                            path=path,
                        )
                    )  # fmt: skip
        return [*learned, *disagree, *self.decisions]


def _walk(data: Mapping[str, Any], tag: str) -> Iterator[tuple[str, Mapping[str, Any]]]:
    yield tag, data
    for key, value in data.items():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _walk(item, str(item.get(TAG_KEY, key)))


def _unresolved(
    box: ChainRepo, env: str, nodes: list[tuple[str, Mapping[str, Any], str]],
    learned: Mapping[str, str],
) -> list[str]:  # fmt: skip
    """Values of new folders and jobs, bound to a constant, that no constant explains."""
    selectors = box.config.constants
    known = {**{k: v for k, v in box.load_env(env).constants.items() if v}, **learned}
    found: list[str] = []
    for node, data, tag in nodes:
        for element_tag, element in _walk(data, tag):
            for constant, selector in selectors.items():
                if not _bound(selector, element_tag, element):
                    continue
                value = element.get(selector.attribute)
                if not isinstance(value, str) or PLACEHOLDER.search(value):
                    continue
                same = [c for c, s in selectors.items() if s == selector and known.get(c) == value]
                line = (
                    f"{selector.attribute}={value} ({node}): no constant has this value in {env}"
                )
                if not same and line not in found and constant:
                    found.append(line)
    return found


def _bound(selector: Selector, tag: str, element: Mapping[str, Any]) -> bool:
    if selector.inline or selector.attribute not in element:
        return False
    if selector.tag is not None and selector.tag != tag:
        return False
    return all(element.get(k) == v for k, v in selector.where.items())


def analyze(repo: ChainRepo, data: bytes, env: str | None = None) -> Intake:
    """Compare an export with the repository: its environment and every decision it needs."""
    from controlm_chain_admin.core.refactor import _sandbox, _tracked  # avoids an import cycle

    repo = load_repo(repo.root)
    detected, evidence = detect_env(repo, parse_xml(data))
    warnings: list[str] = []
    if env is None:
        if detected is None:
            raise ModelError(
                f"cannot tell the environment of this export ({'; '.join(evidence)}): name it"
            )
        env = detected
    elif detected != env:
        warnings.append(
            f"the names say {detected}, not {env}" if detected else "; ".join(evidence)
        )
    known = repo.load_env(env).constants
    volatile = frozenset(repo.config.volatile_attributes)
    collector = _Collector(env, known, load_overrides(repo, env), volatile)
    folders: list[FolderIntake] = []
    new_nodes: list[tuple[str, Mapping[str, Any], str]] = []
    with _sandbox(_tracked(repo.root)) as box:
        report = import_xml(box, data, env)
        box = load_repo(box.root)
        for name in report.folders:
            after_folder = read_json(box.folder_file(name))
            ids_after = [str(j) for j in after_folder.get(JOBS_KEY, [])]
            if not repo.folder_file(name).is_file():
                folders.append(FolderIntake(name, "new", tuple(ids_after)))
                new_nodes.append((f"{name}/", after_folder, str(after_folder.get(TAG_KEY))))
                new_nodes += [
                    (f"{name}/{j}", read_json(box.job_file(name, j)), JOB_TAG) for j in ids_after
                ]
                continue
            before_folder = read_json(repo.folder_file(name))
            ids_before = [str(j) for j in before_folder.get(JOBS_KEY, [])]
            added = tuple(j for j in ids_after if j not in ids_before)
            removed = tuple(j for j in ids_before if j not in ids_after)
            folder_changed = collector.compare(f"{name}/", before_folder, after_folder)
            changed = tuple(
                j
                for j in ids_after
                if j in ids_before
                and collector.compare(
                    f"{name}/{j}",
                    read_json(repo.job_file(name, j)),
                    read_json(box.job_file(name, j)),
                )
            )
            for job_id in removed:
                collector.decisions.append(
                    Decision(
                        f"{name}/{job_id}#removed", "removed", ("remove", "keep"), "remove",
                        f"{name}/{job_id}",
                    )
                )  # fmt: skip
            new_nodes += [
                (f"{name}/{j}", read_json(box.job_file(name, j)), JOB_TAG) for j in added
            ]
            status = "changed" if added or removed or changed or folder_changed else "same"
            folders.append(FolderIntake(name, status, added, removed, changed))
        agreeing: Counter[str] = Counter()
        for name in report.folders:
            for path in (box.folder_dir(name)).rglob("*.json"):
                agreeing.update(PLACEHOLDER.findall(path.read_text(encoding="utf-8")))
        decisions = collector.finish(agreeing)
        learned = {
            d.constant or "": d.incoming or ""
            for d in decisions
            if d.kind in ("learn", "set-value")
        }
        unresolved = _unresolved(box, env, new_nodes, learned)
    present = {f.parent.name for f in repo.folders_dir.glob("*/folder.json")}
    if report.suspicious_values:
        warnings.append(
            f"{len(report.suspicious_values)} values carry another environment's letter and are "
            f"kept as they are, e.g. {report.suspicious_values[0]}"
        )
    return Intake(
        env, evidence, bool(present - set(report.folders)), tuple(folders), tuple(decisions),
        tuple(unresolved), tuple(warnings), tuple(s.folder for s in report.skipped),
    )  # fmt: skip
