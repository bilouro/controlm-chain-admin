"""Typed errors raised by the core. Adapters map them to exit codes or HTTP statuses."""

from __future__ import annotations


class ChainError(Exception):
    """Base class of every error raised by :mod:`controlm_chain_admin.core`."""


class XmlFormatError(ChainError):
    """The XML is not a Control-M export this tool can reproduce byte-for-byte."""
