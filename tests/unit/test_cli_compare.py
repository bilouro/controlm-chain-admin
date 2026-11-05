"""ctmchain compare: text for the terminal, Markdown for a pull request, JSON for tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.refactor import (
    apply,
    insert_job,
    rename_job,
    set_attributes,
    update_relation,
)
from tests.support.gitrepo import chain_git_repo, commit_all, git

C = "P77_CHAIN"


def _feature(tmp_path: Path) -> Path:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "feature")
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    apply(repo, update_relation(repo, "P77_A-P77_B_OK", f"{C}/P77_B", and_or="O"))
    commit_all(repo.root, "feat: tune the chain")
    apply(repo, rename_job(repo, f"{C}/P77_D", "P77_DELTA"))
    commit_all(repo.root, "refactor: rename P77_D")
    return repo.root


def test_text_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _feature(tmp_path)

    assert main(["compare", "main", "feature", "--repo", str(root)]) == 0

    out = capsys.readouterr().out
    assert out.startswith("Compare main..feature: 2 commits")
    assert "renamed  job P77_CHAIN/P77_DELTA (was P77_CHAIN/P77_D)" in out
    assert "DESCRIPTION: (none) -> Loaded" in out
    assert "predecessor P77_A-P77_B_OK modified: AND_OR A -> O" in out
    assert "condition renamed P77_OLDNAME-P77_D_OK -> P77_OLDNAME-P77_DELTA_OK" in out
    assert "feat: tune the chain" in out


def test_markdown_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _feature(tmp_path)

    assert main(["compare", "main", "feature", "--repo", str(root), "--format", "md"]) == 0
    md = capsys.readouterr().out
    assert md.startswith("## Chain changes: main..feature")
    assert "| renamed | job | P77_CHAIN/P77_DELTA |" in md

    assert main(["compare", "main", "feature", "--repo", str(root), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["jobs"]["renamed"] == 1 and len(data["commits"]) == 2


def test_head_defaults_to_HEAD_and_worktree_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _feature(tmp_path)
    capsys.readouterr()

    assert main(["compare", "main", "--repo", str(root)]) == 0
    assert "Compare main..HEAD" in capsys.readouterr().out
    assert main(["compare", "HEAD", "--worktree", "--repo", str(root)]) == 0
    assert "No changes" in capsys.readouterr().out


def test_errors_exit_3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _feature(tmp_path)

    assert main(["compare", "main", "nope", "--repo", str(root)]) == 3
    assert "unknown git ref" in capsys.readouterr().err


def test_text_report_summarises_the_attributes_of_an_added_job(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "feature")
    apply(repo, insert_job(repo, f"{C}/P77_NEW", after=f"{C}/P77_A", before=f"{C}/P77_B"))
    commit_all(repo.root, "feat: insert P77_NEW")

    assert main(["compare", "main", "feature", "--repo", str(repo.root)]) == 0

    out = capsys.readouterr().out
    assert "added    job P77_CHAIN/P77_NEW" in out
    assert "JOBNAME: (none) -> P77_NEW" not in out
    assert "attributes (see --format json)" in out
    assert "predecessor P77_A-P77_NEW_OK added" in out


def test_real_only_leaves_out_what_only_calls_a_condition_another_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _feature(tmp_path)  # renaming P77_D renames its conditions
    assert main(["compare", "main", "feature", "--repo", str(root)]) == 0
    full = capsys.readouterr().out

    assert main(["compare", "main", "feature", "--repo", str(root), "--real-only"]) == 0
    real = capsys.readouterr().out
    assert main(["compare", "main", "feature", "--repo", str(root), "--real-only",
                 "--format", "json"]) == 0  # fmt: skip
    body = json.loads(capsys.readouterr().out)

    assert "condition renamed" in full and "[name only]" in full
    assert "condition renamed" not in real and "[name only]" not in real
    assert f"modified job {C}/P77_C" in real
    assert body["links"] == [] and body["summary"]["name_only"] == 0
