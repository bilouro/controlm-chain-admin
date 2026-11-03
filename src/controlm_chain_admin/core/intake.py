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
* ``children``: conditions, ON blocks, resources... differ in their shape: change or ignore;
* ``group``: the same difference in several jobs (or a machine, user, mail or variable in one):
  a new constant with a value per environment, an exception in every job, a change of the base,
  or ignore. A value with the letter of the environment (``UP77_BATCH`` for ``PP77_BATCH``)
  gives every environment its value; the name of the environment inside a text
  (``[UAT] Load failed``) is an inline constant;
* ``removed``: a job of the repository is not in the export: remove it or keep it (or, in a
  full export, note that this environment does not have it);
* ``added`` (full exports): a folder or job the repository does not have: only in this
  environment, or everywhere;
* ``absent`` (full exports): a folder of the repository the export does not have: note that
  this environment does not have it, or keep it.

An export of more than half of the folders is *full* unless told otherwise. A full export of
an environment other than production leaves production alone by default: exceptions instead
of changes, children ignored, what only it has or lacks noted on the folder or job
(``"envs"``). Folders and jobs that do not exist in the environment are not compared.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from controlm_chain_admin.core.constants import (
    ENVIRONMENT_ATTRIBUTES,
    PLACEHOLDER,
    Selector,
    parse_spec,
    propose_name,
    values_from_pattern,
)
from controlm_chain_admin.core.errors import InvalidChange, ModelError
from controlm_chain_admin.core.membership import ENVS_KEY, belongs, environments_of, with_envs
from controlm_chain_admin.core.model import XmlDocument
from controlm_chain_admin.core.ops import JOB_TAG, JOBS_KEY, TAG_KEY, import_xml, only_application
from controlm_chain_admin.core.overrides import Override, load_overrides, write_overrides
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json, write_json
from controlm_chain_admin.core.xmlio import parse_xml

if TYPE_CHECKING:
    from controlm_chain_admin.core.refactor import ChangeSet

VARIABLE_TAG = "VARIABLE"
_KNOWN_OPTIONS = ("exception", "new", "set-value", "ignore")
_NAME_ATTRIBUTES = ("FOLDER_NAME", "JOBNAME")
_STRUCTURAL_KEYS = ("link", TAG_KEY)  # a condition's link, an element's tag: not a value


@dataclass(frozen=True)
class Site:
    """One place of a value: a node, the attribute, variable or child path, and its base value."""

    node: str
    field: str
    scope: str  # attribute | variable | child
    path: tuple[Any, ...]
    current: str | None
    incoming: str | None
    tag: str | None = None  # the element of a child value (DOMAIL, OUTCOND...)

    @property
    def selector(self) -> Selector:
        """What a constant for this value would replace."""
        if self.scope == "variable":
            return Selector("VALUE", VARIABLE_TAG, {"NAME": self.field})
        if self.scope == "child":
            return Selector(str(self.path[-1]), self.tag)
        return Selector(self.field)

    @property
    def can_except(self) -> bool:
        return self.scope == "attribute" or (
            self.scope == "variable" and self.incoming is not None
        )


@dataclass(frozen=True)
class Decision:
    id: str
    kind: str  # learn | set-value | constant | value | group | children | removed | unmatched
    options: tuple[str, ...]
    default: str
    node: str | None = None  # FOLDER/JOB or FOLDER/
    field: str | None = None  # attribute, %%variable, or path inside the children
    constant: str | None = None
    current: str | None = None  # the repository (neutral)
    expected: str | None = None  # the value of the constant in the environment
    incoming: str | None = None  # the export (neutral)
    count: int = 1
    sites: tuple[Site, ...] = ()  # where the decision applies
    suggested: str | None = None  # the name of a new constant, for the option "new"
    values: Mapping[str, str | None] | None = None  # of the new constant, per environment
    inline: bool = False  # the new constant replaces a token inside a text

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
            "suggested": self.suggested,
            "values": dict(self.values) if self.values is not None else None,
            "inline": self.inline,
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
    full: bool = False  # every folder of the environment, not a delivery of some

    def to_json(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "evidence": list(self.evidence),
            "partial": self.partial,
            "full": self.full,
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
        if not isinstance(v, str) and k not in (JOBS_KEY, VARIABLE_TAG, ENVS_KEY)
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


def _tag(tree: Any, path: tuple[Any, ...]) -> str | None:
    """The tag of the element holding the value at ``path``."""
    element = _get(tree, path[:-1])
    if isinstance(element, dict) and isinstance(element.get(TAG_KEY), str):
        return str(element[TAG_KEY])
    keys = [key for key in path[:-1] if isinstance(key, str)]
    return keys[-1] if keys else None


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
    elsewhere: bool = False  # a full export of another environment than production
    decisions: list[Decision] = field(default_factory=list)
    contradicted: dict[str, dict[str, list[Site]]] = field(default_factory=dict)
    learning: dict[str, dict[str, list[Site]]] = field(default_factory=dict)

    def classify(self, site: Site) -> None:
        exception = self.overrides.get(site.node)
        if exception is not None:
            variable = site.scope == "variable"
            values: Mapping[str, Any] = exception.variables if variable else exception.attributes
            if site.field in values and values[site.field] == site.incoming:
                return  # this environment already has it as an exception
        whole = PLACEHOLDER.fullmatch(site.current or "")
        if whole and site.incoming is not None and not PLACEHOLDER.fullmatch(site.incoming):
            constant = whole[1]
            pending = self.learning if self.known.get(constant) is None else self.contradicted
            pending.setdefault(constant, {}).setdefault(site.incoming, []).append(site)
            return
        options = ("change", "exception", "ignore") if site.can_except else ("change", "ignore")
        default = "change"
        if self.elsewhere:
            default = "exception" if site.can_except else "ignore"
        self.decisions.append(_site_decision(site, "value", options, default))

    def compare(self, node: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
        size = self._size()
        b, a = _strings(before, self.volatile), _strings(after, self.volatile)
        for key in [*b, *(k for k in a if k not in b)]:
            if b.get(key) != a.get(key):
                self.classify(Site(node, key, "attribute", (), b.get(key), a.get(key)))
        bv, av = _variables(before), _variables(after)
        for key in [*bv, *(k for k in av if k not in bv)]:
            if bv.get(key) != av.get(key):
                self.classify(Site(node, key, "variable", (), bv.get(key), av.get(key)))
        bc, ac = _children(before), _children(after)
        structural = False
        for path in _leaves(bc, ac):
            if path[:1] == ("shape",) or path[-1] in _STRUCTURAL_KEYS:
                structural = True
                continue
            current, incoming = _get(bc, path), _get(ac, path)
            site = Site(node, _path_text(path), "child", path, current, incoming, _tag(bc, path))
            if PLACEHOLDER.fullmatch(current) and not PLACEHOLDER.fullmatch(incoming):
                self.classify(site)
            elif PLACEHOLDER.search(current) or PLACEHOLDER.search(incoming):
                structural = True
            else:
                self.classify(site)  # a mail, a subject, a sign...: a value like the others
        if structural:
            default = "ignore" if self.elsewhere else "change"
            self.decisions.append(
                Decision(f"{node}#children", "children", ("change", "ignore"), default, node)
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
        grouped: list[Decision] = []
        disagree: list[Decision] = []
        for constant, by_value in self.contradicted.items():
            known = self.known[constant]
            if not agreeing.get(constant) and len(by_value) == 1:
                [(value, sites)] = by_value.items()
                grouped.append(
                    Decision(
                        f"value:{constant}", "set-value", ("set-value", "exceptions", "ignore"),
                        "set-value", constant=constant, current="@{" + constant + "}",
                        expected=known, incoming=value, count=len(sites), sites=tuple(sites),
                    )
                )  # fmt: skip
                continue
            for sites in by_value.values():
                for site in sites:
                    options = _KNOWN_OPTIONS if site.can_except else ("new", "set-value", "ignore")
                    disagree.append(
                        _site_decision(
                            site, "constant", options,
                            "exception" if site.can_except else "ignore", constant, known,
                        )
                    )  # fmt: skip
        for constant, learning in self.learning.items():
            ranked = sorted(learning.items(), key=lambda item: -len(item[1]))
            value, agreeing_sites = ranked[0]
            grouped.append(
                Decision(
                    f"learn:{constant}", "learn", ("learn", "ignore"), "learn",
                    constant=constant, current="@{" + constant + "}", incoming=value,
                    count=len(agreeing_sites), sites=tuple(agreeing_sites),
                )
            )  # fmt: skip
            for _, other_sites in ranked[1:]:
                for site in other_sites:
                    learned_options: tuple[str, ...] = (
                        ("exception", "new", "ignore") if site.can_except else ("new", "ignore")
                    )
                    disagree.append(
                        _site_decision(
                            site, "constant", learned_options,
                            "exception" if site.can_except else "ignore", constant, value,
                        )
                    )  # fmt: skip
        return [*grouped, *disagree, *self.decisions]


def _site_decision(
    site: Site,
    kind: str,
    options: tuple[str, ...],
    default: str,
    constant: str | None = None,
    expected: str | None = None,
) -> Decision:
    return Decision(
        f"{site.node}@{site.field}", kind, options, default, site.node, site.field, constant,
        site.current, expected, site.incoming, sites=(site,),
    )  # fmt: skip


def _walk(data: Mapping[str, Any], tag: str) -> Iterator[tuple[str, Mapping[str, Any]]]:
    yield tag, data
    for key, value in data.items():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _walk(item, str(item.get(TAG_KEY, key)))


def _elements(
    data: Mapping[str, Any], tag: str
) -> Iterator[tuple[tuple[Any, ...], str, Mapping[str, Any]]]:
    """(path from the node, tag, element) of the node and of every element inside it."""
    yield (), tag, data
    for key, value in data.items():
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    item_tag = str(item.get(TAG_KEY, key))
                    for path, inner_tag, inner in _elements(item, item_tag):
                        yield (key, index, *path), inner_tag, inner


# ---------------------------------------------------------------- groups


@dataclass(frozen=True)
class _Envs:
    names: tuple[str, ...]
    letters: Mapping[str, str]
    displays: Mapping[str, str]
    prefixes: tuple[str, ...]
    base: str | None = None  # the environment the repository's values are known to be from

    @classmethod
    def of(cls, repo: ChainRepo, base: str | None = None) -> _Envs:
        configs = [repo.load_env(env) for env in repo.config.environments]
        return cls(
            tuple(repo.config.environments),
            {c.name: c.letter for c in configs if c.letter},
            {c.name: c.display for c in configs if c.display},
            tuple(repo.config.letter_rule.prefixes),
            base,
        )


def _token(text: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(text)}(?![A-Za-z0-9])")


def _letter_pattern(current: str, incoming: str, env: str, envs: _Envs) -> str | None:
    """``{L}P77_BATCH`` when the two values differ only by the letters of their environments."""
    if not envs.prefixes or env not in envs.letters:
        return None
    alternation = "|".join(re.escape(p) for p in sorted(envs.prefixes, key=len, reverse=True))
    pattern = re.sub(rf"(?<![A-Za-z0-9])[A-Z](?=(?:{alternation}))", "{L}", incoming)
    if "{L}" not in pattern:
        return None
    values = values_from_pattern(pattern, envs.letters)
    if values[env] != incoming:
        return None
    if envs.base is not None:  # the repository's value is the base environment's
        return pattern if values.get(envs.base) == current else None
    return pattern if current in [v for e, v in values.items() if e != env] else None


def _display_swap(site: Site, env: str, envs: _Envs) -> bool:
    """The two texts differ only by the name of their environments (``[PROD]``, ``[UAT]``)."""
    target = envs.displays.get(env)
    if not target or site.current is None or site.incoming is None:
        return False
    for other, display in envs.displays.items():
        token = _token(display)
        if other == env or other != (envs.base or other) or not token.search(site.current):
            continue
        if token.sub(lambda _: target, site.current) == site.incoming:
            return True
    return False


def _groups(
    decisions: list[Decision], env: str, envs: _Envs, taken: set[str], elsewhere: bool = False
) -> list[Decision]:
    """The value decisions that repeat one difference, or concern a value of the environment
    (machine, user, mail, variable), as one decision each, before the others."""
    keyed: dict[tuple[str, str | None, str | None], list[Site]] = {}
    for decision in decisions:
        if decision.kind != "value":
            continue
        [site] = decision.sites
        if site.current is None or site.incoming is None:
            continue
        if PLACEHOLDER.search(site.current) or PLACEHOLDER.search(site.incoming):
            continue
        spec = site.selector.spec
        if _display_swap(site, env, envs):
            keyed.setdefault((spec, None, None), []).append(site)
        else:
            keyed.setdefault((spec, site.current, site.incoming), []).append(site)
    # One value of an environment is one constant: when a value pairs with several others, only
    # the pair most jobs share becomes the constant; the rest are exceptions to it.
    largest: Counter[tuple[str, str, str]] = Counter()
    for (spec, current, incoming), sites in keyed.items():
        if current is None or incoming is None:
            continue
        for side, value in (("current", current), ("incoming", incoming)):
            largest[(spec, side, value)] = max(largest[(spec, side, value)], len(sites))
    groups: list[Decision] = []
    grouped: set[Site] = set()
    for (spec, current, incoming), sites in keyed.items():
        first = sites[0]
        environmental = first.scope == "variable" or first.selector.attribute in (
            ENVIRONMENT_ATTRIBUTES
        )
        inline = current is None
        if not inline and not environmental and len(sites) < 2:
            continue
        except_all = all(site.can_except for site in sites)
        if inline:
            clean = True
            values: dict[str, str | None] = dict(envs.displays)
            name = f"env.{first.selector.attribute.lower()}"
            key = f"group:{spec}~env"
        else:
            assert current is not None and incoming is not None
            clean = largest[(spec, "current", current)] == len(sites) and largest[
                (spec, "incoming", incoming)
            ] == len(sites)
            pattern = _letter_pattern(current, incoming, env, envs)
            if pattern:
                values = dict(values_from_pattern(pattern, envs.letters))
            else:
                values = {e: incoming if e == env else current for e in envs.names}
            name = propose_name(first.selector, current, envs.prefixes)
            key = f"group:{spec}={current}>{incoming}"
        options = (
            *(("new",) if clean else ()),
            *(("exceptions",) if except_all else ()),
            "change",
            "ignore",
        )
        if clean and (inline or environmental):
            default = "new"
        else:
            default = "exceptions" if except_all else ("ignore" if elsewhere else "change")
        suggested = _free_name(name, taken)
        taken.add(suggested)
        groups.append(
            Decision(
                key, "group", options, default, field=spec, constant=suggested,
                current=current, incoming=incoming if not inline else envs.displays[env],
                count=len(sites), sites=tuple(sites), suggested=suggested,
                values=values, inline=inline,
            )
        )  # fmt: skip
        grouped.update(sites)
    rest = [d for d in decisions if not (d.kind == "value" and d.sites[0] in grouped)]
    return [*groups, *rest]


def _unmatched(
    box: ChainRepo, env: str, nodes: list[tuple[str, Mapping[str, Any], str]],
    learned: Mapping[str, str], covered: Iterable[tuple[str, str]] = (),
    taken: Iterable[str] = (),
) -> list[Decision]:  # fmt: skip
    """Values of new folders and jobs, bound to a constant, that no constant has there: create
    a constant, use another one, or keep the value as it is in every environment. A value a
    group would make a constant (``covered``: spec, value) waits for that group."""
    covered = set(covered)
    selectors = box.config.constants
    unique: dict[str, Selector] = {}
    for selector in selectors.values():
        if not selector.inline:
            unique.setdefault(selector.spec, selector)
    known = {**{k: v for k, v in box.load_env(env).constants.items() if v}, **learned}
    found: dict[tuple[str, str], list[Site]] = {}
    for node, data, tag in nodes:
        for path, element_tag, element in _elements(data, tag):
            for spec, selector in unique.items():
                if not _bound(selector, element_tag, element):
                    continue
                value = element.get(selector.attribute)
                if not isinstance(value, str) or PLACEHOLDER.search(value):
                    continue
                if any(s == selector and known.get(c) == value for c, s in selectors.items()):
                    continue
                if (spec, value) in covered:
                    continue
                attribute = selector.attribute
                site = Site(node, attribute, "child" if path else "attribute",
                            (*path, attribute), value, value)  # fmt: skip
                found.setdefault((spec, value), []).append(site)
    prefixes = box.config.letter_rule.prefixes
    taken = {*selectors, *taken}
    decisions = []
    for (spec, value), sites in found.items():
        selector = unique[spec]
        name = _free_name(propose_name(selector, value, prefixes), taken)
        taken.add(name)
        others = tuple(f"use:{c}" for c, s in selectors.items() if s == selector)
        decisions.append(
            Decision(
                f"unmatched:{spec}={value}", "unmatched", ("new", *others, "literal"), "new",
                field=spec, constant=name, incoming=value, count=len(sites),
                sites=tuple(sites), suggested=name,
            )
        )  # fmt: skip
    return decisions


def _free_name(name: str, taken: set[str]) -> str:
    candidate, number = name, 2
    while candidate in taken:
        candidate, number = f"{name}_{number}", number + 1
    return candidate


def _bound(selector: Selector, tag: str, element: Mapping[str, Any]) -> bool:
    if selector.inline or selector.attribute not in element:
        return False
    if selector.tag is not None and selector.tag != tag:
        return False
    return all(element.get(k) == v for k, v in selector.where.items())


def analyze(
    repo: ChainRepo, data: bytes, env: str | None = None, full: bool | None = None
) -> Intake:
    """Compare an export with the repository: its environment and every decision it needs.

    ``full`` tells whether the export has every folder of its environment (default: more than
    half of them)."""
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
    present = {
        f.parent.name for f in repo.folders_dir.glob("*/folder.json") if belongs(read_json(f), env)
    }
    folders: list[FolderIntake] = []
    new_nodes: list[tuple[str, Mapping[str, Any], str]] = []
    with _sandbox(_tracked(repo.root)) as box:
        report = import_xml(box, data, env)
        box = load_repo(box.root)
        exported = set(report.folders)
        if full is None:
            full = len(exported & present) * 2 > len(present) if present else True
        elsewhere = full and env != repo.config.git_rules.production
        collector = _Collector(env, known, load_overrides(repo, env), volatile, elsewhere)
        placed = ("only-here", "everywhere"), "only-here" if elsewhere else "everywhere"
        for name in report.folders:
            after_folder = read_json(box.folder_file(name))
            ids_after = [str(j) for j in after_folder.get(JOBS_KEY, [])]
            if not repo.folder_file(name).is_file():
                folders.append(FolderIntake(name, "new", tuple(ids_after)))
                if full:
                    collector.decisions.append(
                        Decision(f"{name}/#added", "added", *placed, f"{name}/")
                    )
                new_nodes.append((f"{name}/", after_folder, str(after_folder.get(TAG_KEY))))
                new_nodes += [
                    (f"{name}/{j}", read_json(box.job_file(name, j)), JOB_TAG) for j in ids_after
                ]
                continue
            before_folder = read_json(repo.folder_file(name))
            ids_before = [str(j) for j in before_folder.get(JOBS_KEY, [])]
            added = tuple(j for j in ids_after if j not in ids_before)
            removed = tuple(
                j
                for j in ids_before
                if j not in ids_after and belongs(read_json(repo.job_file(name, j)), env)
            )
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
            gone: tuple[tuple[str, ...], str] = (
                (("not-here", "remove", "keep"), "not-here" if elsewhere else "remove")
                if full
                else (("remove", "keep"), "remove")
            )
            for job_id in removed:
                collector.decisions.append(
                    Decision(f"{name}/{job_id}#removed", "removed", *gone, f"{name}/{job_id}")
                )
            for job_id in added if full else ():
                collector.decisions.append(
                    Decision(f"{name}/{job_id}#added", "added", *placed, f"{name}/{job_id}")
                )
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
        taken = set(box.config.constants)
        for decision in decisions:
            if decision.kind == "constant" and decision.constant:
                name = _free_name(f"{decision.constant}_2", taken)
                taken.add(name)
                decisions[decisions.index(decision)] = replace(decision, suggested=name)
        production = repo.config.git_rules.production
        envs = _Envs.of(repo, production if elsewhere else None)
        decisions = _groups(decisions, env, envs, taken, elsewhere)
        covered = {
            (d.field or "", d.incoming or "")
            for d in decisions
            if d.kind == "group" and "new" in d.options and not d.inline
        }
        decisions += _unmatched(box, env, new_nodes, learned, covered, taken)
        if full:
            decisions += [
                Decision(
                    f"{name}/#absent", "absent", ("not-here", "keep"),
                    "not-here" if elsewhere else "keep", f"{name}/",
                )
                for name in sorted(present - exported)
            ]  # fmt: skip
        unresolved: list[str] = []
    if report.suspicious_values:
        warnings.append(
            f"{len(report.suspicious_values)} values carry another environment's letter and are "
            f"kept as they are, e.g. {report.suspicious_values[0]}"
        )
    return Intake(
        env, evidence, bool(present - exported), tuple(folders), tuple(decisions),
        tuple(unresolved), tuple(warnings), tuple(s.folder for s in report.skipped), full,
    )  # fmt: skip


# ---------------------------------------------------------------- receive


def _node_file(repo: ChainRepo, node: str) -> Path:
    folder, _, job = node.partition("/")
    return repo.job_file(folder, job) if job else repo.folder_file(folder)


def _set_variable(data: dict[str, Any], name: str, value: str | None) -> None:
    variables = [dict(v) for v in data.get(VARIABLE_TAG, [])]
    kept = [v for v in variables if v.get("NAME") != name]
    if value is None:
        variables = kept
    elif len(kept) == len(variables):
        variables.append({"NAME": name, "VALUE": value})
    else:
        for variable in variables:
            if variable.get("NAME") == name:
                variable["VALUE"] = value
    if variables:
        data[VARIABLE_TAG] = variables
    else:
        data.pop(VARIABLE_TAG, None)


def _restore(box: ChainRepo, site: Site) -> None:
    """Put the repository's value back at ``site`` in the copy."""
    path = _node_file(box, site.node)
    data = dict(read_json(path))
    if site.scope == "attribute":
        if site.current is None:
            data.pop(site.field, None)
        else:
            data[site.field] = site.current
    elif site.scope == "variable":
        _set_variable(data, site.field, site.current)
    else:
        _get(data, site.path[:-1])[site.path[-1]] = site.current
    write_json(path, data)


def _put(box: ChainRepo, site: Site, value: str) -> None:
    """Write ``value`` at ``site`` in the copy."""
    path = _node_file(box, site.node)
    data = dict(read_json(path))
    if site.scope == "attribute":
        data[site.field] = value
    elif site.scope == "variable":
        _set_variable(data, site.field, value)
    else:
        _get(data, site.path[:-1])[site.path[-1]] = value
    write_json(path, data)


_CONSTANT_NAME = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+")


def _created_name(decision: Decision, option: str) -> str | None:
    """The constant an option creates: ``new`` (the suggested name) or ``new:NAME``."""
    if option.startswith("new:"):
        return option[4:]
    return (decision.suggested or "") if option == "new" else None


def _creations(
    repo: ChainRepo, env: str, decisions: tuple[Decision, ...], chosen: Mapping[str, str]
) -> dict[str, tuple[Selector, dict[str, str | None]]]:
    """New constants the choices create: name -> (selector, value per environment)."""
    by_spec = {s.spec: s for s in repo.config.constants.values()}
    created: dict[str, tuple[Selector, dict[str, str | None]]] = {}
    for decision in decisions:
        option = chosen[decision.id]
        name = _created_name(decision, option)
        if name is None:
            continue
        if not _CONSTANT_NAME.fullmatch(name):
            raise InvalidChange(f"invalid constant name {name!r}: use lower-case group.name")
        if name in repo.config.constants or name in created:
            raise InvalidChange(f"constant {name} already exists: choose another name")
        if decision.kind == "group":
            selector = parse_spec(decision.field or "", inline=decision.inline)
            created[name] = (selector, dict(decision.values or {}))
            continue
        if decision.kind == "constant" and decision.constant:
            selector = repo.config.constants[decision.constant]
        else:
            selector = by_spec[decision.field or ""]
        created[name] = (selector, {env: decision.incoming or ""})
    return created


def _except(overrides: dict[str, Override], site: Site) -> None:
    current = overrides.get(site.node, Override())
    if site.scope == "attribute":
        overrides[site.node] = Override(
            {**current.attributes, site.field: site.incoming}, current.variables
        )
    elif site.incoming is not None:
        overrides[site.node] = Override(
            current.attributes, {**current.variables, site.field: site.incoming}
        )


def _keep_children(repo: ChainRepo, box: ChainRepo, node: str) -> None:
    before = read_json(_node_file(repo, node))
    path = _node_file(box, node)
    data = {k: v for k, v in read_json(path).items() if k not in _children(read_json(path))}
    data.update(_children(before))
    write_json(path, data)


def _keep_job(repo: ChainRepo, box: ChainRepo, node: str) -> None:
    folder, _, job_id = node.partition("/")
    write_json(box.job_file(folder, job_id), read_json(repo.job_file(folder, job_id)))
    ids_before = [str(j) for j in read_json(repo.folder_file(folder)).get(JOBS_KEY, [])]
    folder_json = dict(read_json(box.folder_file(folder)))
    ids = [str(j) for j in folder_json.get(JOBS_KEY, [])]
    position = ids_before.index(job_id)
    later = [j for j in ids_before[position + 1 :] if j in ids]
    ids.insert(ids.index(later[0]) if later else len(ids), job_id)
    folder_json[JOBS_KEY] = ids
    write_json(box.folder_file(folder), folder_json)
    meta_before = repo.folder_meta_file(folder)
    if meta_before.is_file():
        old_jobs = read_json(meta_before).get(JOBS_KEY, {})
        meta = dict(read_json(box.folder_meta_file(folder)))
        jobs = meta.get(JOBS_KEY, {})
        meta[JOBS_KEY] = {j: jobs.get(j, old_jobs.get(j, {})) for j in ids}  # folder order
        write_json(box.folder_meta_file(folder), meta)


def _site_key(site: Site) -> tuple[str, tuple[Any, ...]]:
    if site.scope == "attribute":
        return site.node, (site.field,)
    if site.scope == "variable":
        return site.node, (VARIABLE_TAG, site.field)
    return site.node, site.path


def _leaf_key(node: str, path: tuple[Any, ...], data: Mapping[str, Any]) -> tuple[str, Any]:
    """The :func:`_site_key` of the value at ``path`` of a node."""
    if len(path) == 1:
        return node, path
    if path[0] == VARIABLE_TAG and path[-1] == "VALUE" and len(path) == 3:
        return node, (VARIABLE_TAG, str(data[VARIABLE_TAG][path[1]].get("NAME")))
    return node, path


def _common_leaves(
    before: Any, after: Any, path: tuple[Any, ...] = ()
) -> Iterator[tuple[Any, ...]]:
    """Paths of the texts that differ where the two trees have the same shape."""
    if isinstance(before, dict) and isinstance(after, dict):
        for key in before:
            if key in after:
                yield from _common_leaves(before[key], after[key], (*path, key))
    elif isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        for index, (b, a) in enumerate(zip(before, after, strict=True)):
            yield from _common_leaves(b, a, (*path, index))
    elif isinstance(before, str) and isinstance(after, str) and before != after:
        yield path


def _keep_unchanged(repo: ChainRepo, box: ChainRepo, intake: Intake, names: Iterable[str]) -> None:
    """A new constant takes its value wherever the export has it; where the export changed
    nothing (a job of the repository that already had that value), the value stays as it was."""
    marks = re.compile("|".join(re.escape("@{" + name + "}") for name in names))
    differing = {_site_key(site) for decision in intake.decisions for site in decision.sites}
    for folder in intake.folders:
        if folder.status == "new":
            continue
        ids_before = {str(j) for j in read_json(repo.folder_file(folder.name)).get(JOBS_KEY, [])}
        ids_after = [str(j) for j in read_json(box.folder_file(folder.name)).get(JOBS_KEY, [])]
        nodes = [f"{folder.name}/", *(f"{folder.name}/{j}" for j in ids_after if j in ids_before)]
        for node in nodes:
            before, after = (
                read_json(_node_file(repo, node)),
                dict(read_json(_node_file(box, node))),
            )
            kept = False
            for path in _common_leaves(before, after):
                if not marks.search(_get(after, path)) or marks.search(_get(before, path)):
                    continue
                if _leaf_key(node, path, after) not in differing:
                    _get(after, path[:-1])[path[-1]] = _get(before, path)
                    kept = True
            if kept:
                write_json(_node_file(box, node), after)


def _keep_production(repo: ChainRepo, box: ChainRepo, folder: str) -> None:
    """The repository's order of the jobs of ``folder`` and their volatile attributes (dates,
    users, versions); a new job after the one the export has before it, with its own."""
    before = [str(j) for j in read_json(repo.folder_file(folder)).get(JOBS_KEY, [])]
    folder_json = dict(read_json(box.folder_file(folder)))
    after = [str(j) for j in folder_json.get(JOBS_KEY, [])]
    ids = [j for j in before if j in after]
    for index, job_id in enumerate(after):
        if job_id not in ids:
            earlier = [j for j in after[:index] if j in ids]
            ids.insert(ids.index(earlier[-1]) + 1 if earlier else 0, job_id)
    if ids != after:
        folder_json[JOBS_KEY] = ids
        write_json(box.folder_file(folder), folder_json)
    meta_file = box.folder_meta_file(folder)
    if meta_file.is_file():
        meta = dict(read_json(meta_file))
        kept = (
            read_json(repo.folder_meta_file(folder))
            if repo.folder_meta_file(folder).is_file()
            else {}
        )
        jobs = {**meta.get(JOBS_KEY, {}), **{
            j: v for j, v in kept.get(JOBS_KEY, {}).items() if j in after
        }}  # fmt: skip
        meta["attrs"] = kept.get("attrs", meta.get("attrs", {}))
        meta[JOBS_KEY] = {j: jobs[j] for j in ids if j in jobs}
        write_json(meta_file, meta)


def _new_nodes(box: ChainRepo, intake: Intake) -> list[tuple[str, Mapping[str, Any], str]]:
    nodes: list[tuple[str, Mapping[str, Any], str]] = []
    for folder in intake.folders:
        jobs = folder.jobs_added
        if folder.status == "new":
            data = read_json(box.folder_file(folder.name))
            nodes.append((f"{folder.name}/", data, str(data.get(TAG_KEY))))
        for job_id in jobs:
            if box.job_file(folder.name, job_id).is_file():
                nodes.append(
                    (
                        f"{folder.name}/{job_id}",
                        read_json(box.job_file(folder.name, job_id)),
                        JOB_TAG,
                    )
                )
    return nodes


def _place(box: ChainRepo, node: str, envs: Iterable[str]) -> None:
    """Note on a folder or job the environments it exists in."""
    path = _node_file(box, node)
    write_json(path, with_envs(read_json(path), envs, box.config.environments))


def _without(repo: ChainRepo, node: str, env: str) -> list[str]:
    """The environments of a node of ``repo``, but ``env``."""
    envs = environments_of(read_json(_node_file(repo, node))) or repo.config.environments
    return [e for e in envs if e != env]


def receive(
    repo: ChainRepo,
    data: bytes,
    env: str | None = None,
    choices: Mapping[str, str] | None = None,
    full: bool | None = None,
) -> ChangeSet:
    """The export taken into the repository, with ``choices`` (decision id -> option) applied
    over the defaults of :func:`analyze`, as one change set to preview and apply."""
    from controlm_chain_admin.core.refactor import _finish, _sandbox, _tracked

    repo = load_repo(repo.root)
    intake = analyze(repo, data, env, full)
    choices = dict(choices or {})
    unknown = sorted(set(choices) - {d.id for d in intake.decisions})
    if unknown:
        raise InvalidChange(f"unknown decision(s): {', '.join(unknown)}")
    chosen = {d.id: choices.get(d.id, d.default) for d in intake.decisions}
    for decision in intake.decisions:
        option = chosen[decision.id]
        named = option.startswith("new:") and "new" in decision.options
        if option not in decision.options and not named:
            raise InvalidChange(f"{decision.id}: choose one of {', '.join(decision.options)}")
    creations = _creations(repo, intake.env, intake.decisions, chosen)
    values: dict[str, str] = {}
    for decision in intake.decisions:
        option = chosen[decision.id]
        if (decision.kind, option) in (("learn", "learn"), ("set-value", "set-value"), (
            "constant", "set-value",
        )) and decision.constant and decision.incoming is not None:  # fmt: skip
            if values.get(decision.constant, decision.incoming) != decision.incoming:
                raise InvalidChange(f"two values chosen for {decision.constant}")
            values[decision.constant] = decision.incoming
    env = intake.env
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        if creations:
            config = box.config
            added = {name: selector for name, (selector, _) in creations.items()}
            box = box.save_config(replace(config, constants={**config.constants, **added}))
            for other in box.config.environments:
                other_config = box.load_env(other)
                new_values = {name: values.get(other) for name, (_, values) in creations.items()}
                merged = {**other_config.constants, **new_values}
                write_json(box.env_file(other), replace(other_config, constants=merged).to_json())
        if values:
            env_config = box.load_env(env)
            constants = {**env_config.constants, **values}
            write_json(box.env_file(env), replace(env_config, constants=constants).to_json())
        import_xml(box, data, env)
        box = load_repo(box.root)
        if intake.full and env != repo.config.git_rules.production:
            # production's header and job order stay; the export only adds what it has
            meta = read_json(repo.export_meta_file)
            order = read_json(box.export_meta_file).get("folder_order", [])
            write_json(box.export_meta_file, {**meta, "folder_order": order})
            for folder in intake.folders:
                if folder.status != "new":
                    _keep_production(repo, box, folder.name)
        if creations:
            _keep_unchanged(repo, box, intake, creations)
        overrides = load_overrides(box, env)
        exceptions = 0
        for decision in intake.decisions:
            option = chosen[decision.id]
            if decision.kind == "children":
                if option == "ignore" and decision.node:
                    _keep_children(repo, box, decision.node)
                continue
            if decision.kind == "removed":
                if option in ("keep", "not-here") and decision.node:
                    _keep_job(repo, box, decision.node)
                if option == "not-here" and decision.node:
                    _place(box, decision.node, _without(repo, decision.node, env))
                continue
            if decision.kind in ("added", "absent"):
                if option == "only-here" and decision.node:
                    _place(box, decision.node, [env])
                if option == "not-here" and decision.node:
                    _place(box, decision.node, _without(repo, decision.node, env))
                continue
            if option.startswith("use:"):
                for site in decision.sites:
                    _put(box, site, "@{" + option[4:] + "}")
                continue
            if option in ("exception", "exceptions"):
                for site in decision.sites:
                    _restore(box, site)
                    if site.can_except:
                        _except(overrides, site)
                        exceptions += 1
            elif option == "ignore" or (decision.kind == "learn" and option != "learn"):
                for site in decision.sites:
                    _restore(box, site)
        write_overrides(box, env, overrides)
        others = [e for e in box.config.environments if e != env]
        here = {
            d.node for d in intake.decisions if d.kind == "added" and chosen[d.id] == "only-here"
        }
        local = {
            name
            for d in intake.decisions
            if (name := _created_name(d, chosen[d.id])) is not None
            and d.sites
            and all(s.node in here or s.node.partition("/")[0] + "/" in here for s in d.sites)
        }  # used only where this environment alone has them: no value needed elsewhere
        warnings = list(intake.warnings) + [
            f"the new constant {name} has no value yet in {', '.join(missing)}: give it one "
            "before exporting there"
            for name, (_, values) in creations.items()
            if name not in local and (missing := [e for e in others if values.get(e) is None])
        ]
        stand_ins = sorted(
            name
            for d in intake.decisions
            if d.kind == "group" and d.values and d.current is not None
            and (name := _created_name(d, chosen[d.id]))
            and all(d.values.get(e) == d.current for e in others)
        )  # fmt: skip
        if stand_ins and others:
            warnings.append(
                f"{len(stand_ins)} new constant(s) have the base's value in {', '.join(others)} "
                f"until an export of there is received: {', '.join(stand_ins)}"
            )
        new = sum(1 for f in intake.folders if f.status == "new")
        changed = sum(1 for f in intake.folders if f.status == "changed")
        folders = len(intake.folders)
        summary = (
            f"receive a {env} export: {folders} folder{'s' if folders != 1 else ''} "
            f"({new} new, {changed} changed), {len(values)} value(s) of {env}, "
            f"{exceptions} exception(s)"
        )
        if creations:
            summary += f", {len(creations)} new constant(s)"
        return _finish(original, box, summary, warnings)
