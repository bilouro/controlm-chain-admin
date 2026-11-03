"""Typed errors raised by the core. Adapters map them to exit codes or HTTP statuses."""

from __future__ import annotations


class ChainError(Exception):
    """Base class of every error raised by :mod:`controlm_chain_admin.core`."""


class XmlFormatError(ChainError):
    """The XML is not a Control-M export this tool can reproduce byte-for-byte."""


class NotAChainRepo(ChainError):
    """The directory has no ``chain.json``."""


class RepoExists(ChainError):
    """``init`` was asked to create a chain repository where one already exists."""


class UnsafeName(ChainError):
    """A folder or job name cannot be used as a file-system path component."""


class DuplicateName(ChainError):
    """Two elements share an identity that must be unique (e.g. two jobs with one JOBNAME)."""


class ModelError(ChainError):
    """The JSON in the repository does not match the expected shape."""


class UnknownEnvironment(ChainError):
    """The environment is not declared in ``chain.json`` or has no ``env.json``."""


class EnvironmentRequired(ChainError):
    """The letter rule or constants are in use, so import and export need the environment."""


class UnresolvedConstant(ChainError):
    """A ``@{name}`` placeholder has no value in the target environment."""


class ConstantConflict(ChainError):
    """A constant definition contradicts the registry (name, selector or duplicate value)."""


class ChangeConflict(ChainError):
    """A file touched by a change set was modified after the preview was computed."""


class InvalidChange(ModelError):
    """A requested edit is not allowed or not consistent (bad attribute, duplicate link...)."""


class GitError(ChainError):
    """A git command failed (not a git repository, unknown ref...)."""


class SelectionConflict(GitError):
    """A selected commit does not apply without commits that were left out of the selection."""

    def __init__(
        self, message: str, commit: str, paths: tuple[str, ...], missing: tuple[str, ...]
    ) -> None:
        super().__init__(message)
        self.commit = commit
        self.paths = paths
        self.missing = missing  # left-out commits that touched the same files before it

    @property
    def detail(self) -> dict[str, object]:
        return {"commit": self.commit, "paths": list(self.paths), "missing": list(self.missing)}


class NothingToPackage(ChainError):
    """No folder changed, so there is no import file to write."""


class NothingToCommit(ChainError):
    """The chain files have no uncommitted change."""


class ProtectedBranch(ChainError):
    """Edits are refused on the trunk, another protected branch or a detached HEAD."""


class UncommittedChanges(GitError):
    """Uncommitted chain files stop a switch, a merge or a restore: commit, stash or discard."""

    def __init__(self, message: str, changes: int) -> None:
        super().__init__(message)
        self.changes = changes

    @property
    def detail(self) -> dict[str, object]:
        return {"changes": self.changes}


class MergeConflict(GitError):
    """A merge or a stash does not apply cleanly; nothing was changed."""

    def __init__(self, message: str, paths: tuple[str, ...]) -> None:
        super().__init__(message)
        self.paths = paths

    @property
    def detail(self) -> dict[str, object]:
        return {"paths": list(self.paths)}


class TakeConflict(InvalidChange):
    """Changes taken from another branch meet values the checkout changed too; nothing was taken.

    Each conflict says what the checkout has (``mine``), what the change starts from
    (``before``) and what it brings (``theirs``); take them anyway by naming them in ``theirs``.
    """

    def __init__(self, message: str, conflicts: tuple[dict[str, object], ...]) -> None:
        super().__init__(message)
        self.conflicts = conflicts

    @property
    def detail(self) -> dict[str, object]:
        return {"conflicts": list(self.conflicts)}
