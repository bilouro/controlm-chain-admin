"""ctmchain mcp: the tools an assistant (Kilo, Claude, ...) uses to answer and to change chains."""

from __future__ import annotations

import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client, StdioServerParameters

from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.mcpserver import build_server
from tests.support.gitrepo import chain_git_repo, commit_all, git

TOOLS = {"menu", "find", "show", "condition", "validate", "compare", "preview", "apply"}
STEPS = [
    {"do": "change-fields", "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"MAXWAIT": "3"}}}
]


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    """The synthetic chain in git, on a release branch (main is protected)."""
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "release/26.1")
    return repo


def _run(root: Path, use: Callable[[Client], Awaitable[Any]]) -> Any:
    async def main() -> Any:
        async with Client(build_server(root)) as client:
            return await use(client)

    return anyio.run(main)


def _call(root: Path, tool: str, arguments: dict[str, Any] | None = None) -> Any:
    async def use(client: Client) -> Any:
        return await client.call_tool(tool, arguments or {})

    return _run(root, use)


def _data(result: Any) -> Any:
    assert not result.is_error, result.content[0].text
    if result.structured_content is not None:
        return result.structured_content.get("result", result.structured_content)
    return result.content[0].text


def test_the_tools_and_which_of_them_only_read(repo: ChainRepo) -> None:
    async def use(client: Client) -> Any:
        return (await client.list_tools()).tools

    tools = {tool.name: tool for tool in _run(repo.root, use)}

    assert set(tools) == TOOLS
    read_only = {name for name, tool in tools.items() if tool.annotations.read_only_hint}
    assert read_only == TOOLS - {"apply"}
    assert tools["apply"].annotations.destructive_hint is False
    assert "change-fields(nodes, changes)" in (tools["preview"].description or "")
    assert "change-in-env(env, nodes, attributes?, variables?, drop?)" in (
        tools["preview"].description or ""
    )


def test_the_server_tells_the_assistant_how_to_work(repo: ChainRepo) -> None:
    server = build_server(repo.root)

    assert "Find before you change" in (server.instructions or "")
    assert "never commit or push" in (server.instructions or "")


def test_menu_gives_the_repository_and_the_capabilities(repo: ChainRepo) -> None:
    text = _data(_call(repo.root, "menu"))
    detail = _data(_call(repo.root, "menu", {"capability": "change-in-env"}))

    assert text.startswith("Repository P77_RISK_ENGINE: 2 folders; environments uat, prod")
    assert "What you can ask" in text and "change-fields" in text
    assert detail.startswith("change-in-env (set-exception)")


def test_find_show_and_condition_answer_questions(repo: ChainRepo) -> None:
    found = _data(_call(repo.root, "find", {"attribute": "CMDLINE", "value": "load.ksh"}))
    job = _data(_call(repo.root, "show", {"node": "P77_CHAIN/P77_B"}))
    condition = _data(_call(repo.root, "condition", {"name": "P77_B-P77_C_OK"}))

    assert [m["node"] for m in found["matches"]] == ["P77_INGEST_DAILY/P77_INGEST_LOAD"]
    assert job["waits_for"][0]["condition"] == "P77_A-P77_B_OK"
    assert condition["to"] == ["P77_CHAIN/P77_C"]


def test_validate_counts_the_findings_and_lists_the_first(repo: ChainRepo) -> None:
    report = _data(_call(repo.root, "validate", {"limit": 2}))

    assert report["counts"]["error"] >= 1
    assert len(report["findings"]) == 2 and report["total"] > 2
    assert set(report["findings"][0]) >= {"severity", "code", "message"}


def test_compare_two_refs_as_text(repo: ChainRepo) -> None:
    apply(repo, set_attributes(repo, "P77_CHAIN/P77_C", {"DESCRIPTION": "Loaded"}))
    commit_all(repo.root, "feat: describe P77_C")

    text = _data(_call(repo.root, "compare", {"base": "main", "head": "release/26.1"}))

    assert text.startswith("Compare main..release/26.1: 1 commit")
    assert "P77_CHAIN/P77_C" in text


def test_a_long_comparison_is_cut_and_says_so(repo: ChainRepo) -> None:
    apply(repo, set_attributes(repo, "P77_CHAIN/P77_C", {"DESCRIPTION": "Loaded"}))
    commit_all(repo.root, "feat: describe P77_C")

    text = _data(_call(repo.root, "compare", {"base": "main", "head": "release/26.1", "lines": 2}))

    assert len(text.splitlines()) == 3
    assert text.splitlines()[-1].startswith("... ") and "more lines" in text


def test_preview_then_apply_writes_the_change(repo: ChainRepo) -> None:
    steps = [{"do": "change-fields",
              "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"MAXWAIT": "3"}}}]  # fmt: skip

    async def use(client: Client) -> Any:
        preview = _data(await client.call_tool("preview", {"steps": steps}))
        before = read_json(repo.job_file("P77_CHAIN", "P77_B")).get("MAXWAIT")
        applied = _data(
            await client.call_tool("apply", {"steps": steps, "preview_id": preview["preview_id"]})
        )
        return preview, before, applied

    preview, before, applied = _run(repo.root, use)

    assert preview["summary"] == "set MAXWAIT on P77_CHAIN/P77_B"
    assert preview["changes"] == [
        {"where": "P77_CHAIN/P77_B", "field": "MAXWAIT", "before": None, "after": "3"}
    ]
    assert '+  "MAXWAIT": "3"' in preview["diff"]
    assert preview["files"] == ["folders/P77_CHAIN/jobs/P77_B.json"]
    assert before is None
    assert applied["written"] == 1 and "not committed" in applied["note"]
    assert read_json(repo.job_file("P77_CHAIN", "P77_B"))["MAXWAIT"] == "3"


def test_a_preview_is_stale_once_the_repository_changed(repo: ChainRepo) -> None:
    steps = [{"do": "change-fields",
              "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"MAXWAIT": "3"}}}]  # fmt: skip

    async def use(client: Client) -> Any:
        preview = _data(await client.call_tool("preview", {"steps": steps}))
        fresh = load_repo(repo.root)
        apply(fresh, set_attributes(fresh, "P77_CHAIN/P77_B", {"MAXWAIT": "9"}))
        return await client.call_tool(
            "apply", {"steps": steps, "preview_id": preview["preview_id"]}
        )

    result = _run(repo.root, use)

    assert result.is_error and "the repository changed since" in result.content[0].text
    assert read_json(repo.job_file("P77_CHAIN", "P77_B"))["MAXWAIT"] == "9"


def test_another_server_applies_what_one_previewed(repo: ChainRepo) -> None:
    preview = _data(_call(repo.root, "preview", {"steps": STEPS}))

    applied = _data(
        _call(repo.root, "apply", {"steps": STEPS, "preview_id": preview["preview_id"]})
    )

    assert applied["written"] == 1
    assert read_json(repo.job_file("P77_CHAIN", "P77_B"))["MAXWAIT"] == "3"


def test_steps_other_than_the_previewed_ones_are_refused(repo: ChainRepo) -> None:
    preview = _data(_call(repo.root, "preview", {"steps": STEPS}))
    other = [{"do": "change-fields",
              "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"MAXWAIT": "4"}}}]  # fmt: skip

    result = _call(repo.root, "apply", {"steps": other, "preview_id": preview["preview_id"]})

    assert result.is_error and "the steps are not the same" in result.content[0].text
    assert "MAXWAIT" not in read_json(repo.job_file("P77_CHAIN", "P77_B"))


def test_a_change_already_made_is_not_applied_again(repo: ChainRepo) -> None:
    preview = _data(_call(repo.root, "preview", {"steps": STEPS}))
    _call(repo.root, "apply", {"steps": STEPS, "preview_id": preview["preview_id"]})

    again = _call(repo.root, "apply", {"steps": STEPS, "preview_id": preview["preview_id"]})
    nothing = _data(_call(repo.root, "preview", {"steps": STEPS}))

    assert again.is_error and "nothing to change any more" in again.content[0].text
    assert nothing["preview_id"] is None and nothing["summary"].endswith(": nothing to change")


def test_apply_on_the_protected_trunk_is_refused(repo: ChainRepo) -> None:
    git(repo.root, "checkout", "-q", "main")
    steps = [{"do": "change-fields",
              "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"MAXWAIT": "3"}}}]  # fmt: skip

    async def use(client: Client) -> Any:
        preview = _data(await client.call_tool("preview", {"steps": steps}))
        return await client.call_tool(
            "apply", {"steps": steps, "preview_id": preview["preview_id"]}
        )

    result = _run(repo.root, use)

    assert result.is_error and "main is protected" in result.content[0].text


def test_an_unknown_preview_is_refused(repo: ChainRepo) -> None:
    result = _call(repo.root, "apply", {"steps": STEPS, "preview_id": "nope"})

    assert result.is_error
    assert "this is not the change previewed as nope" in result.content[0].text


def test_errors_reach_the_assistant_with_their_message(repo: ChainRepo) -> None:
    result = _call(repo.root, "preview", {"steps": [{"do": "change-fields", "params": {}}]})
    unknown = _call(repo.root, "show", {"node": "P77_CHAIN/P77_NOPE"})

    assert result.is_error and "change-fields: nodes is missing" in result.content[0].text
    assert unknown.is_error and "unknown job" in unknown.content[0].text


def test_a_long_diff_is_cut_and_says_so(repo: ChainRepo) -> None:
    steps = [{"do": "rename-folder", "params": {"folder": "P77_CHAIN", "new_name": "P77_LINK"}}]

    preview = _data(_call(repo.root, "preview", {"steps": steps, "diff_lines": 5}))

    assert len(preview["diff"].splitlines()) == 6 and "more lines" in preview["diff"]


def test_the_server_runs_over_stdio(repo: ChainRepo) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "controlm_chain_admin", "mcp", "--repo", str(repo.root)],
    )

    async def main() -> Any:
        async with Client(parameters) as client:
            tools = await client.list_tools()
            found = await client.call_tool("find", {"text": "ingest_load"})
            return {tool.name for tool in tools.tools}, found

    names, found = anyio.run(main)

    assert names == TOOLS
    assert json.loads(found.content[0].text)["total"] == 1
