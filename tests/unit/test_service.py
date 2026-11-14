"""``python -m ctmadmin_service``: the assistant's tools as commands, where MCP is not allowed."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from controlm_chain_admin import __version__
from controlm_chain_admin.core.repo import ChainRepo, read_json
from controlm_chain_admin.service import COMMAND, main
from tests.support.gitrepo import chain_git_repo, git, plain_git_identity

JOB = "P77_CHAIN/P77_B"


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    """The synthetic chain in git, on a release branch (main is protected)."""
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "release/26.1")
    return repo


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)
    monkeypatch.delenv("CTMCHAIN_REPO", raising=False)


def _run(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str], *argv: str, stdin: str | None = None
) -> tuple[int, str, str]:
    code = main(["--repo", str(repo.root), *argv], stdin=io.StringIO(stdin or ""))
    out, err = capsys.readouterr()
    return code, out, err


def _json(repo: ChainRepo, capsys: pytest.CaptureFixture[str], *argv: str, **kw: Any) -> Any:
    code, out, err = _run(repo, capsys, *argv, **kw)
    assert code == 0, err
    return json.loads(out)


# ---------------------------------------------------------------- help


def test_help_says_how_to_call_how_to_work_and_lists_every_tool_and_capability(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(repo, capsys, "help")

    assert code == 0
    assert f"{COMMAND} <tool>" in out
    assert "preview_id" in out and f"{COMMAND} apply <preview_id>" in out
    for tool in ("find", "show", "compare", "takeable", "package", "resources", "deliveries"):
        assert f"\n  {tool}" in out
    assert "change-fields(nodes, changes)" in out and "set-resource(" in out
    assert "KEY=VALUE" in out and "null" in out
    assert "Find before you change" in out and "one branch per environment" in out
    assert "capability=<id>" not in out and "the same steps" not in out


def test_help_of_a_tool_gives_its_parameters_and_a_command_to_copy(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(repo, capsys, "help", "package")

    assert code == 0
    assert "--base (required): text" in out
    assert "--take: text, repeat it for several" in out
    assert f"{COMMAND} package main --take job:FOLDER/JOB" in out


def test_help_of_a_capability_gives_its_rules_and_the_preview_command(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(repo, capsys, "help", "change-fields")

    assert code == 0
    assert "JOBNAME is changed with rename-job" in out
    assert f"{COMMAND} preview change-fields --nodes P77_CHAIN/P77_B --changes MAXWAIT=3" in out


def test_the_version_and_no_tool_at_all(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"ctmadmin_service {__version__}"
    assert main([]) == 2
    assert f"{COMMAND} help" in capsys.readouterr().err


# ---------------------------------------------------------------- questions


def test_a_question_prints_its_answer_as_json(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    found = _json(repo, capsys, "find", "ingest_l")
    shown = _json(repo, capsys, "show", "--node", JOB)
    by_flag = _json(repo, capsys, "find", "--attribute=TASKTYPE", "--value", "command")

    assert [m["node"] for m in found["matches"]] == ["P77_INGEST_DAILY/P77_INGEST_LOAD"]
    assert shown["node"] == JOB and shown["kind"] == "job"
    assert by_flag["total"] >= 1


def test_text_tools_print_text_and_flags_take_both_spellings(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(repo, capsys, "menu", "--capability", "change-fields")
    assert code == 0 and out.startswith("change-fields (")

    code, out, _ = _run(repo, capsys, "compare", "main", "HEAD", "--real-only")
    code_kebab, _, _ = _run(repo, capsys, "compare", "main", "HEAD", "--real_only", "true")
    assert code == 0 and code_kebab == 0


def test_the_repository_comes_from_the_environment_or_the_directory(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CTMCHAIN_REPO", str(repo.root))
    assert main(["find", "ingest_l"], stdin=io.StringIO("")) == 0
    monkeypatch.delenv("CTMCHAIN_REPO")
    monkeypatch.chdir(repo.root)
    assert main(["find", "ingest_l"], stdin=io.StringIO("")) == 0


# ---------------------------------------------------------------- changes


def test_preview_then_apply_by_the_id_alone(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    preview = _json(repo, capsys, "preview", "change-fields", "--nodes", JOB,
                    "--changes", "MAXWAIT=3")  # fmt: skip

    assert preview["changes"] == [{"where": JOB, "field": "MAXWAIT", "before": None, "after": "3"}]
    assert preview["apply"] == f"{COMMAND} apply {preview['preview_id']}"
    assert read_json(repo.job_file("P77_CHAIN", "P77_B")).get("MAXWAIT") is None

    applied = _json(repo, capsys, "apply", preview["preview_id"])

    assert applied["written"] == 1 and "not committed" in applied["note"]
    assert read_json(repo.job_file("P77_CHAIN", "P77_B"))["MAXWAIT"] == "3"
    code, _, err = _run(repo, capsys, "apply", preview["preview_id"])
    assert code == 3 and "nothing to change any more" in err


def test_a_value_null_removes_and_lists_repeat_the_flag(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _json(repo, capsys, "preview", "set-variable", "--nodes", JOB,
                  "--nodes", "P77_CHAIN/P77_C", "--name", "%%RETRIES", "--value", "3")  # fmt: skip
    _json(repo, capsys, "apply", first["preview_id"])

    removed = _json(repo, capsys, "preview", "set-variable", "--nodes", JOB,
                    "--name", "%%RETRIES", "--value", "null")  # fmt: skip

    assert {"folders/P77_CHAIN/jobs/P77_B.json", "folders/P77_CHAIN/jobs/P77_C.json"} <= set(
        first["files"]
    )
    assert removed["changes"][0]["where"] == JOB
    assert removed["summary"].startswith("remove")


def test_changes_that_belong_together_are_previewed_after_another(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _json(repo, capsys, "preview", "change-fields", "--nodes", JOB,
                  "--changes", "MAXWAIT=3")  # fmt: skip
    both = _json(repo, capsys, "preview", "change-fields", "--nodes", JOB,
                 "--changes", "MAXRERUN=2", "--after", first["preview_id"])  # fmt: skip

    assert {c["field"] for c in both["changes"]} == {"MAXWAIT", "MAXRERUN"}
    _json(repo, capsys, "apply", both["preview_id"])
    data = read_json(repo.job_file("P77_CHAIN", "P77_B"))
    assert (data["MAXWAIT"], data["MAXRERUN"]) == ("3", "2")


def test_steps_can_come_as_json_from_a_file_or_the_input(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    steps = [{"do": "change-fields", "params": {"nodes": [JOB], "changes": {"MAXWAIT": "4"}}}]
    path = tmp_path / "steps.json"
    path.write_text(json.dumps(steps), "utf-8")

    from_file = _json(repo, capsys, "preview", "--steps-file", str(path))
    from_input = _json(repo, capsys, "preview", "--steps", "-",
                       stdin="﻿" + json.dumps(steps[0]))  # fmt: skip

    assert from_file["preview_id"] == from_input["preview_id"]


def test_a_preview_that_changes_nothing_gives_no_id_to_apply(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    preview = _json(repo, capsys, "preview", "change-fields", "--nodes", JOB,
                    "--changes", "TASKTYPE=Command")  # fmt: skip

    assert preview["preview_id"] is None and "apply" not in preview


# ---------------------------------------------------------------- mistakes


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (["nope"], "unknown tool 'nope'"),
        (["find", "--colour", "x"], "find has no --colour"),
        (["find", "--limit", "many"], "--limit takes a whole number"),
        (["show"], "show needs --node"),
        (["preview"], "preview needs a capability"),
        (["preview", "nope"], "unknown capability 'nope'"),
        (["preview", "change-fields", "--nodes", JOB, "--changes", "MAXWAIT"], "KEY=VALUE"),
        (["preview", "--steps-file", "missing.json"], "cannot read the steps"),
        (["preview", "--steps", "-"], "the steps are not JSON"),
        (["apply"], "apply needs --preview_id"),
        (["find", "a", "b", "c", "d", "e", "f"], "too many values"),
    ],
)
def test_a_wrong_call_says_what_is_wrong_and_where_help_is(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str], argv: list[str], says: str
) -> None:
    code, out, err = _run(repo, capsys, *argv)

    assert code == 2, out
    assert says in err and f"{COMMAND} help" in err


def test_an_error_of_the_repository_is_its_message(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, _, err = _run(repo, capsys, "show", "P77_CHAIN/NOPE")
    assert code == 3 and err.startswith("error: ") and "NOPE" in err

    code, _, err = _run(repo, capsys, "apply", "never00previewed")
    assert code == 3 and "preview again" in err

    elsewhere = main(["--repo", str(tmp_path / "nowhere"), "find", "x"], stdin=io.StringIO(""))
    assert elsewhere == 3 and "--repo" in capsys.readouterr().err


def test_python_dash_m_runs_it(repo: ChainRepo) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ctmadmin_service", "--repo", str(repo.root), "find", "ingest_l"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["total"] == 1
