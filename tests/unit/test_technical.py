"""The technical attributes: what Control-M writes by itself (ids, dates, versions) lives in
``meta/``, is never compared and never an exception. The list is the repository's own, to
extend with a name that turned out to be noise or to cut when a name matters after all."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.errors import InvalidChange
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.refactor import apply, run_operation, set_technical
from controlm_chain_admin.core.repo import load_repo, read_json
from tests.support.gitrepo import chain_git_repo, commit_all, git

ING = "P77_INGEST_DAILY"
LOAD = "P77_INGEST_LOAD"


def test_a_name_added_to_the_list_moves_its_values_to_meta(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    before = export_xml(repo, "uat")

    change = set_technical(repo, add=["DESCRIPTION"])
    apply(repo, change)

    assert change.summary == "technical attributes: +DESCRIPTION (3 values moved to meta)"
    assert {e.path for e in change.edits} >= {"chain.json", f"meta/folders/{ING}.json"}
    repo = load_repo(repo.root)
    assert "DESCRIPTION" in repo.config.volatile_attributes
    assert "DESCRIPTION" not in read_json(repo.job_file(ING, LOAD))
    meta = read_json(repo.folder_meta_file(ING))
    assert meta["jobs"][LOAD]["DESCRIPTION"] == "Load positions"
    assert meta["attrs"]["DESCRIPTION"] == "Daily ingest & load"
    assert export_xml(repo, "uat") == before  # the export merges meta back: nothing moves


def test_a_name_removed_from_the_list_comes_back_into_the_nodes(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    before = export_xml(repo, "uat")

    apply(repo, run_operation(repo, "set-technical", {"remove": ["JOBISN"]}))

    repo = load_repo(repo.root)
    assert "JOBISN" not in repo.config.volatile_attributes
    job = read_json(repo.job_file(ING, LOAD))
    assert job["JOBISN"] == "3" and next(iter(job)) == "JOBISN"  # in the canonical order
    assert "JOBISN" not in read_json(repo.folder_meta_file(ING))["jobs"][LOAD]
    assert read_json(repo.folder_file(ING))["JOBISN"] == "1"
    assert export_xml(repo, "uat") == before


def test_the_list_refuses_names_and_what_a_constant_replaces(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    define_constant(repo, "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH"})
    commit_all(repo.root, "chore: a constant")

    with pytest.raises(InvalidChange, match="nothing"):
        set_technical(repo)
    with pytest.raises(InvalidChange, match="invalid attribute name"):
        set_technical(repo, add=["bad name"])
    with pytest.raises(InvalidChange, match="JOBNAME is a name"):
        set_technical(repo, add=["JOBNAME"])
    with pytest.raises(InvalidChange, match=r"constant node\.batch"):
        set_technical(repo, add=["NODEID"])
    with pytest.raises(InvalidChange, match="already technical"):
        set_technical(repo, add=["JOBISN"])
    with pytest.raises(InvalidChange, match="not technical"):
        set_technical(repo, remove=["NOPE"])


def test_the_technical_command_lists_adds_and_removes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from controlm_chain_admin.cli import main

    root = chain_git_repo(tmp_path).root
    git(root, "switch", "-q", "-c", "release/technical")
    r = ["--repo", str(root)]

    assert main(["technical", *r]) == 0
    assert capsys.readouterr().out.splitlines()[:2] == ["JOBISN", "CREATION_USER"]
    assert main(["technical", "--add", "DESCRIPTION", "--remove", "JOBISN", *r, "--apply"]) == 0
    out = capsys.readouterr().out
    assert "technical attributes: +DESCRIPTION, -JOBISN (" in out and "Applied" in out
    assert main(["technical", *r]) == 0
    listed = capsys.readouterr().out.splitlines()
    assert "DESCRIPTION" in listed and "JOBISN" not in listed
    assert main(["technical", "--add", "JOBNAME", *r]) == 3
