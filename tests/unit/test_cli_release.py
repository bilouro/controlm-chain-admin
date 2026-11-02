"""ctmchain release: start a release, mark its installations, update it, close it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.core.repo import load_repo
from tests.support.gitrepo import chain_git_repo, commit_all, git, plain_git_identity

C = "P77_CHAIN"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    return chain_git_repo(tmp_path).root


def run(root: Path, *args: str) -> int:
    return main(["release", *args, "--repo", str(root)])


def test_a_release_from_start_to_close(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(root, "start", "march") == 0
    assert capsys.readouterr().out == "Started release/march from main\n"
    repo = load_repo(root)
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))
    sha = commit_all(root, "fix: describe P77_E")

    assert run(root, "installed", "uat") == 0
    assert capsys.readouterr().out == f"Tagged uat/march-1 on {sha[:7]}: release/march in uat\n"

    assert run(root, "status") == 0
    out = capsys.readouterr().out
    assert "On release/march · editable · 0 uncommitted chain files" in out
    assert "  release/march  1 ahead of main  uat: uat/march-1  prod: -" in out
    assert run(root, "status", "--format", "json") == 0
    assert json.loads(capsys.readouterr().out)["release"] == "march"

    assert run(root, "installed", "prod", "--release", "march", "--commit", sha[:7]) == 0
    capsys.readouterr()
    assert run(root, "close") == 0
    assert capsys.readouterr().out.startswith("Closed release/march: merged into main (")
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_switch_update_and_errors(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(root, "status") == 0
    assert "On main · read-only: main is protected" in capsys.readouterr().out
    run(root, "start", "march")
    repo = load_repo(root)
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "draft"}))

    assert run(root, "switch", "main") == 3
    assert "1 uncommitted chain file on release/march" in capsys.readouterr().err
    assert run(root, "switch", "main", "--stash") == 0
    assert capsys.readouterr().out.endswith("Switched to main\n")
    assert run(root, "status") == 0
    assert "  stash@{0} on release/march: fix: update job P77_E in P77_CHAIN" in (
        capsys.readouterr().out
    )
    assert run(root, "update") == 3
    assert "main is protected" in capsys.readouterr().err
    assert run(root, "start", "april", "--stash") == 0
    capsys.readouterr()
    assert run(root, "update") == 3
    assert "already has every commit of main" in capsys.readouterr().err


def test_editing_commands_refuse_to_write_on_the_trunk(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["rename-job", f"{C}/P77_E", "P77_E2", "--repo", str(root)]

    assert main(args) == 0  # a preview writes nothing
    capsys.readouterr()
    assert main([*args, "--apply"]) == 3
    assert "main is protected" in capsys.readouterr().err


def test_without_a_subcommand_it_prints_the_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["release"]) == 2
    assert "ctmchain release {status,start" in capsys.readouterr().out
