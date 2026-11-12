"""What a file of the repository holds, read once and remembered until the file changes.

Every page and every command reads the same small files again: the folders, their jobs, the
links. Opening a file is cheap on a local disk and costly where each one is inspected (an
antivirus) or travels (a network drive), so the text of a file is kept by its path with the
size and the time it had; a later reading asks only whether those changed, which opens
nothing. The first reading of a clean git working tree comes from git in one piece (one
``git archive``) instead of file by file.

Memory directories (:mod:`controlm_chain_admin.core.memfs`) are not kept here: they cost
nothing to read.
"""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
import threading
from pathlib import Path
from time import monotonic, time_ns
from typing import Any

from controlm_chain_admin.core.memfs import is_memory
from controlm_chain_admin.core.timing import count

#: files remembered at most; the ones read longest ago go first
LIMIT = 120_000
#: seconds between two looks at the commit a working tree is on
_RECHECK = 2.0
#: A file changed this shortly before it was remembered may change again without its time
#: moving (the clock of a file system has a grain): it is read again until that has passed.
RACY_NS = 50_000_000

_LOCK = threading.RLock()
#: path -> (modification time, size, text with \n line ends, whether the bytes are that text,
#: when it was remembered)
_Entry = tuple[int, int, str, bool, int]
_TEXTS: dict[str, _Entry] = {}
_TOPS: dict[str, Path | None] = {}  # directory -> the top of its git working tree, if any
_PRIMED: dict[str, tuple[str, float]] = {}  # git top -> (commit read from git, looked at)


def clear() -> None:
    """Forget everything (tests, and a process that wants its memory back)."""
    with _LOCK:
        _TEXTS.clear()
        _TOPS.clear()
        _PRIMED.clear()


def _keep(key: str, modified: int, size: int, text: str, exact: bool) -> None:
    with _LOCK:
        _TEXTS.pop(key, None)  # asked for again: among the latest
        _TEXTS[key] = (modified, size, text, exact, time_ns())
        if len(_TEXTS) > LIMIT:
            for old in list(_TEXTS)[: LIMIT // 10]:
                del _TEXTS[old]


def _decode(data: bytes) -> tuple[str, bool]:
    """The text as a file opened in text mode gives it, and whether nothing was translated."""
    text = data.decode("utf-8")
    if "\r" not in text:
        return text, True
    return text.replace("\r\n", "\n").replace("\r", "\n"), False


def _same(kept: _Entry | None, status: os.stat_result) -> bool:
    """Whether the file is surely as it was when remembered: the same time and size, and a
    time old enough then that a later change would have moved it."""
    return (
        kept is not None
        and kept[:2] == (status.st_mtime_ns, status.st_size)
        and kept[0] + RACY_NS <= kept[4]
    )


def read_text(path: Any) -> str:
    """The UTF-8 text of ``path`` with ``\\n`` line ends; from memory when the file is as it
    was. Raises ``FileNotFoundError`` like opening it would."""
    if is_memory(path):
        return str(path.read_text(encoding="utf-8"))
    key = os.fspath(path)
    status = os.stat(key)
    kept = _TEXTS.get(key)
    if not _same(kept, status) and _prime(Path(key)):
        kept = _TEXTS.get(key)
    if kept is not None and _same(kept, status):
        count("files_remembered")
        return kept[2]
    with open(key, "rb") as handle:
        data = handle.read()
    count("files_read")
    text, exact = _decode(data)
    _keep(key, status.st_mtime_ns, status.st_size, text, exact)
    return text


def written(path: Any, text: str) -> None:
    """``path`` was just written with ``text`` (``\\n`` line ends, UTF-8): remember it."""
    if is_memory(path):
        return
    key = os.fspath(path)
    try:
        status = os.stat(key)
    except OSError:
        return
    _keep(key, status.st_mtime_ns, status.st_size, text, True)


def holds(path: Any, text: str) -> bool:
    """Whether ``path`` is known to hold exactly ``text`` already: writing it would change
    nothing, so it need not be written."""
    if is_memory(path):
        return bool(path.is_file() and path.read_bytes() == text.encode("utf-8"))
    key = os.fspath(path)
    kept = _TEXTS.get(key)
    if kept is None or not kept[3] or kept[2] != text:
        return False
    try:
        status = os.stat(key)
    except OSError:
        return False
    return _same(kept, status)


# ---------------------------------------------------------------- the first reading, from git


def _top(directory: Path) -> Path | None:
    """The top of the git working tree ``directory`` is in, looked for once per directory."""
    key = str(directory)
    if key in _TOPS:
        return _TOPS[key]
    found: Path | None = None
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            found = candidate
            break
    with _LOCK:
        _TOPS[key] = found
    return found


def _git(top: Path, *args: str) -> bytes | None:
    count("git_calls")
    try:
        done = subprocess.run(["git", "-C", str(top), *args], capture_output=True, check=False)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def _prime(path: Path) -> bool:
    """Read the whole commit the working tree of ``path`` is on from git, in one piece, and
    remember every file the working tree still has as committed. True when it did; at most
    once per commit, and it looks at the commit every other second at most."""
    top = _top(path.parent)
    if top is None:
        return False
    key, now = str(top), monotonic()
    with _LOCK:
        before = _PRIMED.get(key)
        if before is not None and now - before[1] < _RECHECK:
            return False
        _PRIMED[key] = (before[0] if before else "", now)
    head = _git(top, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if head is None:
        return False
    sha = head.decode().strip()
    if before is not None and before[0] == sha:
        return False
    changed = _git(top, "status", "--porcelain=v1", "-z", "--untracked-files=no")
    archive = _git(top, "-c", "core.autocrlf=false", "archive", "--format=tar", sha)
    if changed is None or archive is None:
        return False
    dirty = set()
    entries = changed.decode("utf-8", "replace").split("\0")
    for entry in entries:
        dirty.add(entry[3:] if len(entry) > 3 and entry[2] == " " else entry)  # a rename's old
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            if member.name in dirty or ".." in member.name.split("/"):
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            data = source.read()
            file = os.path.join(key, *member.name.split("/"))
            try:
                status = os.stat(file)
                text, exact = _decode(data)
            except (OSError, UnicodeDecodeError):
                continue
            if status.st_size == len(data):
                _keep(file, status.st_mtime_ns, status.st_size, text, exact)
            elif exact and status.st_size == len(data) + data.count(b"\n"):
                # checked out with \r\n line ends (core.autocrlf): the same text
                _keep(file, status.st_mtime_ns, status.st_size, text, False)
    with _LOCK:
        _PRIMED[key] = (sha, now)
    count("trees_from_git")
    return True
