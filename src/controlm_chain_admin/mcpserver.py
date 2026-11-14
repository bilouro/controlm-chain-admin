"""``ctmchain mcp``: the chain repository as tools for an assistant (Kilo, Claude, ...).

A thin adapter: the tools are :class:`~controlm_chain_admin.tools.ChainTools`, the same ones
``python -m ctmadmin_service`` runs where an MCP server is not allowed. Needs the ``[mcp]``
extra.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from controlm_chain_admin import __version__
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.tools import WRITERS, ChainTools, error_message, instructions

__all__ = ["ChainTools", "build_server", "run"]

READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

_Tool = TypeVar("_Tool", bound=Callable[..., Any])


def _errors_as_messages(tool: _Tool) -> _Tool:
    """A core error reaches the assistant with its message, to correct the call."""

    @functools.wraps(tool)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return tool(*args, **kwargs)
        except ChainError as exc:
            raise ToolError(error_message(exc)) from exc

    return wrapper  # type: ignore[return-value]


def build_server(root: Path) -> MCPServer:
    """The MCP server of the chain repository at ``root``."""
    tools = ChainTools(root)
    server = MCPServer("ctmchain", instructions=instructions(tools.catalogue), version=__version__)
    for name, description in tools.descriptions().items():
        server.add_tool(
            _errors_as_messages(getattr(tools, name)),
            name=name,
            description=description,
            annotations=WRITES if name in WRITERS else READS,
        )
    return server


def run(root: Path) -> None:  # pragma: no cover - blocks on stdin; tested over stdio
    """Serve the repository at ``root`` over stdin/stdout until the client goes."""
    build_server(root).run("stdio")
