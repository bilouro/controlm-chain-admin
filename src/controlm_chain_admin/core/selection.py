"""Some of a branch's commits applied on its base, cherry-pick style, without touching git.

A selection is computed file by file. A selected commit's change to a file is taken as it is
when the file is still as the commit found it, merged three ways (``git merge-file``) when a
left-out commit changed other lines of the file, and refused when the changes overlap or the
file is missing (the commit needs one that was left out). The result is an overlay of the base
snapshot: nothing is written to the repository, its index or its object store.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from controlm_chain_admin.core.environments import held_env
from controlm_chain_admin.core.errors import ChainError, GitError, SelectionConflict
from controlm_chain_admin.core.history import (
    CommitInfo,
    FileChange,
    RefInfo,
    commits_between,
    file_changes,
    full_sha,
    merge_base,
    merge_text,
    read_blobs,
    resolve,
    snapshot,
    tree_blobs,
)
from controlm_chain_admin.core.repo import load_repo

if TYPE_CHECKING:
    from controlm_chain_admin.core.crossenv import Translation


@dataclass(frozen=True)
class Sides:
    """The two directories being compared and how they were obtained."""

    base: RefInfo
    head: RefInfo
    merge_base: str | None  # sha compared on the base side when it differs from base
    compared: str  # sha (or WORKTREE) actually compared on the base side
    commits: tuple[CommitInfo, ...]  # every commit compared..head, newest first
    selected: tuple[str, ...] | None  # the commits applied, newest first; None: all of them
    changes: Mapping[str, tuple[FileChange, ...]]  # files each non-merge commit changed
    base_root: Path
    head_root: Path
    #: across two environments: what was rewritten on the head side, in the base's terms
    translation: Translation | None = None
    #: (the base's environment, the head's) when the two sides are two environments
    environments: tuple[str, str] | None = None

    @property
    def applied(self) -> tuple[str, ...]:
        """Commits whose changes are on the head side, newest first."""
        if self.selected is not None:
            return self.selected
        return tuple(c.sha for c in self.commits if not c.merge)


def select(
    root: Path, commits: Sequence[CommitInfo], wanted: Sequence[str] | None
) -> tuple[str, ...] | None:
    """Full shas of the wanted commits, newest first; None when that is every commit."""
    if wanted is None:
        return None
    by_sha = {c.sha: c for c in commits}
    picked: set[str] = set()
    for rev in wanted:
        sha = full_sha(root, rev)
        if sha not in by_sha:
            raise GitError(f"{rev} is not one of the commits being compared")
        if by_sha[sha].merge:
            raise GitError(f"{rev} is a merge commit; merge commits cannot be selected")
        picked.add(sha)
    plain = [c.sha for c in commits if not c.merge]
    if set(plain) <= picked:
        return None
    return tuple(sha for sha in plain if sha in picked)


def _short(sha: str) -> str:
    return sha[:7]


def overlay(
    root: Path,
    base: str,
    commits: Sequence[CommitInfo],
    picked: Sequence[str],
    changes: Mapping[str, tuple[FileChange, ...]],
) -> dict[str, bytes | None]:
    """Files that differ from ``base`` once the picked commits are applied, oldest first."""
    base_blobs = tree_blobs(root, base)
    state: dict[str, str | bytes] = dict(base_blobs)  # blob id, or the bytes of a merge
    order = [c.sha for c in reversed(commits) if not c.merge]
    subjects = {c.sha: c.subject for c in commits}
    chosen = set(picked)
    touched: list[str] = []

    def content(value: str | bytes) -> bytes:
        return value if isinstance(value, bytes) else read_blobs(root, [value])[value]

    for position, sha in enumerate(order):
        if sha not in chosen:
            continue
        conflicts: list[str] = []
        for change in changes.get(sha, ()):
            current = state.get(change.path)
            if current == change.before:
                new: str | bytes | None = change.after
            elif current == change.after:
                continue  # already there
            elif current is None or change.before is None or change.after is None:
                conflicts.append(change.path)
                continue
            else:
                new = merge_text(content(current), content(change.before), content(change.after))
                if new is None:
                    conflicts.append(change.path)
                    continue
            if new is None:
                state.pop(change.path, None)
            else:
                state[change.path] = new
            touched.append(change.path)
        if conflicts:
            missing = tuple(
                other
                for other in reversed(order[:position])
                if other not in chosen and any(c.path in conflicts for c in changes.get(other, ()))
            )
            needs = ", ".join(_short(m) for m in missing) or "commits outside the selection"
            raise SelectionConflict(
                f"commit {_short(sha)} ({subjects[sha]}) does not apply without {needs}: "
                + ", ".join(conflicts),
                sha,
                tuple(conflicts),
                missing,
            )

    result: dict[str, bytes | None] = {}
    blobs: dict[str, str] = {}
    for path in dict.fromkeys(touched):
        final = state.get(path)
        if final == base_blobs.get(path):
            continue
        if final is None:
            result[path] = None
        elif isinstance(final, bytes):
            result[path] = final
        else:
            blobs[path] = final
    contents = read_blobs(root, blobs.values())
    result.update({path: contents[blob] for path, blob in blobs.items()})
    return result


def environments_of(root: Path, base: str, head: str) -> tuple[str, str] | None:
    """(the base's environment, the head's) when the two refs hold different environments:
    the branches of two environments, or a branch of one's own that holds one of them."""
    try:
        config = load_repo(root).config
    except ChainError:
        return None
    target, source = held_env(root, config, base), held_env(root, config, head)
    if target is None or source is None or target == source:
        return None
    return target, source


@contextmanager
def _across(
    root: Path,
    base: RefInfo,
    head: RefInfo,
    target: str,
    source: str,
    translate: bool,
    prefer: Sequence[str] = (),
) -> Iterator[Sides]:
    """Two environments' branches side by side: they share no history to compare along, so each
    is taken whole, and the head side is rewritten in the base's terms unless asked not to."""
    from controlm_chain_admin.core.crossenv import translated  # it imports this module

    compared = base.sha or base.name
    with snapshot(root, base.name) as base_root, snapshot(root, head.name) as head_root:
        if not translate:
            yield Sides(
                base, head, None, compared, (), None, {}, base_root, head_root, None,
                (target, source),
            )  # fmt: skip
            return
        with translated(root, base_root, head_root, source, target, prefer) as (
            copy,
            translation,
        ):
            yield Sides(
                base, head, None, compared, (), None, {}, base_root, copy, translation,
                (target, source),
            )  # fmt: skip


@contextmanager
def open_sides(
    root: Path,
    base: str,
    head: str,
    *,
    use_merge_base: bool = True,
    commits: Sequence[str] | None = None,
    translate: bool = True,
    prefer: Sequence[str] = (),
) -> Iterator[Sides]:
    """Snapshots of the base side and of the head side (only ``commits`` when given).

    When the two refs hold different environments, the head side is what its environment has,
    in the terms of the base's (``translate=False``: as it is; ``prefer``: the entries of the
    map that win where it gives several answers); commits cannot be selected.
    """
    base_info, head_info = resolve(root, base), resolve(root, head)
    across = environments_of(root, base, head)
    if across is not None:
        if commits is not None:
            raise GitError(
                f"{base} and {head} hold different environments ({across[0]} and {across[1]}): "
                "they are compared whole, commits cannot be selected"
            )
        with _across(root, base_info, head_info, *across, translate, prefer) as sides:
            yield sides
        return
    if commits is not None and head_info.sha is None:
        raise GitError("the working tree has no commits to select; compare a branch instead")
    head_commit = head_info.sha or resolve(root, "HEAD").sha or "HEAD"
    merge: str | None = None
    if use_merge_base and base_info.sha:
        candidate = merge_base(root, base_info.sha, head_commit)
        if candidate != base_info.sha:
            merge = candidate
    compared = merge or base_info.sha or base  # base may be WORKTREE
    history = commits_between(root, compared, head_commit) if base_info.sha else ()
    changes = {c.sha: file_changes(root, c.sha) for c in history if not c.merge}
    selected = select(root, history, commits)
    if selected is None:
        with snapshot(root, compared) as base_root, snapshot(root, head) as head_root:
            yield Sides(
                base_info, head_info, merge, compared, history, None, changes,
                base_root, head_root,
            )  # fmt: skip
        return
    files = overlay(root, compared, history, selected, changes)
    with snapshot(root, compared) as base_root, snapshot(root, compared, files) as head_root:
        yield Sides(
            base_info, head_info, merge, compared, history, selected, changes,
            base_root, head_root,
        )  # fmt: skip
