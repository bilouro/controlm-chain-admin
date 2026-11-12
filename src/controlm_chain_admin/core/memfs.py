"""Directories that live in memory: the working copies the core used to put on disk.

A comparison takes two branches out of git, rewrites one of them and reads both back; a change
is prepared in a copy of the repository and diffed against it. As real directories that is
thousands of small files written, read and deleted each time, and where every small file is
inspected (an antivirus) or travels (a network drive) it is nearly all of the time an operation
takes. :class:`MemPath` is the part of ``pathlib.Path`` the core uses, over a dictionary: the
same code runs on it, and nothing touches the disk.

The helpers at the end (:func:`copy_tree`, :func:`remove_tree`, :func:`move`) work on both
kinds of path, so a caller need not know which one it holds.
"""

from __future__ import annotations

import io
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

_Parts = tuple[str, ...]


class _Volume:
    """The files and directories of one memory directory."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.files: dict[_Parts, bytes] = {}
        self.children: dict[_Parts, set[str]] = {(): set()}
        self.clock = 0  # goes up with every write: the modification time of what is written
        self.times: dict[_Parts, int] = {}

    def add_dir(self, parts: _Parts) -> None:
        for depth in range(len(parts)):
            self.children.setdefault(parts[:depth], set()).add(parts[depth])
        self.children.setdefault(parts, set())

    def write(self, parts: _Parts, data: bytes) -> None:
        self.add_dir(parts[:-1])
        self.children[parts[:-1]].add(parts[-1])
        self.files[parts] = data
        self.clock += 1
        self.times[parts] = self.clock

    def remove_file(self, parts: _Parts) -> None:
        del self.files[parts]
        self.times.pop(parts, None)
        self.children[parts[:-1]].discard(parts[-1])

    def remove_dir(self, parts: _Parts) -> None:
        for name in list(self.children.get(parts, ())):
            child = (*parts, name)
            if child in self.files:
                self.remove_file(child)
            else:
                self.remove_dir(child)
        self.children.pop(parts, None)
        if parts:
            self.children[parts[:-1]].discard(parts[-1])


class _Stat:
    def __init__(self, size: int, time: int) -> None:
        self.st_size = size
        self.st_mtime_ns = time
        self.st_mtime = time / 1_000_000_000


class _TextWriter(io.StringIO):
    def __init__(self, path: MemPath, encoding: str, newline: str | None, start: str) -> None:
        super().__init__(newline="")  # the text as written: line ends are settled at the end
        self._path, self._encoding, self._newline = path, encoding, newline
        self.write(start)

    def close(self) -> None:
        if not self.closed:
            text = self.getvalue()
            if self._newline is None and os.linesep != "\n":  # as a file opened in text mode
                text = text.replace("\n", os.linesep)
            elif self._newline not in (None, "", "\n"):
                text = text.replace("\n", self._newline)
            self._path.write_bytes(text.encode(self._encoding))
        super().close()


class _BytesWriter(io.BytesIO):
    def __init__(self, path: MemPath, start: bytes) -> None:
        super().__init__()
        self._path = path
        self.write(start)

    def close(self) -> None:
        if not self.closed:
            self._path.write_bytes(self.getvalue())
        super().close()


_Base: Any = Path if TYPE_CHECKING else object  # typed as a path: the core says Path


class MemPath(_Base):  # type: ignore[misc]
    """A path of a memory directory, with the part of ``pathlib.Path`` the core uses."""

    __slots__ = ("_parts", "_volume")

    def __init__(self, volume: _Volume, parts: _Parts = ()) -> None:
        self._volume = volume
        self._parts = parts

    # ------------------------------------------------------------ the path itself

    def _at(self, parts: _Parts) -> MemPath:
        return MemPath(self._volume, parts)

    def __truediv__(self, other: Any) -> MemPath:
        return self.joinpath(other)

    def joinpath(self, *others: Any) -> MemPath:
        parts = list(self._parts)
        for other in others:
            for piece in str(other).replace("\\", "/").split("/"):
                if piece in ("", "."):
                    continue
                if piece == "..":
                    raise ValueError(f"{other!r} leaves the directory")
                parts.append(piece)
        return self._at(tuple(parts))

    @property
    def parts(self) -> _Parts:
        return (str(self._at(())), *self._parts)

    @property
    def name(self) -> str:
        return self._parts[-1] if self._parts else ""

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.name).suffix

    @property
    def stem(self) -> str:
        return PurePosixPath(self.name).stem

    @property
    def parent(self) -> MemPath:
        return self._at(self._parts[:-1])

    def with_name(self, name: str) -> MemPath:
        return self._at((*self._parts[:-1], name))

    def relative_to(self, other: Any) -> PurePosixPath:
        if not isinstance(other, MemPath) or other._volume is not self._volume:
            raise ValueError(f"{self} is not in {other}")
        if self._parts[: len(other._parts)] != other._parts:
            raise ValueError(f"{self} is not in {other}")
        return PurePosixPath(*self._parts[len(other._parts) :])

    def as_posix(self) -> str:
        return str(self)

    def resolve(self, strict: bool = False) -> MemPath:
        return self

    def is_absolute(self) -> bool:
        return True

    def __str__(self) -> str:
        return "/".join((f"<memory {self._volume.label}>", *self._parts))

    def __repr__(self) -> str:
        return f"MemPath({str(self)!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, MemPath)
            and other._volume is self._volume
            and other._parts == self._parts
        )

    def __hash__(self) -> int:
        return hash((id(self._volume), self._parts))

    def __lt__(self, other: MemPath) -> bool:
        return self._parts < other._parts

    # ------------------------------------------------------------ what is there

    def is_file(self) -> bool:
        return self._parts in self._volume.files

    def is_dir(self) -> bool:
        return self._parts in self._volume.children

    def exists(self) -> bool:
        return self.is_file() or self.is_dir()

    def stat(self) -> _Stat:
        data = self._volume.files.get(self._parts)
        if data is None:
            if self.is_dir():
                return _Stat(0, 0)
            raise FileNotFoundError(str(self))
        return _Stat(len(data), self._volume.times.get(self._parts, 0))

    def iterdir(self) -> Iterator[MemPath]:
        if not self.is_dir():
            raise NotADirectoryError(str(self))
        for name in sorted(self._volume.children[self._parts]):
            yield self._at((*self._parts, name))

    def _below(self) -> Iterator[MemPath]:
        for child in self.iterdir():
            yield child
            if child.is_dir():
                yield from child._below()

    def glob(self, pattern: str) -> Iterator[MemPath]:
        wanted = tuple(pattern.split("/"))
        if "**" in wanted:
            raise NotImplementedError(f"glob pattern {pattern!r}")
        if not self.is_dir():
            return
        for path in self._below():
            relative = path._parts[len(self._parts) :]
            if len(relative) == len(wanted) and all(
                fnmatchcase(part, want) for part, want in zip(relative, wanted, strict=True)
            ):
                yield path

    def rglob(self, pattern: str) -> Iterator[MemPath]:
        wanted = tuple(pattern.split("/"))
        if not self.is_dir():
            return
        for path in self._below():
            tail = path._parts[len(self._parts) :][-len(wanted) :]
            if len(tail) == len(wanted) and all(
                fnmatchcase(part, want) for part, want in zip(tail, wanted, strict=True)
            ):
                yield path

    # ------------------------------------------------------------ reading and writing

    def read_bytes(self) -> bytes:
        try:
            return self._volume.files[self._parts]
        except KeyError:
            raise FileNotFoundError(str(self)) from None

    def read_text(self, encoding: str | None = None, errors: str | None = None) -> str:
        with self.open(encoding=encoding, errors=errors) as handle:
            return str(handle.read())

    def write_bytes(self, data: bytes) -> int:
        if self.is_dir():
            raise IsADirectoryError(str(self))
        if self._parts[:-1] not in self._volume.children:
            raise FileNotFoundError(str(self))
        self._volume.write(self._parts, bytes(data))
        return len(data)

    def write_text(
        self,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        with self.open("w", encoding=encoding, errors=errors, newline=newline) as handle:
            handle.write(data)
        return len(data)

    def open(
        self,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> Any:
        binary, kind = "b" in mode, mode.replace("b", "").replace("t", "")
        if kind == "r":
            data = self.read_bytes()
            if binary:
                return io.BytesIO(data)
            text = data.decode(encoding or "utf-8", errors or "strict")
            return io.StringIO(text, newline=newline)  # None: \r\n is read as \n, as on disk
        if kind not in ("w", "a", "x"):
            raise ValueError(f"mode {mode!r} is not supported in a memory directory")
        if kind == "x" and self.exists():
            raise FileExistsError(str(self))
        if self._parts[:-1] not in self._volume.children:
            raise FileNotFoundError(str(self))
        old = self._volume.files.get(self._parts, b"") if kind == "a" else b""
        if binary:
            return _BytesWriter(self, old)
        return _TextWriter(self, encoding or "utf-8", newline, old.decode(encoding or "utf-8"))

    def mkdir(self, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        if self.is_file() or (self.is_dir() and not exist_ok):
            raise FileExistsError(str(self))
        if not parents and self._parts[:-1] not in self._volume.children:
            raise FileNotFoundError(str(self))
        self._volume.add_dir(self._parts)

    def unlink(self, missing_ok: bool = False) -> None:
        if self._parts in self._volume.files:
            self._volume.remove_file(self._parts)
        elif not missing_ok:
            raise FileNotFoundError(str(self))

    def rmdir(self) -> None:
        if not self.is_dir():
            raise FileNotFoundError(str(self))
        if self._volume.children[self._parts]:
            raise OSError(f"directory not empty: {self}")
        self._volume.remove_dir(self._parts)

    def _remove(self) -> None:
        if self.is_file():
            self._volume.remove_file(self._parts)
        elif self.is_dir():
            self._volume.remove_dir(self._parts)


@contextmanager
def memory_dir(label: str = "work") -> Iterator[MemPath]:
    """A new, empty directory in memory, gone with the block: what
    ``tempfile.TemporaryDirectory`` was used for, without the disk."""
    volume = _Volume(label)
    try:
        yield MemPath(volume)
    finally:
        volume.files.clear()
        volume.children.clear()
        volume.times.clear()


def is_memory(path: Any) -> bool:
    return isinstance(path, MemPath)


def copy_file(source: Any, target: Any) -> None:
    """Copy one file, between the disk and memory in any direction."""
    if not is_memory(source) and not is_memory(target):
        shutil.copy2(source, target)
    else:
        target.write_bytes(source.read_bytes())


def copy_tree(source: Any, target: Any) -> None:
    """Copy the directory ``source`` as the new directory ``target``, whichever kind each is."""
    if not is_memory(source) and not is_memory(target):
        shutil.copytree(source, target)
        return
    if target.exists():
        raise FileExistsError(str(target))
    target.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        copy = target.joinpath(*path.relative_to(source).parts)
        if path.is_dir():
            copy.mkdir(parents=True, exist_ok=True)
        else:
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(path.read_bytes())


def remove_tree(path: Any, ignore_errors: bool = False) -> None:
    """Remove a directory and everything in it, on the disk or in memory."""
    if not is_memory(path):
        shutil.rmtree(path, ignore_errors=ignore_errors)
    elif path.is_dir():
        path._remove()
    elif not ignore_errors:
        raise FileNotFoundError(str(path))


def move(source: Any, target: Any) -> None:
    """Move a file or a directory to ``target`` (which is not there), on the disk or in memory."""
    if not is_memory(source) and not is_memory(target):
        shutil.move(source, target)
        return
    if source.is_dir():
        copy_tree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    if is_memory(source):
        source._remove()
    elif source.is_dir():
        shutil.rmtree(source)
    else:
        source.unlink()
