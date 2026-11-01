"""Read a Control-M XML export into the model and write it back byte-for-byte.

Parsing uses the standard-library expat parser with namespace processing off, so the root's
``xmlns:xsi`` / ``xsi:noNamespaceSchemaLocation`` are plain attributes and the source attribute
order is kept. Serialization reproduces the layout written by the Control-M client: UTF-8, LF,
four-space indentation, ``<X ... />`` for empty elements, ``&amp; &lt; &gt; &quot;`` and
``&#x9; &#xA; &#xD;`` escapes inside attribute values, apostrophes literal.
"""

from __future__ import annotations

import xml.parsers.expat
from dataclasses import dataclass, field

from controlm_chain_admin.core.errors import XmlFormatError
from controlm_chain_admin.core.model import XmlComment, XmlDeclaration, XmlDocument, XmlElement

INDENT = "    "  # four spaces per level, as written by the Control-M client

_ATTR_ESCAPES = (
    ("&", "&amp;"),  # must be first
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("\t", "&#x9;"),
    ("\n", "&#xA;"),
    ("\r", "&#xD;"),
)


@dataclass
class _Builder:
    """Mutable element under construction; frozen into an :class:`XmlElement` on close."""

    tag: str
    attrs: tuple[tuple[str, str], ...]
    children: list[XmlElement | XmlComment] = field(default_factory=list)


class _Parser:
    def __init__(self) -> None:
        self.declaration: XmlDeclaration | None = None
        self.prolog_comments: list[str] = []
        self.root: XmlElement | None = None
        self._stack: list[_Builder] = []

    # expat handlers -------------------------------------------------------
    def xml_decl(self, version: str, encoding: str | None, standalone: int) -> None:
        self.declaration = XmlDeclaration(
            version=version,
            encoding=encoding,
            standalone=None if standalone == -1 else bool(standalone),
        )

    def comment(self, text: str) -> None:
        if self._stack:
            self._stack[-1].children.append(XmlComment(text))
        elif self.root is None:
            self.prolog_comments.append(text)
        else:
            raise XmlFormatError("comment after the root element is not supported")

    def start(self, name: str, attrs: list[str]) -> None:
        pairs = tuple(zip(attrs[0::2], attrs[1::2], strict=True))
        self._stack.append(_Builder(name, pairs))

    def end(self, name: str) -> None:
        builder = self._stack.pop()
        element = XmlElement(builder.tag, builder.attrs, tuple(builder.children))
        if self._stack:
            self._stack[-1].children.append(element)
        else:
            self.root = element

    def characters(self, text: str) -> None:
        if text.strip():
            where = self._stack[-1].tag if self._stack else "document"
            raise XmlFormatError(f"unexpected text content in <{where}>: {text.strip()[:40]!r}")

    # driver ---------------------------------------------------------------
    def parse(self, data: bytes) -> XmlDocument:
        parser = xml.parsers.expat.ParserCreate(namespace_separator=None)
        parser.ordered_attributes = True
        parser.XmlDeclHandler = self.xml_decl
        parser.CommentHandler = self.comment
        parser.StartElementHandler = self.start
        parser.EndElementHandler = self.end
        parser.CharacterDataHandler = self.characters
        try:
            parser.Parse(data, True)
        except xml.parsers.expat.ExpatError as exc:
            raise XmlFormatError(f"malformed XML: {exc}") from exc
        if self.declaration is None:
            raise XmlFormatError("missing XML declaration (<?xml ...?>)")
        if self.root is None:
            raise XmlFormatError("missing root element")
        return XmlDocument(
            root=self.root,
            declaration=self.declaration,
            prolog_comments=tuple(self.prolog_comments),
        )


def parse_xml(data: bytes) -> XmlDocument:
    """Parse export bytes into an :class:`XmlDocument`, keeping attribute and child order."""
    return _Parser().parse(data)


def escape_attr(value: str) -> str:
    """Escape an attribute value the way the Control-M client does."""
    for raw, escaped in _ATTR_ESCAPES:
        value = value.replace(raw, escaped)
    return value


def _write_element(element: XmlElement, depth: int, out: list[str]) -> None:
    pad = INDENT * depth
    attrs = "".join(f' {key}="{escape_attr(value)}"' for key, value in element.attrs)
    if not element.children:
        out.append(f"{pad}<{element.tag}{attrs} />\n")
        return
    out.append(f"{pad}<{element.tag}{attrs}>\n")
    for child in element.children:
        if isinstance(child, XmlComment):
            out.append(f"{pad}{INDENT}<!--{child.text}-->\n")
        else:
            _write_element(child, depth + 1, out)
    out.append(f"{pad}</{element.tag}>\n")


def _declaration_line(declaration: XmlDeclaration) -> str:
    encoding = f' encoding="{declaration.encoding}"' if declaration.encoding else ""
    standalone = ""
    if declaration.standalone is not None:
        standalone = f' standalone="{"yes" if declaration.standalone else "no"}"'
    return f'<?xml version="{declaration.version}"{encoding}{standalone}?>\n'


def serialize_xml(document: XmlDocument) -> bytes:
    """Write the document in the exact layout of a Control-M export."""
    out = [_declaration_line(document.declaration)]
    out.extend(f"<!--{text}-->\n" for text in document.prolog_comments)
    _write_element(document.root, 0, out)
    return "".join(out).encode("utf-8")
