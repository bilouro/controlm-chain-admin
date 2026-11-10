"""One branch per environment: the trunk holds production, ``env/<name>`` every other one.

A branch is what its environment has, as its full export says it (``refresh``). Comparing two
of them, or taking from one to another, goes through the map of what varies per environment
(:mod:`controlm_chain_admin.core.envmap`).
"""

from __future__ import annotations

from pathlib import Path

from controlm_chain_admin.core.errors import GitError, UnknownEnvironment
from controlm_chain_admin.core.history import WORKTREE, _git
from controlm_chain_admin.core.repo import ChainConfig


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


def env_branches(root: Path, config: ChainConfig) -> dict[str, str]:
    """Environment -> its branch, for the branches that exist, in the order of chain.json."""
    found = {env: branch_of_env(config, env) for env in config.environments}
    return {env: branch for env, branch in found.items() if branch_exists(root, branch)}
