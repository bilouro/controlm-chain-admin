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

from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.model import XmlComment, XmlDocument, XmlElement

JsonDict = dict[str, Any]
Order = Mapping[str, Sequence[str]]
Seen = Mapping[str, Sequence[tuple[str, ...]]]  # the sequences an export shows, per tag
OWN_ORDER_KEY = "@order"  # metadata of an element written in an order of its own

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
        unknown = [group_tag for group_tag in groups if group_tag not in order]
        for group_tag in [*order, *unknown]:  # a group the order never saw goes last
            for entry in groups.get(group_tag, ()):
                if not isinstance(entry, Mapping):
                    raise ModelError(
                        f"<{tag}>: {group_tag} holds {type(entry).__name__} values, not elements"
                    )
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


def observe_sequences(
    document: XmlDocument,
) -> tuple[dict[str, tuple[tuple[str, ...], ...]], dict[str, tuple[tuple[str, ...], ...]]]:
    """What a document shows: the distinct attribute sequences of each tag, and the distinct
    child-tag runs of each grouped parent, in order of first appearance.

    Only these are facts. One order derived from them also places names that never meet in
    one element (``DAYS`` and ``WEEKDAYS`` of a job), and that place is arbitrary: two exports
    may put them either way, so :func:`merge_orders` takes the sequences, not such an order.
    A grouped parent whose children do not follow one global order is left out, so its
    children are stored as an ordered list.
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

    children = {
        tag: tuple(seqs)
        for tag, seqs in child_seqs.items()
        if tag not in ungroupable and _topological(seqs) is not None
    }
    return {tag: tuple(seqs) for tag, seqs in attr_seqs.items()}, children


def merge_orders(existing: Order, seen: Seen) -> dict[str, tuple[str, ...]]:
    """Extend the recorded orders with the sequences an export shows (:func:`observe_sequences`).

    The recorded order stays as it is; a name new to it goes where the sequences put it. A
    sequence that contradicts the order (an element written another way, by another client)
    does not change it: that element keeps its own order in its metadata
    (:func:`with_own_order`), and the names only it has go last.
    """
    merged: dict[str, tuple[str, ...]] = {}
    for tag in [*existing, *(t for t in seen if t not in existing)]:
        accepted = [tuple(existing[tag])] if tag in existing else []
        for sequence in seen.get(tag, ()):
            if _topological([*accepted, sequence]) is not None:
                accepted.append(sequence)
        order = _topological(accepted) or ()
        rest = (name for sequence in seen.get(tag, ()) for name in sequence if name not in order)
        merged[tag] = (*order, *dict.fromkeys(rest))
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


def with_own_order(
    attrs: Sequence[tuple[str, str]], meta: Mapping[str, str], order: Sequence[str]
) -> dict[str, str]:
    """The metadata of an element, with its own attribute order (``OWN_ORDER_KEY``) when the
    canonical order would write its attributes another way."""
    names = [key for key, _ in attrs]
    if [key for key, _ in merge_volatile(dict(attrs), {}, order)] == names:
        return dict(meta)
    return {**meta, OWN_ORDER_KEY: " ".join(names)}


def merge_volatile(
    attrs: Mapping[str, str], meta: Mapping[str, str], order: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    """Recombine functional attributes and metadata in the canonical attribute order, or in
    the element's own order when its metadata has one (:func:`with_own_order`).

    Attributes unknown to the order (added by hand after the import) go last, in their order.
    """
    if OWN_ORDER_KEY in meta:
        order = meta[OWN_ORDER_KEY].split(" ")
        meta = {key: value for key, value in meta.items() if key != OWN_ORDER_KEY}
    clash = sorted(set(attrs) & set(meta))
    if clash:
        raise ModelError(f"attributes present both in the element and in its metadata: {clash}")
    combined: dict[str, str] = {**attrs, **meta}
    position = {name: index for index, name in enumerate(order)}
    known = sorted((k for k in combined if k in position), key=position.__getitem__)
    unknown = [k for k in combined if k not in position]
    return tuple((k, combined[k]) for k in [*known, *unknown])
