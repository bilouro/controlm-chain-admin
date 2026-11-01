"""The environment-letter rule: names carry the environment as a prefix letter (``UP77_X``).

The letter appears at every *token boundary* of a name, not only at its start: a condition name
such as ``UP77_INIT-UP77_LOAD_OK`` embeds two job names. A boundary is the start of the value
or any position not preceded by a letter or digit (after ``-``, ``_``, ``/``, ``.`` ...).

* Import strips the source environment's letter wherever ``<letter><bare prefix>`` occurs at a
  boundary in a whitelisted attribute.
* Export prepends the target environment's letter wherever a bare prefix occurs at a boundary.
* A source value with a bare prefix at a boundary and no letter in front (``P77_RAW``, or a
  token like ``_RC_X`` that merely looks like a resource) is ambiguous: it is stored whole as
  ``literal:<value>`` and exported unchanged in every environment. Import reports these marks.
* A value carrying another known environment's letter (``PP77_X`` in a UAT export) is kept and
  reported as suspicious.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from controlm_chain_admin.core.model import XmlComment, XmlDocument, XmlElement

LITERAL_PREFIX = "literal:"

#: Attributes whose values carry the environment letter (names of folders, jobs, conditions,
#: resources, controls and calendars). ``NAME`` is harmless on VARIABLE (``%%...``) and others.
DEFAULT_LETTER_ATTRIBUTES: tuple[str, ...] = (
    "FOLDER_NAME",
    "JOBNAME",
    "MEMNAME",
    "PARENT_FOLDER",
    "SUB_APPLICATION",
    "NAME",
)


@dataclass(frozen=True)
class LetterRule:
    """Bare prefixes (``P77``, ``RQ_``, ``RC_``) and the attributes the rule applies to."""

    prefixes: tuple[str, ...] = ()
    attributes: tuple[str, ...] = DEFAULT_LETTER_ATTRIBUTES

    @property
    def enabled(self) -> bool:
        return bool(self.prefixes)

    def _alternation(self) -> str:
        return "|".join(re.escape(p) for p in sorted(self.prefixes, key=len, reverse=True))

    def boundary_pattern(self) -> re.Pattern[str]:
        """At a token boundary: an upper-case letter followed by a prefix, or a bare prefix."""
        alt = self._alternation()
        return re.compile(rf"(?<![A-Za-z0-9])(?:(?P<letter>[A-Z])(?={alt})|(?={alt}))")

    def bare_pattern(self) -> re.Pattern[str]:
        """A bare prefix at a token boundary (export side)."""
        return re.compile(rf"(?<![A-Za-z0-9])(?={self._alternation()})")


@dataclass(frozen=True)
class LetterReport:
    """What stripping the letter noticed: literal marks added and values of other environments."""

    literal_marks: tuple[str, ...]
    suspicious: tuple[str, ...]


def _map_attrs(
    document: XmlDocument, rule: LetterRule, transform: Callable[[str, str, str], str]
) -> XmlDocument:
    """Apply ``transform(tag, attribute, value)`` to every whitelisted attribute of the tree."""
    attributes = set(rule.attributes)

    def visit(element: XmlElement) -> XmlElement:
        attrs = tuple(
            (key, transform(element.tag, key, value) if key in attributes else value)
            for key, value in element.attrs
        )
        children = tuple(
            child if isinstance(child, XmlComment) else visit(child) for child in element.children
        )
        return replace(element, attrs=attrs, children=children)

    return replace(document, root=visit(document.root))


def strip_letter(
    document: XmlDocument, letter: str, rule: LetterRule, known_letters: Sequence[str]
) -> tuple[XmlDocument, LetterReport]:
    """Remove ``letter`` from prefixed tokens in whitelisted attributes (import direction)."""
    if not rule.enabled:
        return document, LetterReport((), ())
    others = {k for k in known_letters if k != letter}
    pattern = rule.boundary_pattern()
    literal_marks: list[str] = []
    suspicious: list[str] = []

    def transform(tag: str, attribute: str, value: str) -> str:
        bare = False
        other = False

        def repl(match: re.Match[str]) -> str:
            nonlocal bare, other
            found = match.group("letter")
            if found is None:
                bare = True
                return ""
            if found == letter:
                return ""
            if found in others:
                other = True
            return found

        stripped = pattern.sub(repl, value)
        where = f"{tag}/@{attribute}={value}"
        if other:
            suspicious.append(where)
        if bare:
            literal_marks.append(where)
            return LITERAL_PREFIX + value
        return stripped

    stripped = _map_attrs(document, rule, transform)
    return stripped, LetterReport(tuple(literal_marks), tuple(suspicious))


def add_letter(document: XmlDocument, letter: str, rule: LetterRule) -> XmlDocument:
    """Prepend ``letter`` to bare-prefixed tokens in whitelisted attributes (export direction)."""
    if not rule.enabled:
        return document
    pattern = rule.bare_pattern()

    def transform(tag: str, attribute: str, value: str) -> str:
        if value.startswith(LITERAL_PREFIX):
            return value[len(LITERAL_PREFIX) :]
        return pattern.sub(letter, value)

    return _map_attrs(document, rule, transform)
