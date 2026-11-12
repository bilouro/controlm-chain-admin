"""``ctmchain mcp``: the chain repository as tools for an assistant (Kilo, Claude, ...).

A thin adapter over the core, like the CLI and the web API. Questions call
:mod:`~controlm_chain_admin.core.lookup`, validate, compare, the map of the environments, what
can be taken, what a package would hold and what an export would bring; a change is a list of
steps of :mod:`~controlm_chain_admin.core.capabilities`, previewed first and written only by
its ``preview_id``, after the same checks as the web API (a protected branch refuses; a preview
the repository moved away from is stale). Nothing is committed, no branch is switched; the one
other thing written is the import file of a package. Needs the ``[mcp]`` extra.
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
    cut_lines,
    load_catalogue,
    plan,
    preview_steps,
    render_menu,
)
from controlm_chain_admin.core.capabilities import preview_id as id_of
from controlm_chain_admin.core.compare import compare as compare_refs
from controlm_chain_admin.core.compare import render_text
from controlm_chain_admin.core.deliveries import (
    build_delivery,
    remove_delivery,
    save_delivery,
)
from controlm_chain_admin.core.deliveries import listed as listed_deliveries
from controlm_chain_admin.core.environments import branch_of_env
from controlm_chain_admin.core.envmap import show_map
from controlm_chain_admin.core.errors import ChainError, ChangeConflict, TakeConflict
from controlm_chain_admin.core.links import folder_names
from controlm_chain_admin.core.lookup import describe_node, find_condition, find_nodes
from controlm_chain_admin.core.package import Package, build_package, save
from controlm_chain_admin.core.refactor import apply as apply_change
from controlm_chain_admin.core.refresh import Refresh
from controlm_chain_admin.core.refresh import refresh as refresh_env
from controlm_chain_admin.core.refresh import render_text as render_refresh
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from controlm_chain_admin.core.take import conflict_line
from controlm_chain_admin.core.take import takeable as takeable_items
from controlm_chain_admin.core.validate import validate as validate_repo
from controlm_chain_admin.core.workspace import ensure_editable

READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
#: every other tool only reads
WRITERS = frozenset(
    {"apply", "write_package", "keep_delivery", "remove_delivery", "write_delivery_package"}
)
APPLIED_NOTE = (
    "Written, not committed: the user reviews it (the Workspace page, or git) and commits."
)
REFRESH_NOTE = (
    "The user applies it: the Refresh page, or ctmchain refresh FILE --apply (it checks the "
    "branch of the environment out, overwrites it and commits).\n"
)
PACKAGE_NOTE = "Nothing in the repository changed: the file is what the user imports in Control-M."
DELIVERY_NOTE = (
    "Kept on the branch of the map, beside the map: no environment's branch and no file of "
    "the working tree changed. The Deliveries page, or delivery_package, makes the import file."
)
DELIVERIES_SHOWN = 100
FINDINGS_SHOWN = 20

_Tool = TypeVar("_Tool", bound=Callable[..., Any])


def _errors_as_messages(tool: _Tool) -> _Tool:
    """A core error reaches the assistant with its message, to correct the call."""

    @functools.wraps(tool)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return tool(*args, **kwargs)
        except TakeConflict as exc:
            lines = [str(exc), *(conflict_line(c) for c in exc.conflicts)]
            raise ToolError("\n".join(lines)) from exc
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
        shown = {finding["code"] for finding in findings[:limit]}
        return {
            "counts": report["counts"],
            "total": len(findings),
            "findings": findings[:limit],
            "explanations": {c: e for c, e in report["explanations"].items() if c in shown},
        }

    def compare(
        self,
        base: str,
        head: str,
        real_only: bool = False,
        lines: int = 200,
        prefer: list[str] | None = None,
        raw: bool = False,
    ) -> str:
        result = compare_refs(self.root, base, head, translate=not raw, prefer=prefer or ())
        text = render_text(result.real_only() if real_only else result)
        return cut_lines(text, lines, "real_only=true leaves out the conditions only renamed")

    def envmap(self) -> dict[str, Any]:
        return show_map(load_repo(self.root))

    def takeable(
        self, head: str, base: str = "HEAD", prefer: list[str] | None = None, limit: int = 200
    ) -> dict[str, Any]:
        found = takeable_items(self.root, base, head, prefer=prefer or ()).to_json()
        return {**found, "items": found["items"][:limit], "total": len(found["items"])}

    def _package(
        self, base: str, head: str, take: list[str] | None, prefer: list[str] | None,
        env: str | None,
    ) -> Package:  # fmt: skip
        return build_package(self.root, base, head, env=env, take=take, prefer=prefer or ())

    def package(
        self,
        base: str,
        head: str = "HEAD",
        take: list[str] | None = None,
        prefer: list[str] | None = None,
        env: str | None = None,
    ) -> dict[str, Any]:
        return _package_summary(self._package(base, head, take, prefer, env))

    def write_package(
        self,
        base: str,
        head: str = "HEAD",
        take: list[str] | None = None,
        prefer: list[str] | None = None,
        env: str | None = None,
        output: str | None = None,
    ) -> dict[str, Any]:
        package = self._package(base, head, take, prefer, env)
        path = save(package, self.root / (output or package.filename))
        return {"path": str(path), **_package_summary(package), "note": PACKAGE_NOTE}

    def deliveries(self) -> dict[str, Any]:
        rows = listed_deliveries(load_repo(self.root))
        return {"deliveries": rows[:DELIVERIES_SHOWN], "total": len(rows)}

    def keep_delivery(
        self,
        name: str,
        head: str,
        items: list[str],
        base: str | None = None,
        prefer: list[str] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        kept = save_delivery(
            load_repo(self.root), name, head, items, base=base, prefer=prefer or (), note=note
        )
        return {"kept": kept.to_json(), "note": DELIVERY_NOTE}

    def remove_delivery(self, name: str) -> dict[str, Any]:
        remove_delivery(load_repo(self.root), name)
        return self.deliveries()

    def delivery_package(
        self, target: str, names: list[str], env: str | None = None
    ) -> dict[str, Any]:
        return _package_summary(build_delivery(self.root, target, names, env=env))

    def write_delivery_package(
        self, target: str, names: list[str], env: str | None = None, output: str | None = None
    ) -> dict[str, Any]:
        package = build_delivery(self.root, target, names, env=env)
        path = save(package, self.root / (output or package.filename))
        return {"path": str(path), **_package_summary(package), "note": PACKAGE_NOTE}

    def refresh(
        self,
        xml: str,
        env: str | None = None,
        lines: int = 200,
        here: bool = False,
        partial: bool = False,
    ) -> str:
        path = self.root / xml  # an absolute path stays as it is
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ChainError(f"cannot read the export {path}: {exc.strerror}") from exc
        repo = load_repo(self.root)
        result = refresh_env(repo, data, source=path.name, env=env, here=here, partial=partial)
        text = render_refresh(result) + _refresh_note(result, repo)
        return cut_lines(text, lines, "ctmchain refresh FILE shows them all")

    def preview(self, steps: list[dict[str, Any]], diff_lines: int = 400) -> dict[str, Any]:
        return preview_steps(load_repo(self.root), steps, diff_lines=diff_lines)

    def apply(self, steps: list[dict[str, Any]], preview_id: str) -> dict[str, Any]:
        repo = load_repo(self.root)
        ensure_editable(repo)
        change = plan(repo, steps)
        if not change.edits:
            raise ChangeConflict(f"{change.summary}: nothing to change any more")
        if id_of(change) != preview_id:
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
            "compare": "What changed between two git refs (branches, tags, commits), as text. "
                       "Two environments (main, env/uat, ...) show their real differences only: "
                       "names, users and machines are read through the map; prefer=[entry] "
                       "settles a value two entries explain; raw=true shows them as stored.",
            "envmap": "The environments, the branch each one has and the map of what varies "
                      "between them (letters, users, machines, datacenters). Read only.",
            "takeable": "What head (a branch or an environment) has that base (default: the "
                        "branch checked out) has not, as items with the ids the capability "
                        "take and the tools package and write_package accept.",
            "package": "What the Control-M import file of base would hold with what head has: "
                       "folders and why, warnings, new findings, the file name. take=[ids as "
                       "takeable gives them, like job:FOLDER/JOB] "
                       "packages only those; base main means production. Writes nothing.",
            "write_package": "Write that import file, once the user agreed: the same arguments "
                             "as package; output names the file (default: its own name, in the "
                             "repository directory). Never over an existing file; nothing in "
                             "the repository changes.",
            "deliveries": "The deliveries kept for later: items put aside under a name, with "
                          "the branch and the commit they come from and whether that branch "
                          "moved since. Read only.",
            "keep_delivery": "Keep items for later under a name, once the user agreed: head is "
                             "the branch (tag, commit) they come from, items their ids as "
                             "takeable gives them (job:FOLDER/JOB, attr:FOLDER/JOB@NAME, "
                             "folder:FOLDER ...), base the ref they were chosen against, if "
                             "any. Written on the branch of the map; no environment changes.",
            "remove_delivery": "Forget one delivery by its name, once the user agreed.",
            "delivery_package": "What the import file of target (a branch: main, env/bench) "
                                "would hold with the deliveries names on what it has, in that "
                                "order: folders and why, warnings, the file name. Two "
                                "deliveries that disagree are refused. Writes nothing.",
            "write_delivery_package": "Write that import file, once the user agreed: the same "
                                      "arguments as delivery_package; output names the file. "
                                      "Never over an existing file.",
            "refresh": "What the full export of one environment (xml: the path of the file) "
                       "would change in the branch of that environment. here=true: in the "
                       "branch checked out instead, a branch of the user's own, and the "
                       "environment's stays as it is; partial=true with it: the export holds "
                       "some folders only, the others stay. A preview: only the user applies "
                       "it.",
            "preview": "Preview a change without writing: steps [{do: <capability>, params}] run "
                       f"in order as one change. Capabilities: {signatures}. Returns a "
                       "preview_id, each field before -> after, warnings and the diff.",
            "apply": "Write a change previewed before, once the user agreed: the same steps and "
                     "the preview_id. Refused when the repository changed since; nothing is "
                     "committed.",
        }  # fmt: skip


def _refresh_note(result: Refresh, repo: ChainRepo) -> str:
    """How the user applies the export just previewed: onto the branch it was previewed on."""
    if not result.work:
        return REFRESH_NOTE
    flags = "--here --partial" if result.partial else "--here"
    own = branch_of_env(repo.config, result.env)
    return (
        f"The user applies it: the Refresh page (Onto: {result.branch}, checked out), or "
        f"ctmchain refresh FILE {flags} --apply (it writes onto {result.branch} and commits; "
        f"{own} stays as it is).\n"
    )


def _package_summary(package: Package) -> dict[str, Any]:
    """What a package holds, without its commits and with the first findings only."""
    data = package.to_json()
    keys = ("env", "source", "taken", "folders", "warnings", "filename", "size")
    return {
        "base": package.base.name,
        "head": package.head.name,
        **{key: data[key] for key in keys},
        "findings": data["findings"][:FINDINGS_SHOWN],
        "findings_total": len(data["findings"]),
    }


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
