"""One branch per environment: the trunk holds production, ``env/<name>`` every other one.

A branch is what its environment has, as its full export says it (``refresh``). Comparing two
of them, or taking from one to another, goes through the map of what varies per environment
(:mod:`controlm_chain_admin.core.envmap`).
"""

from __future__ import annotations

import re
from pathlib import Path

from controlm_chain_admin.core.errors import GitError, UnknownEnvironment
from controlm_chain_admin.core.history import WORKTREE, _git
from controlm_chain_admin.core.repo import ChainConfig

#: the subject of the commit that holds an export (:func:`export_subject`)
#: the subject of a commit that holds an export (:func:`export_subject`)
EXPORT_SUBJECT = re.compile(r"^(refresh|import)\(([^)]+)\): ")


def branch_of_env(config: ChainConfig, env: str) -> str:
    """The branch that holds ``env``: the trunk for production, ``<env_prefix><env>`` else."""
    if env not in config.environments:
        known = ", ".join(config.environments) or "none"
        raise UnknownEnvironment(f"unknown environment {env!r} (known: {known})")
    rules = config.git_rules
    return rules.trunk if env == rules.production else rules.env_prefix + env


def current_branch(root: Path) -> str | None:
    """The branch checked out in ``root``; None when detached or not a git repository."""
    try:
        return str(_git(root, "symbolic-ref", "-q", "--short", "HEAD")).strip() or None
    except GitError:
        return None  # detached, or not a git repository


def env_of_ref(root: Path, config: ChainConfig, ref: str) -> str | None:
    """The environment ``ref`` holds: the trunk's is production, ``env/<name>`` is ``name``,
    the working tree and ``HEAD`` are the checked-out branch's. None for any other ref."""
    rules = config.git_rules
    if ref in (WORKTREE, "HEAD"):
        current = current_branch(root)
        return None if current is None else env_of_ref(root, config, current)
    if ref == rules.trunk:
        return rules.production if rules.production in config.environments else None
    if ref.startswith(rules.env_prefix):
        name = ref[len(rules.env_prefix) :]
        return name if name in config.environments and name != rules.production else None
    return None


def branch_exists(root: Path, branch: str) -> bool:
    try:
        _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}")
    except GitError:
        return False
    return True


def export_subject(env: str, source: str, *, work: bool = False) -> str:
    """The subject of the commit that holds an export of ``env``: a ``refresh`` of the
    environment's branch, an ``import`` onto a branch of one's own. :func:`held_env` reads it
    back, so the two stay together."""
    return f"{'import' if work else 'refresh'}({env}): {source}"


def held_env(root: Path, config: ChainConfig, ref: str) -> str | None:
    """The environment whose chains ``ref`` holds.

    The branch of an environment says it by its name (:func:`env_of_ref`). Any other ref holds
    the environment of the last export put in its history: the nearest commit of its own line
    (first parents) written by a refresh, whose subject names the environment. So a branch of
    one's own holds what the branch it started from holds, until the export of another
    environment goes onto it. None when its history has no such commit, or when that
    environment has no branch (a repository that keeps every environment in one tree).
    """
    named = env_of_ref(root, config, ref)
    if named is not None:
        return named
    rev = "HEAD" if ref == WORKTREE else ref
    try:
        subjects = str(
            _git(
                root, "log", "--first-parent", "-E", f"--grep={EXPORT_SUBJECT.pattern}",
                "--format=%s", f"{rev}^{{commit}}", "--",
            )
        )  # fmt: skip
    except GitError:  # no such ref, no commit yet, not a git repository
        return None
    for subject in subjects.splitlines():  # --grep also matches a line of the body
        found = EXPORT_SUBJECT.match(subject)
        if found and found[2] in config.environments:
            # where no branch holds the environment the subject is somebody's own wording
            env = str(found[2])
            return env if branch_exists(root, branch_of_env(config, env)) else None
    return None


def env_branches(root: Path, config: ChainConfig) -> dict[str, str]:
    """Environment -> its branch, for the branches that exist, in the order of chain.json."""
    found = {env: branch_of_env(config, env) for env in config.environments}
    return {env: branch for env, branch in found.items() if branch_exists(root, branch)}
