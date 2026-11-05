"""``ctmchain mcp``: the chain repository as tools for an assistant (Kilo, Claude, ...).

A thin adapter over the core, like the CLI and the web API. Questions call
:mod:`~controlm_chain_admin.core.lookup`, validate and compare; a change is a list of steps of
:mod:`~controlm_chain_admin.core.capabilities`, previewed first and written only by its
``preview_id``, after the same checks as the web API (a protected branch refuses; a preview
the repository moved away from is stale). Nothing is committed. Needs the ``[mcp]`` extra.
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
from controlm_chain_admin.core.capabilities import (
    Catalogue,
    changes_of,
    load_catalogue,
    plan,
    render_menu,
)
from controlm_chain_admin.core.compare import compare as compare_refs
from controlm_chain_admin.core.compare import render_text
from controlm_chain_admin.core.errors import ChainError, ChangeConflict
from controlm_chain_admin.core.links import folder_names
from controlm_chain_admin.core.lookup import describe_node, find_condition, find_nodes
from controlm_chain_admin.core.refactor import apply as apply_change
from controlm_chain_admin.core.refactor import fingerprint
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.core.validate import validate as validate_repo
from controlm_chain_admin.core.workspace import ensure_editable

READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
APPLIED_NOTE = (
    "Written, not committed: the user reviews it (the Workspace page, or git) and commits."
)

_Tool = TypeVar("_Tool", bound=Callable[..., Any])


def _errors_as_messages(tool: _Tool) -> _Tool:
    """A core error reaches the assistant with its message, to correct the call."""

    @functools.wraps(tool)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return tool(*args, **kwargs)
        except ChainError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def instructions(catalogue: Catalogue) -> str:
    """How the assistant works with these tools: the workflow of the capabilities file."""
    rules = "\n".join(f"- {rule}" for rule in catalogue.workflow)
    return (
        "Tools over a Control-M chain repository (ctmchain). menu lists what can be asked "
        "and how; preview turns steps into a change, apply writes it.\n" + rules
    )


def _cut(text: str, lines: int, hint: str) -> str:
    rows = text.splitlines()
    if len(rows) <= lines:
        return text
    return "\n".join([*rows[:lines], f"... {len(rows) - lines} more lines ({hint})"])


class ChainTools:
    """The tools over one chain repository. They keep nothing between calls: ``apply`` takes
    the steps again with the ``preview_id`` (the fingerprint of the previewed change), so a
    restarted server, or another one, applies exactly what was previewed or refuses."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        load_repo(self.root)  # not a chain repository: fail now, not at the first call
        self.catalogue = load_catalogue()

    def menu(self, capability: str | None = None) -> str:
        repo = load_repo(self.root)
        if capability:
            return render_menu(self.catalogue, capability)
        envs = ", ".join(repo.config.environments)
        head = f"Repository {repo.config.application}: {len(folder_names(repo))} folders"
        return f"{head}; environments {envs}\n\n{render_menu(self.catalogue)}"

    def find(
        self,
        text: str | None = None,
        attribute: str | None = None,
        value: str | None = None,
        env: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        repo = load_repo(self.root)
        return find_nodes(repo, text=text, attribute=attribute, value=value, env=env, limit=limit)

    def show(self, node: str, env: str | None = None) -> dict[str, Any]:
        return describe_node(load_repo(self.root), node, env)

    def condition(self, name: str) -> dict[str, Any]:
        return find_condition(load_repo(self.root), name)

    def validate(self, limit: int = 30) -> dict[str, Any]:
        report = validate_repo(load_repo(self.root)).to_json()
        findings = report["findings"]
        return {"counts": report["counts"], "total": len(findings), "findings": findings[:limit]}

    def compare(self, base: str, head: str, real_only: bool = False, lines: int = 200) -> str:
        result = compare_refs(self.root, base, head)
        text = render_text(result.real_only() if real_only else result)
        return _cut(text, lines, "real_only=true leaves out the conditions only renamed")

    def preview(self, steps: list[dict[str, Any]], diff_lines: int = 400) -> dict[str, Any]:
        change = plan(load_repo(self.root), steps)
        return {
            "preview_id": fingerprint(change)[:12] if change.edits else None,
            "summary": change.summary if change.edits else f"{change.summary}: nothing to change",
            "warnings": list(change.warnings),
            "changes": changes_of(change),
            "files": [edit.path for edit in change.edits],
            "diff": _cut(change.diff(), diff_lines, "diff_lines shows more"),
        }

    def apply(self, steps: list[dict[str, Any]], preview_id: str) -> dict[str, Any]:
        repo = load_repo(self.root)
        ensure_editable(repo)
        change = plan(repo, steps)
        if not change.edits:
            raise ChangeConflict(f"{change.summary}: nothing to change any more")
        if fingerprint(change)[:12] != preview_id:
            raise ChangeConflict(
                f"this is not the change previewed as {preview_id}: the repository changed "
                "since, or the steps are not the same; preview again"
            )
        result = apply_change(repo, change)
        return {"summary": change.summary, "written": result.written,
                "deleted": result.deleted, "note": APPLIED_NOTE}  # fmt: skip

    def descriptions(self) -> dict[str, str]:
        """What each tool does, as the assistant reads it."""
        signatures = ", ".join(c.signature for c in self.catalogue.capabilities)
        return {
            "menu": "What can be asked and how: every capability with an example; "
                    "capability=<id> gives its parameters and rules. Start here.",
            "find": "Find jobs and folders by part of a name (text), an attribute and part of "
                    "its value, or a value in any attribute; env: as that environment has them.",
            "show": "One job (FOLDER/JOB) or folder (FOLDER/): fields, variables, what it waits "
                    "for and releases, exceptions by environment; env: as that one has it.",
            "condition": "One condition by its name: who emits it (from), waits for it (to), "
                         "deletes it (cleanup).",
            "validate": "What is wrong with the chains: counts by severity, the first findings.",
            "compare": "What changed between two git refs (branches, tags, commits), as text.",
            "preview": "Preview a change without writing: steps [{do: <capability>, params}] run "
                       f"in order as one change. Capabilities: {signatures}. Returns a "
                       "preview_id, each field before -> after, warnings and the diff.",
            "apply": "Write a change previewed before, once the user agreed: the same steps and "
                     "the preview_id. Refused when the repository changed since; nothing is "
                     "committed.",
        }  # fmt: skip


def build_server(root: Path) -> MCPServer:
    """The MCP server of the chain repository at ``root``."""
    tools = ChainTools(root)
    server = MCPServer("ctmchain", instructions=instructions(tools.catalogue), version=__version__)
    for name, description in tools.descriptions().items():
        server.add_tool(
            _errors_as_messages(getattr(tools, name)),
            name=name,
            description=description,
            annotations=WRITES if name == "apply" else READS,
        )
    return server


def run(root: Path) -> None:  # pragma: no cover - blocks on stdin; tested over stdio
    """Serve the repository at ``root`` over stdin/stdout until the client goes."""
    build_server(root).run("stdio")
