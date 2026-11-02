"""Commit the edits of a chain repository: what is pending, a suggested message, the commit.

Only the chain files (``chain.json``, ``folders/``, ``meta/``, ``envs/``) are committed, with
``git commit --only``: other files of the working tree and anything else staged stay as they
are. The suggested message is written from the semantic comparison of HEAD with the working
tree, so it describes every edit, whether it came from the web UI, the CLI or a text editor.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.compare import Comparison, _node_lines, compare
from controlm_chain_admin.core.errors import ChangeConflict, GitError, NothingToCommit
from controlm_chain_admin.core.history import WORKTREE, _git, git_state
from controlm_chain_admin.core.links import INDEX_FILE

#: Branches the UI suggests not to commit on directly.
PROTECTED = ("main", "master", "develop")
_PATHS = ("chain.json", "folders", "meta", "envs")
_BODY_LINES = 40


@dataclass(frozen=True)
class Pending:
    branch: str | None
    head: str
    files: tuple[str, ...]  # changed chain files, derived index.json left out
    summary: dict[str, Any]
    message: str  # suggested; "" when nothing is pending
    fingerprint: str

    @property
    def protected(self) -> bool:
        return self.branch in PROTECTED

    def to_json(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "head": self.head,
            "files": list(self.files),
            "summary": self.summary,
            "message": self.message,
            "fingerprint": self.fingerprint,
            "protected": self.protected,
        }


@dataclass(frozen=True)
class Committed:
    sha: str
    branch: str | None
    subject: str

    def to_json(self) -> dict[str, Any]:
        return {"sha": self.sha, "branch": self.branch, "subject": self.subject}


def _derived(path: str) -> bool:
    return path.rsplit("/", 1)[-1] == INDEX_FILE


def _changed(root: Path) -> list[str]:
    """Chain files that differ from HEAD (modified, deleted or new), relative to ``root``."""
    tracked = str(_git(root, "diff", "HEAD", "--name-only", "--no-renames", "-z", "--relative",
                       "--", *_PATHS))  # fmt: skip
    new = str(_git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", *_PATHS))
    return sorted({p for p in (*tracked.split("\0"), *new.split("\0")) if p})


def _fingerprint(root: Path, head: str, files: list[str]) -> str:
    digest = hashlib.sha256(head.encode())
    for path in files:
        if _derived(path):
            continue  # rewritten by validate: not part of what the author reviewed
        target = root / path
        digest.update(path.encode() + b"\0")
        digest.update(target.read_bytes() if target.is_file() else b"<deleted>")
    return digest.hexdigest()


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _subject(result: Comparison) -> str:
    s = result.summary()
    jobs, folders, links = s["jobs"], s["folders"], s["links"]
    parts: list[str] = []
    for verb, key in (("add", "added"), ("remove", "removed"), ("rename", "renamed")):
        if folders[key]:
            parts.append(f"{verb} {_plural(folders[key], 'folder')}")
        if jobs[key]:
            parts.append(f"{verb} {_plural(jobs[key], 'job')}")
    if links["renamed"]:
        parts.append(f"rename {_plural(links['renamed'], 'condition')}")
    if jobs["moved"]:
        parts.append(f"move {_plural(jobs['moved'], 'job')}")
    modified = [j for j in result.jobs if j.change == "modified"]
    if len(modified) == 1 and not parts:
        folder, _, job = modified[0].node.partition("/")
        parts.append(f"update job {job} in {folder}")
    elif modified:
        parts.append(f"update {_plural(len(modified), 'job')}")
    if folders["modified"]:
        parts.append(f"update {_plural(folders['modified'], 'folder')}")
    if s["constants"]:
        parts.append(f"change {_plural(s['constants'], 'constant value')}")
    if not parts:
        parts.append("update export metadata" if result.metadata_files_changed else "update")
    text = ", ".join(parts[:3]) + (", and more" if len(parts) > 3 else "")
    if jobs["added"] or folders["added"]:
        kind = "feat"
    elif not (modified or folders["modified"] or jobs["removed"] or folders["removed"]) and not (
        s["constants"] or result.rules_changed
    ):
        kind = "refactor" if parts[0] != "update export metadata" else "chore"
    else:
        kind = "fix"
    return f"{kind}: {text}"


def suggest_message(result: Comparison) -> str:
    """A Conventional Commits message: a subject that sums up, a body that lists the changes."""
    lines: list[str] = []
    for node in (*result.folders, *result.jobs):
        title = f"- {node.change} {node.kind} {node.node}"
        if node.previous:
            title += f" (was {node.previous})"
        lines.append(title)
        lines += [f"  {detail.strip()}" for detail in _node_lines(node)[1:]]
    for link in result.links:
        if link.change == "renamed":
            lines.append(f"- condition renamed {link.before} -> {link.after}")
        else:
            lines.append(f"- condition {link.change} {link.after or link.before}")
    for c in result.constants:
        lines.append(f"- constant {c.env} {c.name}: {c.before} -> {c.after}")
    if len(lines) > _BODY_LINES:
        lines = [*lines[:_BODY_LINES], f"… and {len(lines) - _BODY_LINES} more lines"]
    body = "\n".join(lines)
    return _subject(result) + (f"\n\n{body}" if body else "")


def pending(root: Path) -> Pending:
    """The uncommitted chain changes, with a suggested message and a fingerprint for commit."""
    state = git_state(root)
    files = _changed(root)
    shown = tuple(f for f in files if not _derived(f))
    message, summary = "", {}
    if shown:
        result = compare(root, "HEAD", WORKTREE)
        message, summary = suggest_message(result), result.summary()
    return Pending(
        state.current, state.head, shown, summary, message, _fingerprint(root, state.head, files)
    )


def commit(root: Path, message: str, fingerprint: str, *, branch: str | None = None) -> Committed:
    """Commit the chain files with ``message``, on a new ``branch`` when given.

    Refuses when nothing is pending or when the files changed since :func:`pending`.
    """
    text = message.strip()
    if not text:
        raise GitError("the commit message is empty")
    head = git_state(root).head
    files = _changed(root)
    if not [f for f in files if not _derived(f)]:
        raise NothingToCommit("nothing to commit: the chain files have no change")
    if _fingerprint(root, head, files) != fingerprint:
        raise ChangeConflict("the files changed since the commit was prepared; review it again")
    if branch:
        try:
            _git(root, "check-ref-format", "--branch", branch)
        except GitError as exc:
            raise GitError(f"invalid branch name {branch!r}") from exc
        try:
            _git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
        except GitError:
            pass
        else:
            raise GitError(f"branch {branch} already exists")
        _git(root, "switch", "-q", "-c", branch)
    paths = [p for p in _PATHS if (root / p).exists() or str(_git(root, "ls-files", "--", p))]
    _git(root, "add", "-A", "--", *paths)
    with tempfile.TemporaryDirectory(prefix="ctmchain-commit-") as tmp:
        note = Path(tmp) / "message.txt"
        note.write_text(text + "\n", encoding="utf-8", newline="\n")
        _git(root, "commit", "-q", "--cleanup=whitespace", "-F", str(note), "--only", "--", *paths)
    sha = str(_git(root, "rev-parse", "HEAD")).strip()
    return Committed(sha, git_state(root).current, text.splitlines()[0])
