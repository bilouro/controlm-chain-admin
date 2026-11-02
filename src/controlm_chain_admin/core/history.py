"""The chain repository at any git ref: refs, merge bases, commits and read-only snapshots.

A snapshot is a temporary directory holding the repository's files (``chain.json``, ``folders/``,
``meta/``, ``envs/``) as committed at a ref, extracted with ``git archive``; the working tree is
never touched. :data:`WORKTREE` names the working tree itself (uncommitted changes included).
Needs the ``git`` program; nothing else.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from controlm_chain_admin.core.errors import GitError

WORKTREE = "WORKTREE"
_SNAPSHOT_PREFIXES = ("chain.json", "folders/", "meta/", "envs/")
_SEP = "\x1f"


@dataclass(frozen=True)
class RefInfo:
    name: str
    kind: str  # branch | remote | tag | commit | worktree
    sha: str | None  # None for the working tree
    subject: str | None = None
    date: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "sha": self.sha,
            "subject": self.subject,
            "date": self.date,
        }


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    subject: str
    author: str
    date: str
    merge: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "subject": self.subject,
            "author": self.author,
            "date": self.date,
            "merge": self.merge,
        }


@dataclass(frozen=True)
class FileChange:
    """One chain file changed by a commit: blob ids before and after (None: absent)."""

    path: str  # relative to the chain repository root, POSIX
    before: str | None
    after: str | None


@dataclass(frozen=True)
class GitState:
    current: str | None  # checked-out branch, None when detached
    head: str
    dirty: bool
    refs: tuple[RefInfo, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "head": self.head,
            "dirty": self.dirty,
            "refs": [r.to_json() for r in self.refs],
        }


def _git(root: Path, *args: str, binary: bool = False) -> Any:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, check=False, text=not binary
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    if result.returncode != 0:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode()
        raise GitError(f"git {' '.join(args[:2])}: {stderr.strip() or 'failed'}")
    return result.stdout


def git_state(root: Path) -> GitState:
    """Current branch, HEAD, dirtiness of the chain files, and every branch, remote and tag."""
    head = _git(root, "rev-parse", "HEAD").strip()
    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    status = _git(root, "status", "--porcelain", "--", ".").strip()
    fmt = _SEP.join(
        ("%(refname)", "%(objectname)", "%(contents:subject)", "%(committerdate:iso-strict)")
    )
    listing = _git(
        root,
        "for-each-ref",
        "--sort=-committerdate",
        f"--format={fmt}",
        "refs/heads",
        "refs/remotes",
        "refs/tags",
    )
    refs: list[RefInfo] = []
    for line in listing.splitlines():
        refname, sha, subject, date = [*line.split(_SEP), "", "", ""][:4]
        for prefix, kind in (
            ("refs/heads/", "branch"),
            ("refs/remotes/", "remote"),
            ("refs/tags/", "tag"),
        ):
            if refname.startswith(prefix):
                name = refname[len(prefix) :]
                if kind == "remote" and name.endswith("/HEAD"):
                    break
                refs.append(RefInfo(name, kind, sha, subject, date))
                break
    return GitState(None if current == "HEAD" else current, head, bool(status), tuple(refs))


def resolve(root: Path, ref: str) -> RefInfo:
    """A ref (branch, tag, sha, ``WORKTREE``) with its commit sha, subject and date."""
    if ref == WORKTREE:
        return RefInfo(WORKTREE, "worktree", None, "uncommitted changes")
    try:
        line = _git(
            root, "log", "-1", f"--format=%H{_SEP}%s{_SEP}%cI", f"{ref}^{{commit}}", "--"
        ).strip()
    except GitError as exc:
        raise GitError(f"unknown git ref {ref!r}") from exc
    sha, subject, date = line.split(_SEP)
    kind = "commit"
    for prefix, name in (
        ("refs/heads/", "branch"),
        ("refs/tags/", "tag"),
        ("refs/remotes/", "remote"),
    ):
        try:
            _git(root, "show-ref", "--verify", "--quiet", f"{prefix}{ref}")
            kind = name
            break
        except GitError:
            continue
    return RefInfo(ref, kind, sha, subject, date)


def merge_base(root: Path, a: str, b: str) -> str:
    return str(_git(root, "merge-base", a, b).strip())


def commits_between(root: Path, base: str, head: str) -> tuple[CommitInfo, ...]:
    """Commits reachable from ``head`` and not from ``base``, newest first."""
    out = _git(
        root, "log", f"--format=%H{_SEP}%s{_SEP}%an{_SEP}%cI{_SEP}%P", f"{base}..{head}", "--"
    )
    commits = []
    for line in out.splitlines():
        sha, subject, author, date, parents = line.split(_SEP)
        commits.append(CommitInfo(sha, subject, author, date, len(parents.split()) > 1))
    return tuple(commits)


def full_sha(root: Path, rev: str) -> str:
    """The full sha of a commit given by any revision (short sha, branch...)."""
    try:
        return str(_git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").strip())
    except GitError as exc:
        raise GitError(f"unknown commit {rev!r}") from exc


def _tree(root: Path, rev: str) -> tuple[Path, str]:
    """(top level, tree-ish of the chain directory at ``rev``) for commands run from the top."""
    prefix = _prefix(root)
    top = Path(str(_git(root, "rev-parse", "--show-toplevel")).strip())
    return top, f"{rev}:{prefix}" if prefix else f"{rev}^{{tree}}"


def _chain_file(path: str) -> bool:
    return path.startswith(_SNAPSHOT_PREFIXES)


def _blob(sha: str) -> str | None:
    return None if set(sha) == {"0"} else sha


def file_changes(root: Path, commit: str) -> tuple[FileChange, ...]:
    """Chain files a commit changed against its first parent (renames as delete + add)."""
    top, before = _tree(root, f"{commit}^1")
    _, after = _tree(root, commit)
    out = str(_git(top, "diff-tree", "-r", "-z", "--no-renames", before, after))
    fields = out.split("\0")
    changes = []
    for meta, path in zip(fields[0::2], fields[1::2], strict=False):
        parts = meta.split()
        if len(parts) < 5 or not _chain_file(path):
            continue
        changes.append(FileChange(path, _blob(parts[2]), _blob(parts[3])))
    return tuple(changes)


def tree_blobs(root: Path, rev: str) -> dict[str, str]:
    """Chain file path -> blob id at ``rev``."""
    top, tree = _tree(root, rev)
    out = str(_git(top, "ls-tree", "-r", "-z", tree))
    blobs = {}
    for entry in filter(None, out.split("\0")):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob" and _chain_file(path):
            blobs[path] = parts[2]
    return blobs


def read_blobs(root: Path, shas: Iterable[str]) -> dict[str, bytes]:
    """Contents of blobs by id, read in one ``git cat-file --batch``."""
    wanted = list(dict.fromkeys(shas))
    if not wanted:
        return {}
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input="\n".join(wanted).encode() + b"\n",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(f"git cat-file: {result.stderr.decode().strip() or 'failed'}")
    out, at, blobs = result.stdout, 0, {}
    for sha in wanted:
        end = out.index(b"\n", at)
        header = out[at:end].split()
        if len(header) != 3:
            raise GitError(f"git cat-file: missing object {sha}")
        size = int(header[2])
        blobs[sha] = out[end + 1 : end + 1 + size]
        at = end + 1 + size + 1
    return blobs


def merge_text(current: bytes, base: bytes, other: bytes) -> bytes | None:
    """Three-way merge of one file (``git merge-file``); None when the changes overlap."""
    with tempfile.TemporaryDirectory(prefix="ctmchain-merge-") as tmp:
        paths = []
        for name, data in (("current", current), ("base", base), ("other", other)):
            path = Path(tmp) / name
            path.write_bytes(data)
            paths.append(str(path))
        try:
            result = subprocess.run(
                ["git", "merge-file", "-p", *paths], capture_output=True, check=False
            )
        except FileNotFoundError as exc:
            raise GitError("git is not installed or not on PATH") from exc
    if result.returncode < 0 or result.returncode > 127:
        raise GitError(f"git merge-file: {result.stderr.decode().strip() or 'failed'}")
    return result.stdout if result.returncode == 0 else None


def _prefix(root: Path) -> str:
    """Path of ``root`` inside its git repository (``""`` at the top), POSIX, ending with /."""
    return str(_git(root, "rev-parse", "--show-prefix").strip())


@contextmanager
def snapshot(
    root: Path, ref: str, overlay: Mapping[str, bytes | None] | None = None
) -> Iterator[Path]:
    """A directory with the repository's files at ``ref`` (the repository itself for WORKTREE).

    ``overlay`` replaces files of the snapshot (path -> content, None deletes the file).
    """
    if ref == WORKTREE:
        if overlay:
            raise GitError("the working tree cannot be overlaid")
        yield root
        return
    info = resolve(root, ref)
    prefix = _prefix(root)
    tree = f"{info.sha}:{prefix}" if prefix else str(info.sha)
    # run from the top level: inside a subdirectory git archive keeps only that subdirectory
    top = Path(str(_git(root, "rev-parse", "--show-toplevel")).strip())
    archive: bytes = _git(top, "archive", "--format=tar", tree, binary=True)
    with tempfile.TemporaryDirectory(prefix="ctmchain-ref-") as tmp:
        target = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                name = PurePosixPath(member.name)
                if not member.isfile() or name.is_absolute() or ".." in name.parts:
                    continue
                if not str(name).startswith(_SNAPSHOT_PREFIXES):
                    continue
                source = tar.extractfile(member)
                if source is None:
                    continue
                path = target.joinpath(*name.parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source.read())
        for relative, content in (overlay or {}).items():
            path = target.joinpath(*PurePosixPath(relative).parts)
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        yield target
