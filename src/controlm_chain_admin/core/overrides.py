"""Exceptions: whole values one environment uses for one job or folder.

``envs/<env>/overrides.json`` maps a node (``FOLDER/JOB``, or ``FOLDER/`` for the folder itself)
to the attributes it sets (``null`` removes one) and the variables it sets::

    {"P77_CHAIN/P77_E": {"set": {"TASKTYPE": "Dummy"}, "variables": {"%%TIME_END": "0100"}}}

Export resolves, per value: exception, then constant, then the base value. An exception value
may itself be a ``@{constant}``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.repo import ChainRepo, read_json, write_json

OVERRIDES_FILE = "overrides.json"
VARIABLE_TAG = "VARIABLE"


@dataclass(frozen=True)
class Override:
    attributes: dict[str, str | None] = field(default_factory=dict)  # None removes it
    variables: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.attributes:
            data["set"] = dict(sorted(self.attributes.items()))
        if self.variables:
            data["variables"] = dict(sorted(self.variables.items()))
        return data

    @property
    def empty(self) -> bool:
        return not self.attributes and not self.variables


def overrides_path(repo: ChainRepo, env: str) -> Any:
    return repo.env_file(env).with_name(OVERRIDES_FILE)


def _parse(env: str, node: str, entry: Any) -> Override:
    where = f"envs/{env}/{OVERRIDES_FILE}: {node}"
    if not isinstance(entry, dict) or set(entry) - {"set", "variables"}:
        raise ModelError(f"{where}: expected an object with 'set' and/or 'variables'")
    attributes = entry.get("set", {})
    variables = entry.get("variables", {})
    if not isinstance(attributes, dict) or not all(
        isinstance(v, str) or v is None for v in attributes.values()
    ):
        raise ModelError(f"{where}: 'set' maps attributes to strings or null")
    if not isinstance(variables, dict) or not all(isinstance(v, str) for v in variables.values()):
        raise ModelError(f"{where}: 'variables' maps variable names to strings")
    return Override(dict(attributes), dict(variables))


def load_overrides(repo: ChainRepo, env: str) -> dict[str, Override]:
    """The exceptions of ``env`` by node; empty when the file does not exist."""
    path = overrides_path(repo, env)
    if not path.is_file():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise ModelError(f"envs/{env}/{OVERRIDES_FILE}: expected an object of nodes")
    return {str(node): _parse(env, str(node), entry) for node, entry in data.items()}


def write_overrides(repo: ChainRepo, env: str, overrides: Mapping[str, Override]) -> None:
    """Write the exceptions of ``env`` (sorted by node); no file when there is none."""
    kept = {node: o.to_json() for node, o in sorted(overrides.items()) if not o.empty}
    path = overrides_path(repo, env)
    if kept:
        write_json(path, kept)
    elif path.exists():
        path.unlink()


def apply_override(data: Mapping[str, Any], override: Override | None) -> dict[str, Any]:
    """A job or folder JSON with the exception applied (attributes, then variables)."""
    out = dict(data)
    if override is None:
        return out
    for attribute, value in override.attributes.items():
        if value is None:
            out.pop(attribute, None)
        else:
            out[attribute] = value
    if override.variables:
        variables = [dict(v) for v in out.get(VARIABLE_TAG, [])]
        for name, value in override.variables.items():
            for variable in variables:
                if variable.get("NAME") == name:
                    variable["VALUE"] = value
                    break
            else:
                variables.append({"NAME": name, "VALUE": value})
        out[VARIABLE_TAG] = variables
    return out
