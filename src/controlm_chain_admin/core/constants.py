"""Constants: logical values ``@{name}`` in the base, resolved per environment at export.

A constant is bound to a *selector* — which attribute of which element it replaces, optionally
filtered by another attribute (``VARIABLE[NAME=%%GEIENV]/@VALUE``). Two modes:

* **value** (default): the whole attribute value equals the environment's value of the
  constant; import replaces it by ``@{name}``, export writes the target environment's value.
* **inline**: the environment's value occurs as a token inside free text (``[UAT] Load failed``);
  import replaces token-bounded occurrences by ``@{name}``, export substitutes them back.

The registry of bindings lives in ``chain.json`` (``constants``); the values per environment in
``envs/<env>/env.json`` (``constants``). A missing value (``null``) makes export fail for that
environment unless unresolved placeholders are explicitly allowed.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from controlm_chain_admin.core.errors import ConstantConflict, ModelError, UnresolvedConstant
from controlm_chain_admin.core.model import XmlComment, XmlDocument, XmlElement
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json, write_json

PLACEHOLDER = re.compile(r"@\{([A-Za-z0-9_.\-]+)\}")
_SPEC = re.compile(
    r"^(?:(?P<tag>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<k>[^=\]]+)=(?P<v>[^\]]*)\])?/@)?"
    r"(?P<attr>[A-Za-z_][A-Za-z0-9_]*)$"
)
_GROUPS = {"NODEID": "node", "RUN_AS": "user", "DEST": "mail", "CC_DEST": "mail"}


@dataclass(frozen=True)
class Selector:
    """Which attribute a constant replaces: ``ATTR``, ``TAG/@ATTR`` or ``TAG[K=V]/@ATTR``."""

    attribute: str
    tag: str | None = None
    where: dict[str, str] = field(default_factory=dict)
    inline: bool = False

    @property
    def spec(self) -> str:
        where = "".join(f"[{k}={v}]" for k, v in self.where.items())
        return f"{self.tag}{where}/@{self.attribute}" if self.tag else self.attribute

    def matches(self, element: XmlElement) -> bool:
        if self.tag is not None and element.tag != self.tag:
            return False
        return all(element.get(key) == value for key, value in self.where.items())

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"attribute": self.attribute}
        if self.tag is not None:
            data["tag"] = self.tag
        if self.where:
            data["where"] = dict(self.where)
        if self.inline:
            data["inline"] = True
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Selector:
        try:
            return cls(
                attribute=str(data["attribute"]),
                tag=str(data["tag"]) if data.get("tag") is not None else None,
                where={str(k): str(v) for k, v in data.get("where", {}).items()},
                inline=bool(data.get("inline", False)),
            )
        except KeyError as exc:
            raise ModelError(f"chain.json constants: missing key {exc}") from exc


def parse_spec(spec: str, inline: bool = False) -> Selector:
    """Parse ``ATTR``, ``TAG/@ATTR`` or ``TAG[K=V]/@ATTR``."""
    match = _SPEC.match(spec)
    if not match:
        raise ModelError(f"invalid attribute spec {spec!r}: use ATTR, TAG/@ATTR or TAG[K=V]/@ATTR")
    where = {match["k"]: match["v"]} if match["k"] else {}
    return Selector(match["attr"], match["tag"], where, inline)


def placeholder(name: str) -> str:
    return f"@{{{name}}}"


def values_from_pattern(pattern: str, letters: Mapping[str, str]) -> dict[str, str]:
    """Fill every environment from a template with ``{L}`` (upper letter) / ``{l}`` (lower)."""
    return {
        env: pattern.replace("{L}", letter.upper()).replace("{l}", letter.lower())
        for env, letter in letters.items()
    }


# ---------------------------------------------------------------- tree rewriting


def _rewrite(
    document: XmlDocument, visit_attr: Callable[[XmlElement, str, str], str]
) -> XmlDocument:
    def visit(element: XmlElement) -> XmlElement:
        attrs = tuple((key, visit_attr(element, key, value)) for key, value in element.attrs)
        children = tuple(
            child if isinstance(child, XmlComment) else visit(child) for child in element.children
        )
        return replace(element, attrs=attrs, children=children)

    return replace(document, root=visit(document.root))


@dataclass(frozen=True)
class ImportConstantsReport:
    replaced: int
    unmapped: dict[str, tuple[str, ...]]  # spec -> distinct values seen but bound to no constant


def apply_import(
    document: XmlDocument, bindings: Mapping[str, Selector], env_values: Mapping[str, str | None]
) -> tuple[XmlDocument, ImportConstantsReport]:
    """Replace environment values by ``@{name}`` placeholders (import direction)."""
    replaced = 0
    unmapped: dict[str, list[str]] = {}

    def visit(element: XmlElement, key: str, value: str) -> str:
        nonlocal replaced
        applicable = [
            (name, selector)
            for name, selector in bindings.items()
            if selector.attribute == key and selector.matches(element)
        ]
        whole = [(n, s) for n, s in applicable if not s.inline]
        for name, _ in whole:
            expected = env_values.get(name)
            if expected is not None and value == expected:
                replaced += 1
                return placeholder(name)
        if whole and not PLACEHOLDER.fullmatch(value):
            seen = unmapped.setdefault(whole[0][1].spec, [])
            if value not in seen:
                seen.append(value)
        for name, _ in ((n, s) for n, s in applicable if s.inline):
            expected = env_values.get(name)
            if expected:
                pattern = rf"(?<![A-Za-z0-9]){re.escape(expected)}(?![A-Za-z0-9])"
                value, count = re.subn(pattern, placeholder(name), value)
                replaced += count
        return value

    rewritten = _rewrite(document, visit)
    return rewritten, ImportConstantsReport(replaced, {k: tuple(v) for k, v in unmapped.items()})


@dataclass(frozen=True)
class ExportConstantsReport:
    resolved: int
    unresolved: tuple[str, ...]  # constant names referenced but without a value in the env


def apply_export(
    document: XmlDocument,
    bindings: Mapping[str, Selector],
    env_values: Mapping[str, str | None],
    *,
    allow_unresolved: bool = False,
) -> tuple[XmlDocument, ExportConstantsReport]:
    """Resolve ``@{name}`` placeholders to the environment's values (export direction)."""
    resolved = 0
    unresolved: dict[str, None] = {}

    def repl(match: re.Match[str]) -> str:
        nonlocal resolved
        name = match.group(1)
        value = env_values.get(name) if name in bindings else None
        if value is None:
            unresolved[name] = None
            return match.group(0)
        resolved += 1
        return value

    def visit(_element: XmlElement, _key: str, value: str) -> str:
        return PLACEHOLDER.sub(repl, value) if "@{" in value else value

    rewritten = _rewrite(document, visit)
    if unresolved and not allow_unresolved:
        names = ", ".join(sorted(unresolved))
        raise UnresolvedConstant(f"no value in this environment for constants: {names}")
    return rewritten, ExportConstantsReport(resolved, tuple(unresolved))


# ---------------------------------------------------------------- names


def propose_name(selector: Selector, value: str, letter_prefixes: Sequence[str]) -> str:
    """A readable constant name for a value, e.g. ``node.p77_batch`` or ``mail.ops``."""
    attr = selector.attribute
    if selector.tag == "VARIABLE":
        group, base = "var", selector.where.get("NAME", value).lstrip("%")
    elif attr in _GROUPS:
        group = _GROUPS[attr]
        base = value.split("@")[0] if group == "mail" else value
    else:
        group, base = attr.lower(), value
    if letter_prefixes and group != "var":
        alternation = "|".join(re.escape(p) for p in letter_prefixes)
        if re.match(rf"^[A-Z](?:{alternation})", base):
            base = base[1:]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").lower() or "value"
    return f"{group}.{slug}"


# ---------------------------------------------------------------- repository


def constants_table(repo: ChainRepo) -> dict[str, dict[str, str | None]]:
    """Every constant with its value per environment (``None`` when missing)."""
    repo = load_repo(repo.root)
    per_env = {env: repo.load_env(env).constants for env in repo.config.environments}
    return {
        name: {env: per_env[env].get(name) for env in repo.config.environments}
        for name in repo.config.constants
    }


@dataclass(frozen=True)
class ConstantRow:
    """One constant: what it replaces, its value per environment, where it is used."""

    name: str
    spec: str
    values: dict[str, str | None]
    uses: int  # placeholders in jobs, folders and exceptions
    nodes: tuple[str, ...]  # FOLDER/JOB or FOLDER/ using it, in folder order

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(env for env, value in self.values.items() if value is None)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "spec": self.spec,
            "values": dict(self.values),
            "missing": list(self.missing),
            "uses": self.uses,
            "nodes": list(self.nodes),
        }


def constants_overview(repo: ChainRepo) -> list[ConstantRow]:
    """Every constant with its values per environment and the nodes that use it."""
    from controlm_chain_admin.core.links import folder_names  # local: avoids an import cycle

    repo = load_repo(repo.root)
    table = constants_table(repo)
    uses: dict[str, int] = dict.fromkeys(table, 0)
    nodes: dict[str, list[str]] = {name: [] for name in table}
    for folder in folder_names(repo):
        ids = [str(j) for j in read_json(repo.folder_file(folder)).get("jobs", [])]
        files = [(f"{folder}/", repo.folder_file(folder))]
        files += [(f"{folder}/{j}", repo.job_file(folder, j)) for j in ids]
        for node, path in files:
            for name in PLACEHOLDER.findall(path.read_text(encoding="utf-8")):
                if name in uses:
                    uses[name] += 1
                    if node not in nodes[name]:
                        nodes[name].append(node)
    for env in repo.config.environments:
        exceptions = repo.env_file(env).with_name("overrides.json")
        if exceptions.is_file():
            for name in PLACEHOLDER.findall(exceptions.read_text(encoding="utf-8")):
                if name in uses:
                    uses[name] += 1
    return [
        ConstantRow(name, repo.config.constants[name].spec, values, uses[name], tuple(nodes[name]))
        for name, values in table.items()
    ]


def define_constant(
    repo: ChainRepo, name: str, selector: Selector, values: Mapping[str, str | None]
) -> ChainRepo:
    """Register (or extend) a constant and write its values into the environment files."""
    repo = load_repo(repo.root)
    config = repo.config
    existing = config.constants.get(name)
    if existing is not None and existing != selector:
        raise ConstantConflict(f"constant {name!r} is already bound to {existing.spec}")
    rule = config.letter_rule
    if rule.enabled and selector.attribute in rule.attributes and not selector.inline:
        raise ConstantConflict(
            f"attribute {selector.attribute} is governed by the letter rule; no constants there"
        )
    unknown = sorted(set(values) - set(config.environments))
    if unknown:
        raise ConstantConflict(
            f"unknown environment(s) {unknown}; known: {list(config.environments)}"
        )
    table = constants_table(repo)
    for other, other_values in table.items():
        if other == name or config.constants[other] != selector:
            continue
        for env, value in values.items():
            if value is not None and other_values.get(env) == value:
                raise ConstantConflict(
                    f"{selector.spec}={value!r} in {env} already belongs to constant {other!r}"
                )
    repo = repo.save_config(replace(config, constants={**config.constants, name: selector}))
    for env in repo.config.environments:
        env_config = repo.load_env(env)
        merged: dict[str, str | None] = dict(env_config.constants)
        merged.setdefault(name, None)
        if values.get(env) is not None:
            merged[name] = values[env]
        write_json(repo.env_file(env), replace(env_config, constants=merged).to_json())
    return repo


def build_draft(
    repo: ChainRepo, document: XmlDocument, specs: Sequence[str], env: str | None
) -> dict[str, Any]:
    """A mapping draft for ``distinct --write``: every value with a proposed name and env slots."""
    from controlm_chain_admin.core.inspect import distinct_values  # local: avoids an import cycle

    repo = load_repo(repo.root)
    prefixes = repo.config.letter_rule.prefixes
    draft: dict[str, Any] = {"environment": env}
    for spec, values in distinct_values(document, specs).items():
        selector = parse_spec(spec)
        entries: dict[str, Any] = {}
        for item in values:
            slots: dict[str, str | None] = dict.fromkeys(repo.config.environments)
            if env is not None:
                slots[env] = item.value
            entries[item.value] = {
                "count": item.count,
                "samples": list(item.samples),
                "as": propose_name(selector, item.value, prefixes),
                "values": slots,
            }
        draft[spec] = entries
    return draft


def apply_draft(repo: ChainRepo, draft: Mapping[str, Any]) -> tuple[ChainRepo, tuple[str, ...]]:
    """Define every constant of a draft whose ``as`` is set; ``pattern`` fills the environments."""
    repo = load_repo(repo.root)
    env = draft.get("environment")
    letters = repo.env_letters()
    defined: list[str] = []
    for spec, entries in draft.items():
        if spec == "environment" or not isinstance(entries, Mapping):
            continue
        selector = parse_spec(spec)
        for value, entry in entries.items():
            name = entry.get("as")
            if not name:
                continue
            values: dict[str, str | None] = {}
            if entry.get("pattern"):
                values.update(values_from_pattern(str(entry["pattern"]), letters))
            values.update({k: v for k, v in entry.get("values", {}).items() if v is not None})
            if env and values.get(env) is None:
                values[env] = str(value)
            repo = define_constant(repo, str(name), selector, values)
            defined.append(str(name))
    return repo, tuple(defined)
