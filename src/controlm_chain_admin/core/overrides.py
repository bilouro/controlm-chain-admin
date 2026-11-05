"""Exceptions: what one environment has for one job or folder instead of the base.

``envs/<env>/overrides.json`` maps a node (``FOLDER/JOB``, or ``FOLDER/`` for the folder itself)
to the attributes it sets (``null`` removes one), the variables it sets (``null``: the variable
is not there) and its lines (conditions, SHOUT, ON blocks and what is inside them), named by
their locator (:mod:`controlm_chain_admin.core.elements`)::

    {"P77_CHAIN/P77_E": {
        "set": {"TASKTYPE": "Dummy"},
        "variables": {"%%TIME_END": "0100", "%%RETRIES": null},
        "elements": {
            "OUTCOND[link=P77_E-P77_F_OK,ODATE=ODAT]": {"SIGN": "-"},
            "INCOND[link=P77_FLAG,ODATE=ODAT]": {"AND_OR": "A", "after": null},
            "SHOUT[WHEN=NOTOK,DEST=EM]": null
        }
    }}

A line the base has takes the attributes given (``null`` removes one; a list replaces the
elements inside it); a line the base has not is added whole, after the sibling ``after`` names
(``null``: first of its tag; absent or unknown: last); ``null`` leaves the line out there.

Export resolves, per value: exception, then constant, then the base value. An exception value
may itself be a ``@{constant}``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from controlm_chain_admin.core.elements import Segment, find, parse_locator, resolve
from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.jsonmodel import CHILDREN_KEY, TAG_KEY
from controlm_chain_admin.core.repo import ChainRepo, read_json, write_json

OVERRIDES_FILE = "overrides.json"
VARIABLE_TAG = "VARIABLE"
AFTER_KEY = "after"  # of an added line: the locator of the sibling it follows
Line = dict[str, Any] | None  # attributes (and lists) a line takes, or None: not there


@dataclass(frozen=True)
class Override:
    attributes: dict[str, str | None] = field(default_factory=dict)  # None removes it
    variables: dict[str, str | None] = field(default_factory=dict)  # None removes it
    elements: dict[str, Line] = field(default_factory=dict)  # by locator

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.attributes:
            data["set"] = dict(sorted(self.attributes.items()))
        if self.variables:
            data["variables"] = dict(sorted(self.variables.items()))
        if self.elements:
            data["elements"] = dict(sorted(self.elements.items()))
        return data

    @property
    def empty(self) -> bool:
        return not self.attributes and not self.variables and not self.elements

    @property
    def count(self) -> int:
        """How many values and lines the exception sets."""
        return len(self.attributes) + len(self.variables) + len(self.elements)


def overrides_path(repo: ChainRepo, env: str) -> Any:
    return repo.env_file(env).with_name(OVERRIDES_FILE)


def _parse(env: str, node: str, entry: Any) -> Override:
    where = f"envs/{env}/{OVERRIDES_FILE}: {node}"
    if not isinstance(entry, dict) or set(entry) - {"set", "variables", "elements"}:
        raise ModelError(f"{where}: expected an object with 'set', 'variables' and/or 'elements'")
    attributes = entry.get("set", {})
    variables = entry.get("variables", {})
    elements = entry.get("elements", {})
    if not isinstance(attributes, dict) or not all(
        isinstance(v, str) or v is None for v in attributes.values()
    ):
        raise ModelError(f"{where}: 'set' maps attributes to strings or null")
    if not isinstance(variables, dict) or not all(
        isinstance(v, str) or v is None for v in variables.values()
    ):
        raise ModelError(f"{where}: 'variables' maps variable names to strings or null")
    if not isinstance(elements, dict) or not all(_is_line(v) for v in elements.values()):
        raise ModelError(
            f"{where}: 'elements' maps locators to the attributes of the line, or null"
        )
    for text in elements:
        try:
            parse_locator(str(text))
        except ValueError as error:
            raise ModelError(f"{where}: {error}") from None
    return Override(dict(attributes), dict(variables), {str(k): v for k, v in elements.items()})


def _is_line(value: Any) -> bool:
    return value is None or (
        isinstance(value, dict)
        and all(v is None or isinstance(v, str | list) for v in value.values())
    )


def load_overrides(repo: ChainRepo, env: str) -> dict[str, Override]:
    """The exceptions of ``env`` by node; empty when the file does not exist."""
    path = overrides_path(repo, env)
    if not path.is_file():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise ModelError(f"envs/{env}/{OVERRIDES_FILE}: expected an object of nodes")
    return {str(node): _parse(env, str(node), entry) for node, entry in data.items()}


def write_overrides(repo: ChainRepo, env: str, overrides: Mapping[str, Override]) -> None:
    """Write the exceptions of ``env`` (sorted by node); no file when there is none."""
    kept = {node: o.to_json() for node, o in sorted(overrides.items()) if not o.empty}
    path = overrides_path(repo, env)
    if kept:
        write_json(path, kept)
    elif path.exists():
        path.unlink()


def apply_override(data: Mapping[str, Any], override: Override | None) -> dict[str, Any]:
    """A job or folder JSON with the exception applied: attributes, variables, then lines.

    A line whose parent the base has not any more is skipped (``stale_lines`` names them)."""
    out = dict(data)
    if override is None:
        return out
    for attribute, value in override.attributes.items():
        if value is None:
            out.pop(attribute, None)
        else:
            out[attribute] = value
    if override.variables:
        variables = [dict(v) for v in out.get(VARIABLE_TAG, [])]
        for name, value in override.variables.items():
            if value is None:
                variables = [v for v in variables if v.get("NAME") != name]
                continue
            for variable in variables:
                if variable.get("NAME") == name:
                    variable["VALUE"] = value
                    break
            else:
                variables.append({"NAME": name, "VALUE": value})
        if variables:
            out[VARIABLE_TAG] = variables
        else:
            out.pop(VARIABLE_TAG, None)
    if override.elements:
        _apply_lines(out, override.elements)
    return out


def _apply_lines(out: dict[str, Any], lines: Mapping[str, Line]) -> None:
    """Change, remove and add lines; an added line waits for the sibling it follows."""
    pending: list[tuple[tuple[Segment, ...], dict[str, Any]]] = []
    for text, line in lines.items():
        segments = parse_locator(text)
        parent = _parent(out, segments)
        if parent is None:
            continue  # stale: the base lost the block this line was inside
        found = find(parent, segments[-1])
        if line is None:
            if found is not None:
                key, index = found
                parent[key] = [e for i, e in enumerate(parent[key]) if i != index]
        elif found is not None:
            key, index = found
            parent[key] = [
                _changed(e, line) if i == index else e for i, e in enumerate(parent[key])
            ]
        else:
            pending.append((segments, line))
    while pending:
        later: list[tuple[tuple[Segment, ...], dict[str, Any]]] = []
        for segments, line in pending:
            parent = _parent(out, segments)
            assert parent is not None
            if _waits(parent, line, [s for s, _ in pending if s is not segments]):
                later.append((segments, line))  # its sibling is added too: after it
                continue
            _add(parent, segments[-1], line)
        if len(later) == len(pending):  # they wait for each other: last of their tag
            for segments, line in later:
                _add(_parent(out, segments) or out, segments[-1], {**line, AFTER_KEY: ""})
            break
        pending = later


def _waits(
    parent: Mapping[str, Any], line: Mapping[str, Any], others: list[tuple[Segment, ...]]
) -> bool:
    """Whether the sibling the line follows is not there yet but is being added too."""
    after = line.get(AFTER_KEY)
    if not isinstance(after, str) or not after:
        return False
    target = parse_locator(after)[-1]
    if resolve(parent, (target,)) is not None:
        return False
    return any(str(other[-1]) == str(target) for other in others)


def _parent(out: dict[str, Any], segments: tuple[Segment, ...]) -> dict[str, Any] | None:
    """The (copied, writable) element holding the line the segments name."""
    current = out
    for segment in segments[:-1]:
        found = find(current, segment)
        if found is None:
            return None
        key, index = found
        copied = [dict(e) if isinstance(e, dict) else e for e in current[key]]
        current[key] = copied
        current = copied[index]
    return current


def _changed(element: Mapping[str, Any], line: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(element)
    for key, value in line.items():
        if key == AFTER_KEY:
            continue
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def _add(parent: dict[str, Any], segment: Segment, line: Mapping[str, Any]) -> None:
    """Insert the line among the siblings of its tag, after the one ``after`` names."""
    element: dict[str, Any] = dict(segment.where)
    element.update({k: v for k, v in line.items() if k != AFTER_KEY and v is not None})
    after = line.get(AFTER_KEY, "")  # "" (or unknown): last of its tag; None: first
    ordered = parent.get(CHILDREN_KEY)
    if isinstance(ordered, list):
        ordered = list(ordered)
        element = {TAG_KEY: segment.tag, **element}
        parent[CHILDREN_KEY] = _insert(ordered, parent, segment.tag, element, after)
        return
    grouped = list(parent.get(segment.tag, []))
    parent[segment.tag] = _insert(grouped, parent, segment.tag, element, after)


def _insert(
    items: list[Any], parent: Mapping[str, Any], tag: str, element: dict[str, Any], after: Any
) -> list[Any]:
    same = [i for i, e in enumerate(items) if isinstance(e, dict) and e.get(TAG_KEY, tag) == tag]
    if after is None:
        position = same[0] if same else len(items)
    else:
        found = None
        if isinstance(after, str) and after:
            found = find(parent, parse_locator(after)[-1])
        if found is not None and found[0] in (tag, CHILDREN_KEY):
            position = found[1] + 1
        else:
            position = same[-1] + 1 if same else len(items)
    return [*items[:position], element, *items[position:]]


def prune_overrides(repo: ChainRepo) -> list[str]:
    """Drop what the exceptions of every environment set that the base has anyway now, and the
    lines whose block the base lost; returns a warning per node that lost something stale."""
    warnings: list[str] = []
    for env in repo.config.environments:
        overrides = load_overrides(repo, env)
        if not overrides:
            continue
        kept: dict[str, Override] = {}
        for node, override in overrides.items():
            folder, _, job = node.partition("/")
            path = repo.job_file(folder, job) if job else repo.folder_file(folder)
            if not path.is_file():
                warnings.append(f"exception for {env} on {node} dropped: the node is gone")
                continue
            base = read_json(path)
            pruned, stale = _pruned(override, base)
            if stale:
                warnings.append(
                    f"exception for {env} on {node}: {len(stale)} line(s) dropped, the base "
                    f"lost the block they were in ({', '.join(stale)})"
                )
            if not pruned.empty:
                kept[node] = pruned
        if kept != overrides:
            write_overrides(repo, env, kept)
    return warnings


def _pruned(override: Override, base: Mapping[str, Any]) -> tuple[Override, list[str]]:
    attributes = {
        k: v
        for k, v in override.attributes.items()
        if not (base.get(k) == v if v is not None else k not in base)
    }
    present = {
        str(v.get("NAME")): str(v.get("VALUE", ""))
        for v in base.get(VARIABLE_TAG, [])
        if isinstance(v, dict)
    }
    variables = {
        k: v
        for k, v in override.variables.items()
        if not (present.get(k) == v if v is not None else k not in present)
    }
    elements: dict[str, Line] = {}
    stale: list[str] = []
    for text, line in override.elements.items():
        segments = parse_locator(text)
        parent = resolve(base, segments[:-1])
        if parent is None:
            stale.append(text)
            continue
        found = find(parent, segments[-1])
        if line is None:
            if found is not None:
                elements[text] = None
            continue
        if found is None:
            elements[text] = line  # the base still lacks the line
            continue
        element = parent[found[0]][found[1]]
        rest = {
            k: v
            for k, v in line.items()
            if k != AFTER_KEY and not (element.get(k) == v if v is not None else k not in element)
        }
        if rest:
            elements[text] = rest
    return Override(attributes, variables, elements), stale


def node_exceptions(repo: ChainRepo, node: str) -> dict[str, Override]:
    """The exceptions of one node (``FOLDER/JOB`` or ``FOLDER/``), by environment."""
    found = {}
    for env in repo.config.environments:
        override = load_overrides(repo, env).get(node)
        if override is not None and not override.empty:
            found[env] = override
    return found
