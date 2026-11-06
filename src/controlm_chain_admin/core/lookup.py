"""Read-only answers for an assistant: find nodes, describe one, a condition by its name.

What the tools of ``ctmchain mcp`` return to answer questions in plain words ("which jobs run
on that agent in prod?", "what does P77_B wait for?"), as JSON-ready dictionaries.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from controlm_chain_admin.core.constants import resolve_json
from controlm_chain_admin.core.errors import InvalidChange, ModelError
from controlm_chain_admin.core.inspect import show_node
from controlm_chain_admin.core.links import NodeRef, folder_names, load_links
from controlm_chain_admin.core.membership import belongs
from controlm_chain_admin.core.overrides import apply_override, load_overrides, node_exceptions
from controlm_chain_admin.core.repo import ChainRepo, read_json

_NAME_FIELDS = {"job": ("JOBNAME", "DESCRIPTION"), "folder": ("FOLDER_NAME", "DESCRIPTION")}
_GROUPS = ("VARIABLE", "INCOND", "OUTCOND", "jobs", "meta")


def find_nodes(
    repo: ChainRepo,
    *,
    text: str | None = None,
    attribute: str | None = None,
    value: str | None = None,
    env: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Jobs and folders by part of their name (``text``), an ``attribute`` and part of its
    ``value``, all ignoring case; with ``env``, the ones that environment has, with its values.
    """
    if not (text or attribute or value):
        raise InvalidChange("give a text, an attribute or a value to look for")
    wanted = (
        text.casefold() if text else None,
        attribute.upper() if attribute else None,
        value.casefold() if value else None,
    )
    matches = []
    for ref, data in _nodes(repo, env):
        matched = _match(ref, data, *wanted)
        if matched:
            kind = "job" if ref.job is not None else "folder"
            name = data.get(_NAME_FIELDS[kind][0], ref.job or ref.folder)
            matches.append({"node": _node_id(ref), "kind": kind, "name": name, "matched": matched})
    return {"total": len(matches), "matches": matches[:limit], "truncated": len(matches) > limit}


def describe_node(repo: ChainRepo, node: str, env: str | None = None) -> dict[str, Any]:
    """One job or folder: its fields, variables, other lines, what it waits for and releases,
    and the exceptions of every environment; with ``env``, as that environment has it."""
    ref = NodeRef.parse(node)
    data = show_node(repo, node, env)
    technical = data.get("meta", {})
    links = sorted(load_links(repo).values(), key=lambda link: link.name)
    described: dict[str, Any] = {
        "node": _node_id(ref),
        "kind": "job" if ref.job is not None else "folder",
        **({"env": env} if env else {}),
        "attributes": {k: v for k, v in data.items() if isinstance(v, str)},
        "variables": {v["NAME"]: v.get("VALUE") for v in data.get("VARIABLE", [])},
        "waits_for": [
            {"condition": link.name, "from": [str(p) for p in link.all_producers]}
            for link in links
            if ref in link.consumers
        ],
        "releases": [
            {"condition": link.name, "to": [str(c) for c in link.consumers]}
            for link in links
            if ref in link.all_producers
        ],
        "lines": {k: v for k, v in data.items() if not isinstance(v, str) and k not in _GROUPS},
        "technical": technical,
        "exceptions": {
            name: _parts(override.attributes, override.variables, override.elements)
            for name, override in node_exceptions(repo, _node_id(ref)).items()
        },
    }
    if ref.job is None:
        described["jobs"] = list(data.get("jobs", []))
    return described


def find_condition(repo: ChainRepo, name: str) -> dict[str, Any]:
    """One condition by its name (or its link id): who emits it, waits for it, deletes it."""
    links = load_links(repo)
    found = next((link for link in links.values() if link.name == name), links.get(name))
    if found is None:
        raise ModelError(f"no condition is called {name}; find the jobs, then show them")
    return found.to_json()


def _nodes(repo: ChainRepo, env: str | None) -> Iterator[tuple[NodeRef, dict[str, Any]]]:
    """Every folder, then its jobs, as JSON; with ``env``, resolved as that environment has it."""
    values = repo.load_env(env).constants if env else None
    overrides = load_overrides(repo, env) if env else {}
    for folder in folder_names(repo):
        folder_data = dict(read_json(repo.folder_file(folder)))
        refs = [NodeRef(folder, None), *(NodeRef(folder, str(j)) for j in folder_data["jobs"])]
        for ref in refs:
            data = folder_data if ref.job is None else dict(read_json(_job_file(repo, ref)))
            if env is None:
                yield ref, data
            elif belongs(data, env):
                override = overrides.get(_node_id(ref))
                yield ref, resolve_json(apply_override(data, override), repo.config.constants,
                                        values or {})  # fmt: skip


def _job_file(repo: ChainRepo, ref: NodeRef) -> Any:
    assert ref.job is not None
    return repo.job_file(ref.folder, ref.job)


def _match(
    ref: NodeRef,
    data: Mapping[str, Any],
    text: str | None,
    attribute: str | None,
    value: str | None,
) -> dict[str, str]:
    """The fields that answer the search; empty when the node does not."""
    fields = {k: v for k, v in data.items() if isinstance(v, str)}
    matched: dict[str, str] = {}
    if text is not None:
        kind = "job" if ref.job is not None else "folder"
        named = [k for k in _NAME_FIELDS[kind] if text in fields.get(k, "").casefold()]
        if not named:
            return {}
        matched[named[0]] = fields[named[0]]
    if attribute is not None:
        if attribute not in fields or (value and value not in fields[attribute].casefold()):
            return {}
        matched[attribute] = fields[attribute]
    elif value is not None:
        hits = {k: v for k, v in fields.items() if value in v.casefold()}
        if not hits:
            return {}
        matched.update(hits)
    return matched


def _node_id(ref: NodeRef) -> str:
    return str(ref) if ref.job is not None else f"{ref.folder}/"


def _parts(*parts: Mapping[str, Any]) -> dict[str, Any]:
    names = ("attributes", "variables", "elements")
    return {name: dict(part) for name, part in zip(names, parts, strict=True) if part}
