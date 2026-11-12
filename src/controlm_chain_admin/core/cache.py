"""Results kept by commit: a comparison of two commits is the same whenever it is asked for.

Working one out takes both branches out of git and reads them whole; the answer depends only on
the two commits, the map, the rules and the options. So it is kept under the git directory
(``ctmchain-cache``, which no ``git status`` shows) with all of those in its key, and the same
question again is answered from there. The working tree is never kept: it has no commit.

``CTMCHAIN_NO_CACHE=1`` turns it off; :func:`fresh` works a result out anew and keeps it.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from pathlib import Path
from typing import Any, TypeVar

from controlm_chain_admin import __version__
from controlm_chain_admin.core.environments import current_branch, env_branches
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.history import WORKTREE, _git, resolve
from controlm_chain_admin.core.repo import CHAIN_FILE, load_repo
from controlm_chain_admin.core.timing import count

#: results kept at most: the oldest go
KEEP = 60
DIRECTORY = "ctmchain-cache"
OFF = "CTMCHAIN_NO_CACHE"

_Result = TypeVar("_Result")
_FRESH: ContextVar[bool] = ContextVar("ctmchain_cache_fresh", default=False)


def directory(root: Path) -> Path:
    """Where the results of the repository at ``root`` are kept: inside its git directory."""
    return Path(str(_git(root, "rev-parse", "--absolute-git-dir")).strip()) / DIRECTORY


@contextmanager
def fresh() -> Iterator[None]:
    """Inside the block nothing is answered from what is kept; what is worked out is kept."""
    token = _FRESH.set(True)
    try:
        yield
    finally:
        _FRESH.reset(token)


def state(root: Path, refs: Sequence[str]) -> list[Any] | None:
    """Everything a result about ``refs`` depends on besides its options: the commit of each
    ref, the branch checked out (``HEAD`` is read as it), the environments' branches, the map
    and the rules of the working tree. None when it cannot be kept (the working tree is one of
    the refs, a ref does not exist, no git)."""
    if WORKTREE in refs or os.environ.get(OFF):
        return None
    try:
        commits = [[ref, resolve(root, ref).sha] for ref in refs]
        config = load_repo(root).config
        branches = env_branches(root, config)
        heads = str(_git(root, "for-each-ref", "--format=%(refname:short) %(objectname)",
                         "refs/heads"))  # fmt: skip
        tips = dict(line.split(" ", 1) for line in heads.splitlines() if " " in line)
        rules = hashlib.sha256((root / CHAIN_FILE).read_bytes()).hexdigest()
    except (ChainError, OSError):
        return None
    if any(sha is None for _, sha in commits):
        return None
    return [
        commits,
        current_branch(root),
        {env: tips.get(branch) is not None for env, branch in branches.items()},
        tips.get(config.git_rules.map_branch),
        rules,
    ]


def _load(path: Path) -> tuple[bool, Any]:
    try:
        with path.open("rb") as handle:
            return True, pickle.load(handle)  # our own file, in the git directory
    except Exception:  # missing, cut short, written by another version of a class
        return False, None


def _store(path: Path, value: Any) -> None:
    """Write the result, whole or not at all; a result that cannot be kept is not an error."""
    with suppress(OSError, pickle.PicklingError, TypeError, AttributeError):
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix="writing-", dir=path.parent)
        with os.fdopen(handle, "wb") as out:
            pickle.dump(value, out, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(name, path)
        kept = sorted(path.parent.glob("*.pickle"), key=lambda p: p.stat().st_mtime)
        for old in kept[: max(len(kept) - KEEP, 0)]:
            old.unlink(missing_ok=True)


def remember(
    root: Path, kind: str, parts: Sequence[Any] | None, compute: Callable[[], _Result]
) -> _Result:
    """``compute()``, or what it gave the last time for the same ``parts`` (None: not kept)."""
    if parts is None:
        return compute()
    text = json.dumps([__version__, kind, list(parts)], sort_keys=True, default=str)
    key = hashlib.sha256(text.encode()).hexdigest()[:40]
    try:
        path = directory(root) / f"{kind}-{key}.pickle"
    except ChainError:
        return compute()
    if not _FRESH.get():
        found, value = _load(path)
        if found:
            count("cache_hits")
            with suppress(OSError):
                os.utime(path)  # asked for again: among the latest
            return value  # type: ignore[no-any-return]
    result = compute()
    _store(path, result)
    return result
