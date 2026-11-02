"""The chain repository on disk: ``chain.json`` rules, folder and job files, metadata sidecars.

Layout::

    chain.json                       rules: application, environments, orders, volatile
                                     attributes, letter rule, constants, git branches and tags
    meta/export.json                 declaration, prolog comments, root element and folder order
    meta/folders/<FOLDER>.json       volatile attributes of the folder and of its jobs
    folders/<FOLDER>/folder.json     folder attributes and folder-level children, plus "jobs"
    folders/<FOLDER>/jobs/<JOB>.json one file per job
    envs/<env>/env.json              per-environment values (letter, display name, constants)
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from controlm_chain_admin.core.errors import (
    ModelError,
    NotAChainRepo,
    RepoExists,
    UnknownEnvironment,
)
from controlm_chain_admin.core.letter import DEFAULT_LETTER_ATTRIBUTES, LetterRule

if TYPE_CHECKING:
    from controlm_chain_admin.core.constants import Selector

CHAIN_FILE = "chain.json"

DEFAULT_VOLATILE_ATTRIBUTES: tuple[str, ...] = (
    "JOBISN",
    "CREATION_USER",
    "CREATION_DATE",
    "CREATION_TIME",
    "CHANGE_USERID",
    "CHANGE_DATE",
    "CHANGE_TIME",
    "VERSION_OPCODE",
    "IS_CURRENT_VERSION",
    "VERSION_SERIAL",
    "VERSION_HOST",
    "DATACENTER",
    "VERSION",
    "MODIFIED",
    "LAST_UPLOAD",
    "FOLDER_ORDER_METHOD",
    "REAL_FOLDER_ID",
    "JOBS_IN_GROUP",
)


@dataclass(frozen=True)
class GitRules:
    """The ``git`` key of ``chain.json``: which branches are read-only, how releases and their
    installations are named. Every key is optional; these are the defaults."""

    trunk: str = "main"  # mirrors production; releases start from it and merge back into it
    protected: tuple[str, ...] = ("main", "master")  # never edited (the trunk always is)
    release_prefix: str = "release/"
    tag_format: str = "{env}/{release}-{n}"  # one tag per installation of a release
    production: str = "prod"  # a release is closed once its last commit is installed here
    remote: str = "origin"

    def refusal(self, branch: str | None) -> str | None:
        """Why edits are refused on ``branch`` (None: a detached HEAD); None when they are not."""
        if branch is None:
            return "HEAD is detached: switch to a release branch to edit"
        if branch == self.trunk:
            return (
                f"{branch} is protected (the trunk mirrors production): edit on a release "
                "branch started from it"
            )
        if branch in self.protected:
            return f"{branch} is protected: edit on a release branch started from {self.trunk}"
        return None

    def to_json(self) -> dict[str, Any]:
        return {
            "trunk": self.trunk,
            "protected": list(self.protected),
            "release_prefix": self.release_prefix,
            "tag_format": self.tag_format,
            "production": self.production,
            "remote": self.remote,
        }

    @classmethod
    def from_json(cls, data: Any) -> GitRules:
        if not isinstance(data, dict):
            raise ModelError("chain.json: git must be an object")
        known = cls().to_json()
        unknown = sorted(set(data) - set(known))
        if unknown:
            raise ModelError(f"chain.json: git has unknown keys: {', '.join(unknown)}")
        values: dict[str, Any] = {}
        for key, value in data.items():
            if key == "protected":
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise ModelError("chain.json: git.protected must be a list of branch names")
                values[key] = tuple(value)
            elif not isinstance(value, str) or not value:
                raise ModelError(f"chain.json: git.{key} must be a non-empty string")
            else:
                values[key] = value
        rules = cls(**values)
        for field_name in ("{env}", "{release}", "{n}"):
            if field_name not in rules.tag_format:
                raise ModelError(f"chain.json: git.tag_format must contain {field_name}")
        return rules


def _tuple_map(data: Any, what: str) -> dict[str, tuple[str, ...]]:
    if not isinstance(data, dict):
        raise ModelError(f"chain.json: {what} must be an object")
    return {str(k): tuple(str(x) for x in v) for k, v in data.items()}


@dataclass(frozen=True)
class ChainConfig:
    """Contents of ``chain.json``: the rules of one chain repository."""

    application: str
    environments: tuple[str, ...]
    volatile_attributes: tuple[str, ...] = DEFAULT_VOLATILE_ATTRIBUTES
    attribute_order: dict[str, tuple[str, ...]] = field(default_factory=dict)
    child_order: dict[str, tuple[str, ...]] = field(default_factory=dict)
    letter_rule: LetterRule = field(default_factory=LetterRule)
    constants: dict[str, Selector] = field(default_factory=dict)
    dedupe_jobnames: bool = False
    git: GitRules | None = None  # None: the defaults, not written to chain.json

    @property
    def git_rules(self) -> GitRules:
        return self.git or GitRules()

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "application": self.application,
            "environments": list(self.environments),
            "letter_rule": {
                "prefixes": list(self.letter_rule.prefixes),
                "attributes": list(self.letter_rule.attributes),
                **(
                    {"leading_only": list(self.letter_rule.leading_only)}
                    if self.letter_rule.leading_only
                    else {}
                ),
            },
            "volatile_attributes": list(self.volatile_attributes),
            "attribute_order": {k: list(v) for k, v in self.attribute_order.items()},
            "child_order": {k: list(v) for k, v in self.child_order.items()},
            "constants": {k: v.to_json() for k, v in self.constants.items()},
            "dedupe_jobnames": self.dedupe_jobnames,
        }
        if self.git is not None:
            data["git"] = self.git.to_json()
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ChainConfig:
        from controlm_chain_admin.core.constants import Selector  # local: avoids an import cycle

        try:
            rule = data.get("letter_rule", {})
            return cls(
                application=str(data["application"]),
                environments=tuple(str(e) for e in data["environments"]),
                volatile_attributes=tuple(
                    str(a) for a in data.get("volatile_attributes", DEFAULT_VOLATILE_ATTRIBUTES)
                ),
                attribute_order=_tuple_map(data.get("attribute_order", {}), "attribute_order"),
                child_order=_tuple_map(data.get("child_order", {}), "child_order"),
                letter_rule=LetterRule(
                    prefixes=tuple(str(p) for p in rule.get("prefixes", ())),
                    attributes=tuple(
                        str(a) for a in rule.get("attributes", DEFAULT_LETTER_ATTRIBUTES)
                    ),
                    leading_only=tuple(str(p) for p in rule.get("leading_only", ())),
                ),
                constants={
                    str(k): Selector.from_json(v) for k, v in data.get("constants", {}).items()
                },
                dedupe_jobnames=bool(data.get("dedupe_jobnames", False)),
                git=GitRules.from_json(data["git"]) if "git" in data else None,
            )
        except KeyError as exc:
            raise ModelError(f"chain.json: missing key {exc}") from exc


@dataclass(frozen=True)
class EnvConfig:
    """Contents of ``envs/<env>/env.json``: how one environment differs from the base."""

    name: str
    letter: str
    display: str
    constants: dict[str, str | None] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "letter": self.letter,
            "display": self.display,
            "constants": dict(self.constants),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> EnvConfig:
        try:
            return cls(
                name=str(data["name"]),
                letter=str(data["letter"]),
                display=str(data.get("display", str(data["name"]).upper())),
                constants={
                    str(k): (str(v) if v is not None else None)
                    for k, v in data.get("constants", {}).items()
                },
            )
        except KeyError as exc:
            raise ModelError(f"env.json: missing key {exc}") from exc


@dataclass(frozen=True)
class ChainRepo:
    """A chain repository rooted at ``root`` with its loaded configuration."""

    root: Path
    config: ChainConfig

    # paths -----------------------------------------------------------------
    @property
    def chain_file(self) -> Path:
        return self.root / CHAIN_FILE

    @property
    def export_meta_file(self) -> Path:
        return self.root / "meta" / "export.json"

    @property
    def folders_dir(self) -> Path:
        return self.root / "folders"

    def folder_dir(self, folder: str) -> Path:
        return self.folders_dir / folder

    def folder_file(self, folder: str) -> Path:
        return self.folder_dir(folder) / "folder.json"

    def job_file(self, folder: str, job: str) -> Path:
        return self.folder_dir(folder) / "jobs" / f"{job}.json"

    def folder_meta_file(self, folder: str) -> Path:
        return self.root / "meta" / "folders" / f"{folder}.json"

    def env_file(self, env: str) -> Path:
        return self.root / "envs" / env / "env.json"

    # persistence -----------------------------------------------------------
    def save_config(self, config: ChainConfig) -> ChainRepo:
        """Write ``chain.json`` and return the repository with the new configuration."""
        write_json(self.chain_file, config.to_json())
        return replace(self, config=config)

    def load_env(self, name: str) -> EnvConfig:
        """Read ``envs/<name>/env.json``; raises :class:`UnknownEnvironment` when absent."""
        if name not in self.config.environments or not self.env_file(name).is_file():
            known = ", ".join(self.config.environments) or "none"
            raise UnknownEnvironment(f"unknown environment {name!r} (known: {known})")
        return EnvConfig.from_json(read_json(self.env_file(name)))

    def env_letters(self) -> dict[str, str]:
        """Letter of every declared environment, by environment name."""
        return {name: self.load_env(name).letter for name in self.config.environments}


def write_json(path: Path, data: Any) -> None:
    """Write JSON deterministically: 2-space indent, UTF-8, LF, trailing newline, keys as given."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ModelError(f"missing file {path}") from exc
    except json.JSONDecodeError as exc:
        raise ModelError(f"invalid JSON in {path}: {exc}") from exc


def init_repo(
    root: Path,
    application: str,
    environments: Sequence[str],
    *,
    letters: Mapping[str, str] | None = None,
    prefixes: Sequence[str] = (),
    leading_only: Sequence[str] = (),
) -> ChainRepo:
    """Create ``chain.json`` and one ``envs/<env>/env.json`` per environment in ``root``.

    ``letters`` maps an environment to its letter; by default the upper-cased first character of
    the environment name (test → T, uat → U, bench → B, prod → P). ``prefixes`` are the bare
    prefixes of the letter rule; without them the rule is disabled. Names starting with one of
    ``leading_only`` carry the letter on their first token only (``URQ_P77_X``).
    """
    root.mkdir(parents=True, exist_ok=True)
    if (root / CHAIN_FILE).exists():
        raise RepoExists(f"{root} already is a chain repository ({CHAIN_FILE} exists)")
    names = tuple(environments)
    chosen = {env: (letters or {}).get(env, env[:1].upper()) for env in names}
    if len(set(chosen.values())) != len(chosen):
        raise ModelError(f"environment letters must be distinct: {chosen}")
    config = ChainConfig(
        application=application,
        environments=names,
        letter_rule=LetterRule(prefixes=tuple(prefixes), leading_only=tuple(leading_only)),
    )
    repo = ChainRepo(root=root, config=config).save_config(config)
    for env in names:
        env_config = EnvConfig(name=env, letter=chosen[env], display=env.upper())
        write_json(repo.env_file(env), env_config.to_json())
    return repo


def load_repo(root: Path) -> ChainRepo:
    """Open an existing chain repository; raises :class:`NotAChainRepo` otherwise."""
    chain_file = root / CHAIN_FILE
    if not chain_file.is_file():
        raise NotAChainRepo(f"{root} is not a chain repository: no {CHAIN_FILE} found")
    return ChainRepo(root=root, config=ChainConfig.from_json(read_json(chain_file)))
