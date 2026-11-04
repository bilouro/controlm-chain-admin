"""Read-only inspection: distinct attribute values and single nodes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from controlm_chain_admin.core import ops
from controlm_chain_admin.core.constants import resolve_json
from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.jsonmodel import OWN_ORDER_KEY
from controlm_chain_admin.core.links import NodeRef
from controlm_chain_admin.core.model import XmlDocument, XmlElement
from controlm_chain_admin.core.overrides import apply_override, load_overrides
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json

FOLDER_TAGS = ("SMART_FOLDER", "FOLDER")


@dataclass(frozen=True)
class DistinctValue:
    value: str
    count: int
    samples: tuple[str, ...]  # up to three node identities where the value occurs

    def to_json(self) -> dict[str, Any]:
        return {"value": self.value, "count": self.count, "samples": list(self.samples)}


def _parse_spec(spec: str) -> tuple[str | None, str, dict[str, str]]:
    from controlm_chain_admin.core.constants import parse_spec  # local: avoids an import cycle

    selector = parse_spec(spec)
    return selector.tag, selector.attribute, selector.where


def _identity(stack: Sequence[XmlElement]) -> str:
    """``FOLDER/JOB`` of the nearest job ancestor-or-self, or ``FOLDER/`` at folder level."""
    folder = next((e.get("FOLDER_NAME") for e in stack if e.tag in FOLDER_TAGS), None)
    job = next((e.get("JOBNAME") for e in reversed(stack) if e.tag == "JOB"), None)
    return f"{folder or ''}/{job or ''}"


def distinct_values(
    document: XmlDocument, specs: Sequence[str], samples: int = 3
) -> dict[str, tuple[DistinctValue, ...]]:
    """Distinct values per spec. A spec is ``ATTR`` (any element) or ``TAG/@ATTR``.

    Values are sorted by descending count, then by value. Each value lists up to ``samples``
    node identities (``FOLDER/JOB`` or ``FOLDER/``) where it occurs.
    """
    parsed = [(spec, *_parse_spec(spec)) for spec in specs]
    counts: dict[str, dict[str, int]] = {spec: {} for spec in specs}
    seen: dict[str, dict[str, list[str]]] = {spec: {} for spec in specs}
    stack: list[XmlElement] = []

    def walk(element: XmlElement) -> None:
        stack.append(element)
        identity = _identity(stack)
        for spec, tag, attr, where in parsed:
            if tag is not None and element.tag != tag:
                continue
            if any(element.get(k) != v for k, v in where.items()):
                continue
            value = element.get(attr)
            if value is None:
                continue
            counts[spec][value] = counts[spec].get(value, 0) + 1
            places = seen[spec].setdefault(value, [])
            if len(places) < samples and identity not in places:
                places.append(identity)
        for child in element.elements():
            walk(child)
        stack.pop()

    walk(document.root)
    return {
        spec: tuple(
            DistinctValue(value, count, tuple(seen[spec][value]))
            for value, count in sorted(counts[spec].items(), key=lambda kv: (-kv[1], kv[0]))
        )
        for spec in specs
    }


def load_document(repo: ChainRepo) -> XmlDocument:
    """The repository as one neutral document: names without letter, metadata merged back."""
    return ops.load_document(repo)[0]


def show_node(repo: ChainRepo, node: str, env: str | None = None) -> dict[str, Any]:
    """The JSON of a job (``FOLDER/JOB``) or folder (``FOLDER/``) with its volatile metadata;
    with ``env``, as that environment has it: its exception applied and its values in place of
    the constants (one without a value there stays ``@{name}``)."""
    ref = NodeRef.parse(node)
    data = _node_json(repo, ref)
    if env is None:
        return data
    repo = load_repo(repo.root)
    values = repo.load_env(env).constants  # unknown environment: UnknownEnvironment
    override = load_overrides(repo, env).get(str(ref))
    resolved: dict[str, Any] = resolve_json(
        apply_override(data, override), repo.config.constants, values
    )
    return resolved


def _node_json(repo: ChainRepo, ref: NodeRef) -> dict[str, Any]:
    if not repo.folder_file(ref.folder).is_file():
        raise ModelError(f"unknown folder {ref.folder!r}")
    meta_file = repo.folder_meta_file(ref.folder)
    meta: dict[str, Any] = (
        read_json(meta_file) if meta_file.exists() else {"attrs": {}, "jobs": {}}
    )
    if ref.job is None:
        data = dict(read_json(repo.folder_file(ref.folder)))
        return {**data, "meta": _shown(meta.get("attrs", {}))}
    job_file = repo.job_file(ref.folder, ref.job)
    if not job_file.is_file():
        raise ModelError(f"unknown job {ref.job!r} in folder {ref.folder!r}")
    data = dict(read_json(job_file))
    return {**data, "meta": _shown(meta.get("jobs", {}).get(ref.job, {}))}


def _shown(meta: dict[str, str]) -> dict[str, str]:
    """The volatile attributes of a node, without the order it was written in."""
    return {key: value for key, value in meta.items() if key != OWN_ORDER_KEY}
