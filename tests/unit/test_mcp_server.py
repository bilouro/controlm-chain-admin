"""ctmchain mcp: the tools an assistant (Kilo, Claude, ...) uses to answer and to change chains."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client, StdioServerParameters

from controlm_chain_admin.core.kilo import AGENT_FILE, CONFIG, kilo_files
from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.mcpserver import ChainTools, build_server
from tests.support.fourenvs import (
    CHAIN,
    LETTERS,
    export_of,
    four_branches,
    two_users_in,
    uat_ahead,
    with_map,
    without_folder,
)
from tests.support.gitrepo import chain_git_repo, commit_all, git, plain_git_identity

WRITERS = {"apply", "write_package", "keep_delivery", "remove_delivery",
           "write_delivery_package"}  # fmt: skip
TOOLS = {
    "menu", "find", "show", "condition", "validate", "compare", "envmap", "takeable",
    "package", "refresh", "preview", "deliveries", "delivery_package", "resources", *WRITERS,
}  # fmt: skip
BENCH, UAT = "env/bench", "env/uat"
NEW_JOB = f"job:{CHAIN}/P77_NEW"
STEPS = [
    {"do": "change-fields", "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"MAXWAIT": "3"}}}
]


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    """The synthetic chain in git, on a release branch (main is protected)."""
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "release/26.1")
    return repo


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


@pytest.fixture
def envs(tmp_path: Path) -> ChainRepo:
    """Four environments, one branch each, with their map; uat is ahead of the others and
    bench runs one job as another user; the branch of bench is checked out."""
    repo = four_branches(tmp_path, change=two_users_in("bench"))
    with_map(repo)
    git(repo.root, "switch", "-q", BENCH)
    return load_repo(repo.root)


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
    assert read_only == TOOLS - WRITERS
    assert tools["apply"].annotations.destructive_hint is False
    assert "take(head, items, theirs?, prefer?)" in (tools["preview"].description or "")
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
    assert set(report["explanations"]) == {f["code"] for f in report["findings"]}  # of those


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


def test_the_kilo_agent_names_every_tool_and_is_asked_before_each_one_that_writes(
    repo: ChainRepo,
) -> None:
    files = kilo_files(repo.root, sys.executable)
    agent, config = files[AGENT_FILE], json.loads(files[CONFIG])

    assert {f"ctmchain_{tool}" for tool in TOOLS} == set(re.findall(r"ctmchain_[a-z_]+", agent))
    assert {name for name, rule in config["permission"].items() if rule == "ask"} == {
        f"ctmchain_{tool}" for tool in WRITERS
    }


# ---------------------------------------------------------------- one branch per environment


def test_the_assistant_is_told_how_the_environments_are_kept(envs: ChainRepo) -> None:
    server = build_server(envs.root)
    menu = _data(_call(envs.root, "menu"))

    assert "one branch per environment" in (server.instructions or "")
    assert "  take: Take changes from another branch or environment" in menu
    for tool in ("envmap", "takeable", "package", "refresh"):
        assert f"  {tool}: " in menu


def test_envmap_gives_the_branches_the_letters_and_the_entries(envs: ChainRepo) -> None:
    shown = _data(_call(envs.root, "envmap"))

    assert shown["branch"] == "map" and shown["letters"] == LETTERS
    assert shown["branches"]["prod"] == "main" and shown["branches"]["uat"] == UAT
    assert {"run_as.1", "run_as.2", "nodeid.1"} <= {entry["name"] for entry in shown["entries"]}


def test_compare_two_environments_by_their_real_differences(envs: ChainRepo) -> None:
    arguments = {"base": BENCH, "head": UAT}

    text = _data(_call(envs.root, "compare", arguments))
    settled = _data(_call(envs.root, "compare", {**arguments, "prefer": ["run_as.2"]}))
    raw = _data(_call(envs.root, "compare", {**arguments, "raw": True}))

    assert text.startswith("Compare env/bench (bench) with env/uat (uat): real differences only")
    assert "kept as it is" in text and "kept as it is" not in settled
    assert "RUN_AS: abp77proc -> aup77proc" in raw and "RUN_AS: abp77proc" not in text


def test_takeable_lists_the_items_with_the_ids_take_accepts(envs: ChainRepo) -> None:
    found = _data(_call(envs.root, "takeable", {"head": UAT}))
    first = _data(_call(envs.root, "takeable", {"head": UAT, "base": "main", "limit": 2}))

    assert (found["into"], found["from"], found["environments"]) == (BENCH, UAT, ["bench", "uat"])
    assert {"id": NEW_JOB, "label": "the whole job, added"} in found["items"]
    assert found["total"] == len(found["items"])
    assert first["into"] == "main" and len(first["items"]) == 2 and first["total"] > 2


def test_a_take_is_previewed_then_applied_like_any_change(envs: ChainRepo) -> None:
    steps = [{"do": "take", "params": {"head": UAT, "items": [NEW_JOB],
                                       "prefer": ["run_as.1"]}}]  # fmt: skip

    preview = _data(_call(envs.root, "preview", {"steps": steps}))
    applied = _data(
        _call(envs.root, "apply", {"steps": steps, "preview_id": preview["preview_id"]})
    )

    assert preview["summary"].startswith("take 1 change from env/uat")
    assert f"folders/{CHAIN}/jobs/P77_NEW.json" in preview["files"]
    assert applied["written"] >= 1
    new = read_json(envs.root / "folders" / CHAIN / "jobs" / "P77_NEW.json")
    assert new["RUN_AS"] == "abp77proc"  # the user of bench: the map turned it


def test_a_conflict_of_a_take_names_the_item_and_its_three_values(repo: ChainRepo) -> None:
    node, item = f"{CHAIN}/P77_A", f"attr:{CHAIN}/P77_A@CMDLINE"
    git(repo.root, "switch", "-q", "-c", "release/26.2", "main")
    apply(repo, set_attributes(repo, node, {"CMDLINE": "/opt/p77/bin/theirs.ksh"}))
    commit_all(repo.root, "feat: their script")
    git(repo.root, "switch", "-q", "release/26.1")
    mine = load_repo(repo.root)
    apply(mine, set_attributes(mine, node, {"CMDLINE": "/opt/p77/bin/mine.ksh"}))
    commit_all(repo.root, "feat: my script")
    steps = [{"do": "take", "params": {"head": "release/26.2", "items": [item]}}]

    result = _call(repo.root, "preview", {"steps": steps})
    forced = _data(
        _call(repo.root, "preview", {"steps": [{**steps[0], "params": {
            **steps[0]["params"], "theirs": [item]}}]})
    )  # fmt: skip

    message = result.content[0].text
    assert result.is_error and "1 item(s) changed in the checkout too" in message
    assert (
        f"conflict {item}: mine /opt/p77/bin/mine.ksh, before /opt/p77/bin/a.ksh, "
        "theirs /opt/p77/bin/theirs.ksh"
    ) in message
    assert forced["changes"][0]["after"] == "/opt/p77/bin/theirs.ksh"


def test_package_says_what_would_go_to_production_and_writes_nothing(envs: ChainRepo) -> None:
    arguments = {"base": "main", "head": UAT, "take": [NEW_JOB], "prefer": ["run_as.1"]}

    package = _data(_call(envs.root, "package", arguments))
    nothing = _data(_call(envs.root, "package", {"base": UAT, "head": UAT, "env": "uat"}))

    assert (package["env"], package["source"], package["taken"]) == ("prod", "uat", [NEW_JOB])
    assert package["folders"] == [{"name": CHAIN, "jobs": 8, "reasons": ["job P77_NEW added"]}]
    assert package["filename"].startswith("deploy_prod_env-uat_1-item_")
    assert package["size"] > 0 and package["warnings"] == []
    assert nothing["size"] == 0 and nothing["folders"] == []
    assert not list(envs.root.glob("*.xml"))


def test_write_package_writes_the_import_file_and_never_over_another(envs: ChainRepo) -> None:
    arguments = {"base": "main", "head": UAT, "take": [NEW_JOB], "prefer": ["run_as.1"]}

    written = _data(_call(envs.root, "write_package", arguments))
    again = _call(envs.root, "write_package", arguments)
    named = _data(_call(envs.root, "write_package", {**arguments, "output": "out/prod.xml"}))
    empty = _call(envs.root, "write_package", {"base": UAT, "head": UAT, "env": "uat"})

    path = Path(written["path"])
    assert path == envs.root / written["filename"] and written["size"] == path.stat().st_size
    assert b'JOBNAME="PP77_NEW"' in path.read_bytes()
    assert b'RUN_AS="app77proc"' in path.read_bytes()
    assert again.is_error and "is there already" in again.content[0].text
    assert Path(named["path"]) == envs.root / "out" / "prod.xml"
    assert empty.is_error and "nothing to package" in empty.content[0].text


def test_refresh_shows_what_an_export_brings_and_writes_nothing(
    envs: ChainRepo, tmp_path: Path
) -> None:
    export = tmp_path / "uat.xml"
    export.write_bytes(uat_ahead("uat", export_of("uat")).replace(b"a2.ksh -x", b"a3.ksh"))
    before = git(envs.root, "rev-parse", UAT)

    text = _data(_call(envs.root, "refresh", {"xml": str(export)}))
    short = _data(_call(envs.root, "refresh", {"xml": str(export), "lines": 3}))
    missing = _call(envs.root, "refresh", {"xml": "nowhere.xml"})

    assert text.startswith("Refresh env/uat (uat) from uat.xml: 3 folders, 12 jobs")
    assert "CMDLINE: /opt/p77/bin/a2.ksh -x -> /opt/p77/bin/a3.ksh" in text
    assert "Nothing written" in text and "ctmchain refresh" in text
    assert len(short.splitlines()) == 4 and "more lines" in short
    assert missing.is_error and "nowhere.xml" in missing.content[0].text
    assert git(envs.root, "rev-parse", UAT) == before
    assert git(envs.root, "branch", "--show-current") == BENCH


def test_refresh_onto_the_branch_of_one_s_own_whole_or_some_folders(
    envs: ChainRepo, tmp_path: Path
) -> None:
    whole, some = tmp_path / "next.xml", tmp_path / "delivery.xml"
    whole.write_bytes(uat_ahead("uat", export_of("uat")).replace(b"a2.ksh -x", b"a3.ksh"))
    some.write_bytes(without_folder(whole.read_bytes(), "UP77_INGEST_DAILY"))
    on_bench = _call(envs.root, "refresh", {"xml": str(whole), "here": True})
    git(envs.root, "switch", "-q", "-c", "work/uat-next", UAT)
    before = git(envs.root, "rev-parse", "HEAD")

    onto = _data(_call(envs.root, "refresh", {"xml": str(whole), "here": True}))
    part = _data(_call(envs.root, "refresh", {"xml": str(some), "here": True, "partial": True}))
    alone = _call(envs.root, "refresh", {"xml": str(some), "partial": True})

    assert onto.startswith("Import onto work/uat-next (uat) from next.xml: 3 folders, 12 jobs")
    assert "CMDLINE: /opt/p77/bin/a2.ksh -x -> /opt/p77/bin/a3.ksh" in onto
    assert "ctmchain refresh FILE --here --apply" in onto and "env/uat stays as it is" in onto
    assert "a partial export: the folders it does not have stay" in part
    assert "ctmchain refresh FILE --here --partial --apply" in part
    assert "removed" not in part  # the folder it lacks stays
    assert on_bench.is_error and "env/bench holds bench" in on_bench.content[0].text
    assert alone.is_error and "a branch of your own" in alone.content[0].text
    assert git(envs.root, "rev-parse", "HEAD") == before
    assert git(envs.root, "status", "--porcelain") == ""


def test_the_assistant_is_told_about_a_branch_of_one_s_own(envs: ChainRepo) -> None:
    server = build_server(envs.root)
    described = ChainTools(envs.root).descriptions()["refresh"]
    agent = kilo_files(envs.root, sys.executable)[AGENT_FILE]

    assert "here=true" in described and "partial=true" in described
    for text in (server.instructions or "", agent):
        flat = " ".join(text.split())
        assert "here=true" in flat and "partial=true" in flat
        assert "the environment of the last export" in flat


def test_resources_lists_who_uses_each_and_a_capability_gives_one_to_several_jobs(
    repo: ChainRepo,
) -> None:
    before = _data(_call(repo.root, "resources"))
    nodes = ["P77_CHAIN/P77_A", "P77_CHAIN/P77_B"]
    steps = [{"do": "set-resource", "params": {"nodes": nodes, "name": "RQ_AM"}}]
    preview = _data(_call(repo.root, "preview", {"steps": steps}))
    _call(repo.root, "apply", {"steps": steps, "preview_id": preview["preview_id"]})
    after = _data(_call(repo.root, "resources", {"name": "rq_am"}))

    assert before["total"] == 1 and before["resources"][0]["count"] == 1
    assert after["resources"][0]["nodes"] == [
        "P77_CHAIN/P77_A", "P77_CHAIN/P77_B", "P77_INGEST_DAILY/P77_INGEST_INIT",
    ]  # fmt: skip


def test_deliveries_are_kept_listed_packaged_and_removed(envs: ChainRepo) -> None:
    item = f"job:{CHAIN}/P77_NEW"
    none = _data(_call(envs.root, "deliveries"))
    kept = _data(_call(envs.root, "keep_delivery", {
        "name": "new job", "head": UAT, "items": [item], "base": BENCH, "note": "for Friday",
    }))  # fmt: skip
    listed = _data(_call(envs.root, "deliveries"))
    preview = _data(_call(envs.root, "delivery_package", {"target": BENCH, "names": ["new job"]}))
    chosen = {"target": BENCH, "names": ["new job"], "output": "out/bench.xml"}
    written = _data(_call(envs.root, "write_delivery_package", chosen))
    twice = _call(envs.root, "keep_delivery", {"name": "new job", "head": UAT, "items": [item]})
    gone = _data(_call(envs.root, "remove_delivery", {"name": "new job"}))

    assert none == {"deliveries": [], "total": 0}
    assert kept["kept"]["name"] == "new job" and "branch of the map" in kept["note"]
    (row,) = listed["deliveries"]
    assert (row["name"], row["head"], row["items"], row["moved"]) == (
        "new job",
        UAT,
        [item],
        False,
    )
    assert preview["env"] == "bench" and preview["taken"] == [item]
    assert [f["name"] for f in preview["folders"]] == [CHAIN]
    path = Path(written["path"])
    assert path == envs.root / "out" / "bench.xml" and b'JOBNAME="BP77_NEW"' in path.read_bytes()
    assert twice.is_error and "already" in twice.content[0].text
    assert gone == {"deliveries": [], "total": 0}
    assert git(envs.root, "branch", "--show-current") == BENCH  # no branch was switched


def test_the_assistant_is_told_about_deliveries(envs: ChainRepo) -> None:
    server = build_server(envs.root)
    agent = kilo_files(envs.root, sys.executable)[AGENT_FILE]
    menu = _data(_call(envs.root, "menu"))

    assert "keep_delivery" in (server.instructions or "")
    assert "ctmchain_keep_delivery" in agent and "ctmchain_write_delivery_package" in agent
    assert "  deliveries: " in menu


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
