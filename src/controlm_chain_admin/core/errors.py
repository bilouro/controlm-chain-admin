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


class OrderConflict(ChainError):
    """Observed attribute or child order contradicts the order recorded in ``chain.json``."""


class ModelError(ChainError):
    """The JSON in the repository does not match the expected shape."""


class UnknownEnvironment(ChainError):
    """The environment is not declared in ``chain.json`` or has no ``env.json``."""


class EnvironmentRequired(ChainError):
    """The letter rule is enabled, so import and export need to know the environment."""
