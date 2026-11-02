"""ctmchain package: the Control-M import file with every folder a branch changed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.core.repo import load_repo
from tests.support.gitrepo import chain_git_repo, commit_all, git

C, ING = "P77_CHAIN", "P77_INGEST_DAILY"


def _feature(tmp_path: Path) -> tuple[Path, str, str]:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "feature")
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    chain = commit_all(repo.root, "feat: describe P77_C")
    apply(repo, set_attributes(repo, f"{ING}/P77_INGEST_LOAD", {"DESCRIPTION": "Ingest"}))
    ingest = commit_all(repo.root, "feat: describe the load")
    return repo.root, chain, ingest


def test_package_writes_the_changed_folders(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, *_ = _feature(tmp_path)
    out = tmp_path / "deploy.xml"

    code = main(
        ["package", "main", "feature", "--env", "uat", "--repo", str(root), "-o", str(out)]
    )

    assert code == 0
    text = capsys.readouterr().out
    assert text.startswith("Package main..feature for uat: 2 folders, 2 commits")
    assert "P77_CHAIN (7 jobs): job P77_C modified" in text
    assert f"Wrote {out}" in text
    assert b'FOLDER_NAME="UP77_CHAIN"' in out.read_bytes()


def test_package_of_selected_commits_as_a_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _chain, ingest = _feature(tmp_path)
    monkeypatch.chdir(tmp_path)

    code = main(
        ["package", "main", "feature", "--env", "uat", "--repo", str(root),
         "--commit", ingest[:8], "--dry-run"]
    )  # fmt: skip

    assert code == 0
    text = capsys.readouterr().out
    assert "1 folder, 1 of 2 commits" in text and "P77_INGEST_DAILY" in text
    assert "P77_CHAIN" not in text and "Wrote" not in text
    assert not list(tmp_path.glob("*.xml"))


def test_package_default_file_name_and_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, *_ = _feature(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["package", "main", "feature", "--env", "uat", "--repo", str(root),
                 "--format", "json"]) == 0  # fmt: skip

    data = json.loads(capsys.readouterr().out)
    assert {f["name"] for f in data["folders"]} == {C, ING}  # in export order
    assert (tmp_path / data["filename"]).is_file() and data["filename"].startswith("deploy_uat_")


def test_nothing_to_package(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root, *_ = _feature(tmp_path)

    assert main(["package", "feature", "feature", "--env", "uat", "--repo", str(root)]) == 0

    assert "Nothing to package" in capsys.readouterr().out


def test_a_selection_that_needs_a_left_out_commit_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, chain, _ingest = _feature(tmp_path)
    repo = load_repo(root)
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded twice"}))
    again = commit_all(root, "feat: describe P77_C again")

    code = main(["package", "main", "feature", "--env", "uat", "--repo", str(root),
                 "--commit", again, "--dry-run"])  # fmt: skip

    assert code == 3
    assert f"without {chain[:7]}" in capsys.readouterr().err


def test_compare_accepts_a_selection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root, _chain, ingest = _feature(tmp_path)

    assert main(["compare", "main", "feature", "--repo", str(root), "--commit", ingest]) == 0

    out = capsys.readouterr().out
    assert "1 of 2 commits" in out and "P77_INGEST_LOAD" in out and "P77_C\n" not in out
