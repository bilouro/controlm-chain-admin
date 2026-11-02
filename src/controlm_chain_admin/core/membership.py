"""Folders and jobs that exist in some environments only.

A ``folder.json`` or a job file may carry ``"envs": ["uat"]``: the node exists in those
environments only; without the key it exists in every environment. The export of another
environment leaves it out; importing an export that has it adds that environment.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

ENVS_KEY = "envs"


def environments_of(data: Mapping[str, Any]) -> tuple[str, ...] | None:
    """The environments of a node, or ``None`` for every environment."""
    envs = data.get(ENVS_KEY)
    return tuple(str(e) for e in envs) if isinstance(envs, list) else None


def belongs(data: Mapping[str, Any], env: str | None) -> bool:
    """Whether the node exists in ``env`` (every node exists in the neutral repository)."""
    envs = environments_of(data)
    return env is None or envs is None or env in envs


def with_envs(
    data: Mapping[str, Any], envs: Iterable[str], every: Sequence[str]
) -> dict[str, Any]:
    """``data`` existing in ``envs`` (in the repository's order); every environment: no key."""
    chosen = set(envs)
    result = {k: v for k, v in data.items() if k != ENVS_KEY}
    if not set(every) <= chosen:
        result[ENVS_KEY] = [e for e in every if e in chosen]
    return result
