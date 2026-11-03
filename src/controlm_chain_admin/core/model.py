"""Immutable in-memory model of a Control-M XML export, faithful to the source document.

The export is attribute-only XML: elements carry ordered attributes and child elements, never
text. Keeping attribute order and child order as in the source is what makes a byte-identical
serialization possible.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class XmlComment:
    """An XML comment (``<!--text-->``) kept in place."""

    text: str


@dataclass(frozen=True)
class XmlElement:
    """An element with ordered attributes and ordered children (elements or comments)."""

    tag: str
    attrs: tuple[tuple[str, str], ...] = ()
    children: tuple[XmlElement | XmlComment, ...] = ()

    def get(self, name: str, default: str | None = None) -> str | None:
        """Value of attribute ``name`` or ``default``."""
        for key, value in self.attrs:
            if key == name:
                return value
        return default

    def attrs_dict(self) -> dict[str, str]:
        """Attributes as a dict (insertion order preserved)."""
        return dict(self.attrs)

    def elements(self) -> Iterator[XmlElement]:
        """Child elements, skipping comments."""
        for child in self.children:
            if isinstance(child, XmlElement):
                yield child

    def find_all(self, tag: str) -> tuple[XmlElement, ...]:
        """Direct child elements with the given tag."""
        return tuple(child for child in self.elements() if child.tag == tag)


@dataclass(frozen=True)
class XmlDeclaration:
    """The ``<?xml ...?>`` declaration. ``standalone`` is ``None`` when absent."""

    version: str = "1.0"
    encoding: str | None = "utf-8"
    standalone: bool | None = None


@dataclass(frozen=True)
class XmlDocument:
    """A whole export: declaration, prolog comments and the root element."""

    root: XmlElement
    declaration: XmlDeclaration = field(default_factory=XmlDeclaration)
    prolog_comments: tuple[str, ...] = ()
    newline: str = "\n"  # "\r\n" for exports saved on Windows
    bom: bool = False  # a UTF-8 byte order mark before the declaration
