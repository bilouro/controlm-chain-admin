"""Conversion between :class:`XmlElement` trees and the JSON shape stored in a chain repository.

Shape of an element as JSON:

* attributes are top-level string entries, in source order (the XML attribute names are kept);
* when the parent tag is one of :data:`GROUPED_PARENTS` and has a canonical child order, child
  elements are grouped by tag under the tag name, each group being a list of element dicts;
* otherwise (ON blocks, unknown parents, parents with comments or an unexpected order) the
  children are an ordered ``"children"`` list where each entry carries its ``"tag"``; a
  comment is ``{"tag": "#comment", "text": ...}``.

Lower-case keys are reserved for this tool (``children``, ``tag``, ``jobs``, ``envs`` ...);
Control-M attribute and element names are upper-case, so the two never clash.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from controlm_chain_admin.core.errors import ModelError, OrderConflict
from controlm_chain_admin.core.model import XmlComment, XmlDocument, XmlElement

JsonDict = dict[str, Any]
Order = Mapping[str, Sequence[str]]

COMMENT_TAG = "#comment"
CHILDREN_KEY = "children"
TAG_KEY = "tag"

#: Parents whose children are grouped by tag in JSON. Their child order was measured to be
#: globally consistent in real exports; ON blocks are not (DO* actions interleave freely).
GROUPED_PARENTS: tuple[str, ...] = ("DEFTABLE", "SMART_FOLDER", "FOLDER", "JOB")


# ---------------------------------------------------------------- element -> JSON


def _can_group(element: XmlElement, order: Sequence[str]) -> bool:
    if any(isinstance(child, XmlComment) for child in element.children):
        return False
    positions = [order.index(c.tag) if c.tag in order else -1 for c in element.elements()]
    return all(p >= 0 for p in positions) and positions == sorted(positions)


def element_to_json(element: XmlElement, child_order: Order) -> JsonDict:
    """Convert an element (and its subtree) to the repository JSON shape."""
    data: JsonDict = dict(element.attrs)
    if not element.children:
        return data
    order = child_order.get(element.tag)
    if order is not None and _can_group(element, order):
        groups: dict[str, list[JsonDict]] = {}
        for child in element.elements():
            groups.setdefault(child.tag, []).append(element_to_json(child, child_order))
        for tag in order:
            if tag in groups:
                data[tag] = groups[tag]
        return data
    data[CHILDREN_KEY] = [_child_to_json(child, child_order) for child in element.children]
    return data


def _child_to_json(child: XmlElement | XmlComment, child_order: Order) -> JsonDict:
    if isinstance(child, XmlComment):
        return {TAG_KEY: COMMENT_TAG, "text": child.text}
    return {TAG_KEY: child.tag, **element_to_json(child, child_order)}


# ---------------------------------------------------------------- JSON -> element


def json_to_element(tag: str, data: Mapping[str, Any], child_order: Order) -> XmlElement:
    """Rebuild an element from its JSON shape (inverse of :func:`element_to_json`)."""
    attrs: list[tuple[str, str]] = []
    groups: dict[str, list[Any]] = {}
    ordered: list[Any] | None = None
    for key, value in data.items():
        if key == CHILDREN_KEY:
            ordered = list(value)
        elif isinstance(value, str):
            attrs.append((key, value))
        elif isinstance(value, list):
            groups[key] = value
        else:
            raise ModelError(
                f"<{tag}>: unexpected JSON value for {key!r} ({type(value).__name__})"
            )
    if ordered is not None and groups:
        raise ModelError(f"<{tag}>: both 'children' and grouped children present")

    children: list[XmlElement | XmlComment] = []
    if ordered is not None:
        for entry in ordered:
            children.append(_child_from_json(tag, entry, child_order))
    elif groups:
        order = child_order.get(tag)
        if order is None:
            raise ModelError(
                f"<{tag}>: grouped children but no canonical child order in chain.json"
            )
        unknown = sorted(set(groups) - set(order))
        if unknown:
            raise ModelError(f"<{tag}>: child groups not in the canonical order: {unknown}")
        for group_tag in order:
            for entry in groups.get(group_tag, ()):
                children.append(json_to_element(group_tag, entry, child_order))
    return XmlElement(tag, tuple(attrs), tuple(children))


def _child_from_json(parent: str, entry: Any, child_order: Order) -> XmlElement | XmlComment:
    if not isinstance(entry, Mapping) or TAG_KEY not in entry:
        raise ModelError(f"<{parent}>: every entry of 'children' needs a 'tag'")
    child_tag = entry[TAG_KEY]
    if child_tag == COMMENT_TAG:
        return XmlComment(str(entry.get("text", "")))
    rest = {k: v for k, v in entry.items() if k != TAG_KEY}
    return json_to_element(str(child_tag), rest, child_order)


# ---------------------------------------------------------------- orders


def _topological(sequences: Iterable[Sequence[str]]) -> tuple[str, ...] | None:
    """One total order consistent with every sequence, or ``None`` when they contradict.

    Ties are broken by first appearance, so the result follows the first sequence given.
    """
    first_seen: dict[str, int] = {}
    before: dict[str, set[str]] = {}
    for seq in sequences:
        for index, name in enumerate(seq):
            first_seen.setdefault(name, len(first_seen))
            before.setdefault(name, set()).update(seq[index + 1 :])
    indegree = dict.fromkeys(first_seen, 0)
    for successors in before.values():
        for successor in successors:
            indegree[successor] += 1
    ready = sorted((n for n in first_seen if indegree[n] == 0), key=first_seen.__getitem__)
    order: list[str] = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for successor in sorted(before[name], key=first_seen.__getitem__):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
        ready.sort(key=first_seen.__getitem__)
    return tuple(order) if len(order) == len(first_seen) else None


def _child_runs(element: XmlElement) -> tuple[str, ...] | None:
    """Child tags with consecutive repeats collapsed; None when comments or interleaving occur."""
    if any(isinstance(child, XmlComment) for child in element.children):
        return None
    runs: list[str] = []
    for child in element.elements():
        if not runs or runs[-1] != child.tag:
            runs.append(child.tag)
    return None if len(runs) != len(set(runs)) else tuple(runs)


def observe_orders(
    document: XmlDocument,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    """Derive (attribute order per tag, child order per grouped parent) from a document.

    Attribute orders must be consistent (they always are in Control-M exports); a contradiction
    raises :class:`OrderConflict`. A grouped parent whose children do not follow one global
    order is left out of the child order, so its children are stored as an ordered list.
    """
    attr_seqs: dict[str, list[tuple[str, ...]]] = {}
    child_seqs: dict[str, list[tuple[str, ...]]] = {}
    ungroupable: set[str] = set()

    def walk(element: XmlElement) -> None:
        seq = tuple(key for key, _ in element.attrs)
        bucket = attr_seqs.setdefault(element.tag, [])
        if seq not in bucket:
            bucket.append(seq)
        if element.tag in GROUPED_PARENTS and element.children:
            runs = _child_runs(element)
            if runs is None:
                ungroupable.add(element.tag)
            else:
                cbucket = child_seqs.setdefault(element.tag, [])
                if runs not in cbucket:
                    cbucket.append(runs)
        for child in element.elements():
            walk(child)

    walk(document.root)

    attr_order: dict[str, tuple[str, ...]] = {}
    for tag, seqs in attr_seqs.items():
        order = _topological(seqs)
        if order is None:
            raise OrderConflict(f"attribute order of <{tag}> is not consistent across the export")
        attr_order[tag] = order
    child_order: dict[str, tuple[str, ...]] = {}
    for tag, seqs in child_seqs.items():
        if tag in ungroupable:
            continue
        order = _topological(seqs)
        if order is not None:
            child_order[tag] = order
    return attr_order, child_order


def merge_orders(existing: Order, observed: Order) -> dict[str, tuple[str, ...]]:
    """Merge two order tables; raises :class:`OrderConflict` when they contradict each other."""
    merged: dict[str, tuple[str, ...]] = {}
    for tag in [*existing, *(t for t in observed if t not in existing)]:
        sequences = [tuple(existing[tag])] if tag in existing else []
        if tag in observed:
            sequences.append(tuple(observed[tag]))
        order = _topological(sequences)
        if order is None:
            raise OrderConflict(
                f"order of <{tag}> in this export contradicts the order recorded in chain.json"
            )
        merged[tag] = order
    return merged


# ---------------------------------------------------------------- volatile metadata


def split_volatile(
    attrs: Sequence[tuple[str, str]], volatile: Sequence[str]
) -> tuple[tuple[tuple[str, str], ...], dict[str, str]]:
    """Separate volatile export metadata from the functional attributes."""
    volatile_set = set(volatile)
    kept = tuple((k, v) for k, v in attrs if k not in volatile_set)
    meta = {k: v for k, v in attrs if k in volatile_set}
    return kept, meta


def merge_volatile(
    attrs: Mapping[str, str], meta: Mapping[str, str], order: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    """Recombine functional attributes and metadata in the canonical attribute order.

    Attributes unknown to the order (added by hand after the import) go last, in their order.
    """
    clash = sorted(set(attrs) & set(meta))
    if clash:
        raise ModelError(f"attributes present both in the element and in its metadata: {clash}")
    combined: dict[str, str] = {**attrs, **meta}
    position = {name: index for index, name in enumerate(order)}
    known = sorted((k for k in combined if k in position), key=position.__getitem__)
    unknown = [k for k in combined if k not in position]
    return tuple((k, combined[k]) for k in [*known, *unknown])
