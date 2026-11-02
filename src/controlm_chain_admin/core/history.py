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
from collections.abc import Iterator
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

    def to_json(self) -> dict[str, Any]:
        return {"sha": self.sha, "subject": self.subject, "author": self.author, "date": self.date}


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
    out = _git(root, "log", f"--format=%H{_SEP}%s{_SEP}%an{_SEP}%cI", f"{base}..{head}", "--")
    commits = []
    for line in out.splitlines():
        sha, subject, author, date = line.split(_SEP)
        commits.append(CommitInfo(sha, subject, author, date))
    return tuple(commits)


def _prefix(root: Path) -> str:
    """Path of ``root`` inside its git repository (``""`` at the top), POSIX, ending with /."""
    return str(_git(root, "rev-parse", "--show-prefix").strip())


@contextmanager
def snapshot(root: Path, ref: str) -> Iterator[Path]:
    """A directory with the repository's files at ``ref`` (the repository itself for WORKTREE)."""
    if ref == WORKTREE:
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
        yield target
