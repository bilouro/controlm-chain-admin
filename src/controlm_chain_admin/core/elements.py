"""Naming one line of a folder or job: a condition, a SHOUT, an ON block, an action inside one.

A *locator* names an element by its tag and what tells it from its siblings, segment by
segment from the node down: ``OUTCOND[link=P77_A-P77_B_OK,ODATE=ODAT]`` is a condition (by
its link id, as the JSON holds it), ``ON[STMT=*,CODE=NOTOK]/DOMAIL[0]`` the first DOMAIL of an
ON block. Tags with identity
attributes (:data:`IDENTITY`) are named by them, the others by their position among the
siblings of their tag; a key two siblings share gets ``#2`` on the second one.

Locators outlive positions: an exception written for one environment still finds its line
after the base gained or lost other lines.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from controlm_chain_admin.core.jsonmodel import CHILDREN_KEY, TAG_KEY

#: The attributes that tell one element of a tag from its siblings.
IDENTITY: Mapping[str, tuple[str, ...]] = {
    "INCOND": ("link", "ODATE"),  # conditions reference a link id in place of their NAME
    "OUTCOND": ("link", "ODATE"),
    "DOCOND": ("link", "ODATE"),
    "CONTROL": ("NAME",),
    "QUANTITATIVE": ("NAME",),
    "SHOUT": ("WHEN", "DEST"),
    "ON": ("STMT", "CODE"),
    "RULE_BASED_CALENDAR": ("NAME",),
    "RULE_BASED_CALENDARS": ("NAME",),
    "TAG": ("NAME",),
    "VARIABLE": ("NAME",),
}

_SEGMENT = re.compile(
    r"^(?P<tag>[A-Za-z_#][A-Za-z0-9_#]*)\[(?P<inside>.*)\](?:#(?P<ordinal>\d+))?$"
)
_SPLIT_SEGMENTS = re.compile(r"/(?=[A-Za-z_#][A-Za-z0-9_#]*\[)")
_SPLIT_PAIRS = re.compile(r",(?=[A-Za-z_][A-Za-z0-9_]*=)")


@dataclass(frozen=True)
class Segment:
    """One step of a locator: a tag, and its key attributes or its position among its tag."""

    tag: str
    where: Mapping[str, str] = field(default_factory=dict)
    position: int | None = None
    ordinal: int = 1  # the n-th sibling with this key (1-based)

    def __str__(self) -> str:
        if self.position is not None:
            return f"{self.tag}[{self.position}]"
        inside = ",".join(f"{k}={v}" for k, v in self.where.items())
        suffix = f"#{self.ordinal}" if self.ordinal > 1 else ""
        return f"{self.tag}[{inside}]{suffix}"

    def matches(self, element: Mapping[str, Any]) -> bool:
        return all(element.get(k) == v for k, v in self.where.items())


def parse_locator(text: str) -> tuple[Segment, ...]:
    """The segments of a locator; raises ``ValueError`` on anything else."""
    segments: list[Segment] = []
    for part in _SPLIT_SEGMENTS.split(text):
        match = _SEGMENT.match(part)
        if match is None:
            raise ValueError(f"not a locator: {text!r}")
        inside = match["inside"]
        ordinal = int(match["ordinal"] or 1)
        if inside.isdigit():
            segments.append(Segment(match["tag"], position=int(inside), ordinal=ordinal))
            continue
        where: dict[str, str] = {}
        for pair in _SPLIT_PAIRS.split(inside) if inside else ():
            key, equals, value = pair.partition("=")
            if not equals:
                raise ValueError(f"not a locator: {text!r}")
            where[key] = value
        segments.append(Segment(match["tag"], where, ordinal=ordinal))
    return tuple(segments)


def siblings(parent: Mapping[str, Any], tag: str) -> list[tuple[str, int, Mapping[str, Any]]]:
    """The elements of ``tag`` inside ``parent``: (the key holding them, index, element)."""
    grouped = parent.get(tag)
    if isinstance(grouped, list):
        return [(tag, i, e) for i, e in enumerate(grouped) if isinstance(e, dict)]
    ordered = parent.get(CHILDREN_KEY)
    if isinstance(ordered, list):
        return [
            (CHILDREN_KEY, i, e)
            for i, e in enumerate(ordered)
            if isinstance(e, dict) and e.get(TAG_KEY) == tag
        ]
    return []


def elements_of(parent: Mapping[str, Any]) -> Iterator[tuple[str, int, str, Mapping[str, Any]]]:
    """Every element inside ``parent``, in document order: (key, index, tag, element)."""
    ordered = parent.get(CHILDREN_KEY)
    if isinstance(ordered, list):
        for i, e in enumerate(ordered):
            if isinstance(e, dict):
                yield CHILDREN_KEY, i, str(e.get(TAG_KEY, "")), e
        return
    for key, value in parent.items():
        if isinstance(value, list):
            for i, e in enumerate(value):
                if isinstance(e, dict) and TAG_KEY not in e:
                    yield key, i, key, e


def segment_of(parent: Mapping[str, Any], tag: str, index: int) -> Segment:
    """The segment naming the element at ``index`` of ``tag``'s siblings in ``parent``."""
    same = siblings(parent, tag)
    element = same[index][2]
    identity = IDENTITY.get(tag, ())
    if identity and all(isinstance(element.get(k), str) for k in identity):
        where = {k: str(element[k]) for k in identity}
        alike = [e for _, _, e in same if all(e.get(k) == v for k, v in where.items())]
        ordinal = next(n for n, e in enumerate(alike, 1) if e is element)
        return Segment(tag, where, ordinal=ordinal)
    return Segment(tag, position=index)


def find(parent: Mapping[str, Any], segment: Segment) -> tuple[str, int] | None:
    """Where ``segment`` is inside ``parent``: the key holding the list and the index."""
    same = siblings(parent, segment.tag)
    if segment.position is not None:
        if 0 <= segment.position < len(same):
            key, index, _ = same[segment.position]
            return key, index
        return None
    matches = [(key, index) for key, index, e in same if segment.matches(e)]
    if len(matches) >= segment.ordinal:
        return matches[segment.ordinal - 1]
    return None


def resolve(node: Mapping[str, Any], segments: tuple[Segment, ...]) -> Mapping[str, Any] | None:
    """The element the segments lead to, or None when any step is missing."""
    current: Mapping[str, Any] = node
    for segment in segments:
        found = find(current, segment)
        if found is None:
            return None
        key, index = found
        current = current[key][index]
    return current


def locator(parent: Mapping[str, Any], tag: str, index: int, prefix: str = "") -> str:
    """The locator text of an element, under ``prefix`` (its parent's locator)."""
    segment = str(segment_of(parent, tag, index))
    return f"{prefix}/{segment}" if prefix else segment
