"""Raw-bytes helpers over a Control-M export, used as an independent oracle in tests.

They never parse XML: a folder is the byte range of a top-level ``<SMART_FOLDER ...>`` or
``<FOLDER ...>`` element at indentation 4, so comparisons against the product code do not share
its implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A top-level folder: opening tag at indentation 4 up to its closing tag at indentation 4,
# followed by the newline. Non-greedy so each folder is matched separately.
_FOLDER_RE = re.compile(
    rb"^    <(SMART_FOLDER|FOLDER)\b.*?\n    </\1>\n",
    re.DOTALL | re.MULTILINE,
)
_FOLDER_NAME_RE = re.compile(rb'\sFOLDER_NAME="([^"]*)"')
_APPLICATION_RE = re.compile(rb'\sAPPLICATION="([^"]*)"')


@dataclass(frozen=True)
class RawFolder:
    """Byte range of one top-level folder element, with its identity attributes."""

    name: str
    application: str | None
    start: int
    end: int  # exclusive; includes the trailing newline


@dataclass(frozen=True)
class RawExport:
    header: bytes
    folders: tuple[RawFolder, ...]
    footer: bytes


def _attr(opening_tag: bytes, pattern: re.Pattern[bytes]) -> str | None:
    match = pattern.search(opening_tag)
    return match.group(1).decode("utf-8") if match else None


def split_folders(data: bytes) -> RawExport:
    """Split an export into header bytes, top-level folder ranges and footer bytes."""
    folders: list[RawFolder] = []
    for match in _FOLDER_RE.finditer(data):
        opening_tag = data[match.start() : data.index(b">", match.start()) + 1]
        folders.append(
            RawFolder(
                name=_attr(opening_tag, _FOLDER_NAME_RE) or "",
                application=_attr(opening_tag, _APPLICATION_RE),
                start=match.start(),
                end=match.end(),
            )
        )
    if not folders:
        raise ValueError("no top-level folder element found")
    return RawExport(
        header=data[: folders[0].start],
        folders=tuple(folders),
        footer=data[folders[-1].end :],
    )


def filter_applications(data: bytes, keep: set[str]) -> bytes:
    """Return the export restricted to the folders whose APPLICATION is in ``keep``."""
    raw = split_folders(data)
    body = b"".join(data[f.start : f.end] for f in raw.folders if f.application in keep)
    return raw.header + body + raw.footer
