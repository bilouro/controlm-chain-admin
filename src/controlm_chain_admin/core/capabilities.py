"""What can be asked in plain words, and how each request becomes changes.

``capabilities.json`` (next to this module) is the one source: the menu people read, the
tools an assistant calls (``ctmchain mcp``) and the instructions it follows all come from it.
A capability names the operation it runs (:data:`refactor.OPERATIONS`), its parameters as JSON
Schema, its rules and an example on the synthetic chain; ``each`` runs the operation once per
item of a list parameter. Every request is a list of steps ``{"do": <capability>, "params"}``,
previewed as one change set.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from controlm_chain_admin.core.errors import InvalidChange
from controlm_chain_admin.core.ops import ORIGINALS_KEY
from controlm_chain_admin.core.refactor import ChangeSet, fingerprint, run_operation
from controlm_chain_admin.core.repo import ChainRepo

_TYPE_WORDS = {"string": "text", "boolean": "true or false", "null": "null"}
_CHECKS = {
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


@dataclass(frozen=True)
class Capability:
    """One thing that can be asked: the operation it runs and how to call it."""

    id: str
    op: str
    group: str
    title: str
    when: str
    params: Mapping[str, Any]  # JSON Schema of an object
    rules: tuple[str, ...]
    example_say: str
    example: Mapping[str, Any]
    each: str | None = None

    @property
    def signature(self) -> str:
        """``change-in-env(env, nodes, attributes?, ...)``: the id and the parameters, the
        optional ones with ``?``."""
        required = list(self.params.get("required", []))
        optional = [f"{p}?" for p in self.params.get("properties", {}) if p not in required]
        return f"{self.id}({', '.join([*required, *optional])})"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "each": self.each,
            "group": self.group,
            "title": self.title,
            "when": self.when,
            "params": self.params,
            "rules": list(self.rules),
            "example": {"say": self.example_say, "params": self.example},
        }


@dataclass(frozen=True)
class Question:
    """A read-only tool of the assistant, as the menu lists it."""

    tool: str
    title: str
    say: str


@dataclass(frozen=True)
class Catalogue:
    """Everything in ``capabilities.json``."""

    workflow: tuple[str, ...]
    groups: tuple[str, ...]
    questions: tuple[Question, ...]
    not_by_prompt: Mapping[str, str]
    capabilities: tuple[Capability, ...]

    def get(self, capability: str) -> Capability:
        for candidate in self.capabilities:
            if candidate.id == capability:
                return candidate
        known = ", ".join(c.id for c in self.capabilities)
        raise InvalidChange(f"unknown capability {capability!r}; known: {known}")

    def operations(self, steps: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """The operations of the steps, in order; every step is checked first."""
        operations: list[dict[str, Any]] = []
        for number, step in enumerate(steps, 1):
            if not isinstance(step, Mapping) or not isinstance(step.get("do"), str):
                raise InvalidChange(f"step {number}: say what to do (do: a capability id)")
            capability = self.get(step["do"])
            params = step.get("params") or {}
            if not isinstance(params, Mapping):
                raise InvalidChange(f"{capability.id}: params must be an object")
            _check(capability, params)
            operations.extend(_expand(capability, params))
        return operations

    def to_json(self) -> dict[str, Any]:
        return {
            "workflow": list(self.workflow),
            "groups": list(self.groups),
            "questions": [vars(q) for q in self.questions],
            "not_by_prompt": dict(self.not_by_prompt),
            "capabilities": [c.to_json() for c in self.capabilities],
        }


@cache
def load_catalogue() -> Catalogue:
    """Read ``capabilities.json`` of the installed package."""
    text = resources.files(__package__).joinpath("capabilities.json").read_text("utf-8")
    data = json.loads(text)
    return Catalogue(
        workflow=tuple(data["workflow"]),
        groups=tuple(data["groups"]),
        questions=tuple(Question(**q) for q in data["questions"]),
        not_by_prompt=dict(data["not_by_prompt"]),
        capabilities=tuple(
            Capability(
                id=c["id"],
                op=c["op"],
                each=c.get("each"),
                group=c["group"],
                title=c["title"],
                when=c["when"],
                params=c["params"],
                rules=tuple(c["rules"]),
                example_say=c["example"]["say"],
                example=c["example"]["params"],
            )
            for c in data["capabilities"]
        ),
    )


def plan(repo: ChainRepo, steps: Sequence[Mapping[str, Any]]) -> ChangeSet:
    """Preview the steps as one change set (a batch when there are several operations)."""
    operations = load_catalogue().operations(steps)
    if not operations:
        raise InvalidChange("nothing to do: give at least one step")
    if len(operations) == 1:
        return run_operation(repo, operations[0]["op"], operations[0]["params"])
    return run_operation(repo, "batch", {"changes": operations})


def preview_steps(
    repo: ChainRepo, steps: Sequence[Mapping[str, Any]], *, diff_lines: int = 400
) -> dict[str, Any]:
    """What the steps would change, for the user to agree to: the id an apply checks (none
    when nothing changes), each field before -> after, the warnings and the diff."""
    change = plan(repo, steps)
    return {
        "preview_id": preview_id(change) if change.edits else None,
        "summary": change.summary if change.edits else f"{change.summary}: nothing to change",
        "warnings": list(change.warnings),
        "changes": changes_of(change),
        "files": [edit.path for edit in change.edits],
        "diff": cut_lines(change.diff(), diff_lines, "diff_lines shows more"),
    }


def preview_id(change: ChangeSet) -> str:
    """The short fingerprint that names a previewed change."""
    return fingerprint(change)[:12]


def cut_lines(text: str, lines: int, hint: str) -> str:
    """The first ``lines`` lines of ``text``, then how many more and how to see them."""
    rows = text.splitlines()
    if len(rows) <= lines:
        return text
    return "\n".join([*rows[:lines], f"... {len(rows) - lines} more lines ({hint})"])


def changes_of(change: ChangeSet) -> list[dict[str, Any]]:
    """Each field a change set changes, where: what to tell the user before applying."""
    rows: list[dict[str, Any]] = []
    for edit in change.edits:
        where = _where(edit.path)
        if edit.before is None or edit.after is None:
            after = "created" if edit.before is None else "deleted"
            rows.append({"where": where, "field": None, "before": None, "after": after})
            continue
        before, after_data = json.loads(edit.before), json.loads(edit.after)
        if not isinstance(before, dict) or not isinstance(after_data, dict):
            rows.append({"where": where, "field": None, "before": None, "after": "changed"})
            continue
        if edit.path.startswith("meta/folders/"):  # the JOBNAME Control-M has lives there
            folder = edit.path.split("/")[2].removesuffix(".json")
            rows.extend(_jobnames(folder, before, after_data))
            before = {k: v for k, v in before.items() if k != ORIGINALS_KEY}
            after_data = {k: v for k, v in after_data.items() if k != ORIGINALS_KEY}
        rows.extend({"where": where, **row} for row in _fields(before, after_data))
    return rows


def _jobnames(
    folder: str, before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """The jobs whose JOBNAME in Control-M changes: a numbered job is called by its number
    there unless another name is kept for it."""
    olds, news = before.get(ORIGINALS_KEY, {}), after.get(ORIGINALS_KEY, {})
    return [
        {
            "where": f"{folder}/{job}",
            "field": "JOBNAME",
            "before": olds.get(job, job),
            "after": news.get(job, job),
        }
        for job in [*olds, *(j for j in news if j not in olds)]
        if olds.get(job, job) != news.get(job, job)
    ]


def _fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in [*before, *(k for k in after if k not in before)]:
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if key == "VARIABLE":
            olds = {v["NAME"]: v.get("VALUE") for v in old or []}
            news = {v["NAME"]: v.get("VALUE") for v in new or []}
            rows += [
                {"field": name, "before": olds.get(name), "after": news.get(name)}
                for name in [*olds, *(n for n in news if n not in olds)]
                if olds.get(name) != news.get(name)
            ]
        else:
            rows.append({"field": key, "before": _short(old), "after": _short(new)})
    return rows


def _short(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 160 else text[:157] + "..."


def _where(path: str) -> str:
    """``folders/F/jobs/J.json`` is ``F/J``, ``folders/F/folder.json`` is ``F/``."""
    parts = path.split("/")
    if len(parts) == 4 and parts[0] == "folders" and parts[2] == "jobs":
        return f"{parts[1]}/{parts[3].removesuffix('.json')}"
    if len(parts) == 3 and parts[0] == "folders" and parts[2] == "folder.json":
        return f"{parts[1]}/"
    return path


def _expand(capability: Capability, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    if capability.each is None:
        return [{"op": capability.op, "params": dict(params)}]
    rest = {k: v for k, v in params.items() if k != capability.each}
    single = capability.each.removesuffix("s")
    return [
        {"op": capability.op, "params": {single: item, **rest}} for item in params[capability.each]
    ]


# ---------------------------------------------------------------- parameters


def _check(capability: Capability, params: Mapping[str, Any]) -> None:
    properties: Mapping[str, Any] = capability.params.get("properties", {})
    unknown = sorted(set(params) - set(properties))
    if unknown:
        expected = ", ".join(properties)
        raise InvalidChange(
            f"{capability.id}: unknown parameter {', '.join(unknown)}; it takes {expected}"
        )
    for name in capability.params.get("required", []):
        if name not in params:
            expected = _describe(capability, name)
            raise InvalidChange(f"{capability.id}: {name} is missing ({expected})")
    for name, value in params.items():
        if not _fits(properties[name], value):
            raise InvalidChange(f"{capability.id}: {name} must be {_words(properties[name])}")


def _fits(schema: Mapping[str, Any], value: Any) -> bool:
    kind = schema.get("type")
    if kind == "array":
        items = schema.get("items", {})
        return isinstance(value, list) and all(_fits(items, item) for item in value)
    if kind == "object":
        values = schema.get("additionalProperties", {})
        return isinstance(value, Mapping) and all(
            isinstance(key, str) and _fits(values, item) for key, item in value.items()
        )
    return any(_CHECKS[str(k)](value) for k in _kinds(kind))


def _words(schema: Mapping[str, Any]) -> str:
    """What a parameter takes, in words: ``list of text``, ``attribute -> text or null``."""
    kind = schema.get("type")
    if kind == "array":
        return f"a list of {_words(schema.get('items', {})).removeprefix('a ')}"
    if kind == "object":
        return f"{schema.get('x-key', 'name')} -> {_words(schema.get('additionalProperties', {}))}"
    return " or ".join(_TYPE_WORDS[str(k)] for k in _kinds(kind))


def _kinds(kind: Any) -> list[str]:
    """The JSON Schema ``type`` as a list: ``"string"`` or ``["string", "null"]``."""
    return [str(k) for k in kind] if isinstance(kind, list) else [str(kind)]


def _describe(capability: Capability, name: str) -> str:
    schema = capability.params["properties"][name]
    return f"{_words(schema)}: {schema.get('description', '')}".rstrip(": ")


# ---------------------------------------------------------------- the menu


def render_menu(catalogue: Catalogue, capability: str | None = None) -> str:
    """The menu as text: every capability by group with an example, or one in detail."""
    if capability is not None:
        return _detail(catalogue.get(capability))
    lines = ["What you can ask (ctmchain menu <capability> for the details)", ""]
    for group in catalogue.groups:
        lines.append(group)
        for item in (c for c in catalogue.capabilities if c.group == group):
            lines += [f"  {item.id}: {item.title}", f'    e.g. "{item.example_say}"']
        lines.append("")
    lines.append("Questions")
    for question in catalogue.questions:
        lines += [f"  {question.tool}: {question.title}", f'    e.g. "{question.say}"']
    return "\n".join(lines) + "\n"


def _detail(capability: Capability) -> str:
    lines = [f"{capability.id} ({capability.op}): {capability.title}", f"When: {capability.when}"]
    lines.append("Parameters:")
    required = set(capability.params.get("required", []))
    for name, schema in capability.params.get("properties", {}).items():
        flag = " (required)" if name in required else ""
        words = _words(schema).removeprefix("a ")
        lines.append(f"  {name}{flag}: {words} - {schema.get('description', '')}")
    if capability.each:
        lines.append(f"  one {capability.op} per item of {capability.each}")
    if capability.rules:
        lines += ["Rules:", *(f"  - {rule}" for rule in capability.rules)]
    example = json.dumps(capability.example, ensure_ascii=False)
    lines += [f'Example: "{capability.example_say}"', f"  {example}"]
    return "\n".join(lines) + "\n"
