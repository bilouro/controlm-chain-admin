"""Semantic comparison of two refs of a chain repository (feature branch vs develop)."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.errors import GitError
from controlm_chain_admin.core.history import WORKTREE
from controlm_chain_admin.core.refactor import (
    apply,
    insert_job,
    link_nodes,
    move_job,
    rename_folder,
    rename_job,
    rename_link,
    set_attributes,
    set_variables,
    unlink_nodes,
    update_relation,
)
from controlm_chain_admin.core.repo import ChainRepo
from tests.support.gitrepo import chain_git_repo, commit_all, git

C = "P77_CHAIN"


def _feature(tmp_path: Path) -> ChainRepo:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "feature")
    return repo


def _job(result, node: str):  # type: ignore[no-untyped-def]
    return next(j for j in result.jobs if j.node == node)


def test_identical_refs_have_no_changes(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)

    result = compare(repo.root, "main", "main")

    assert result.jobs == () and result.folders == () and result.links == ()
    assert result.summary()["jobs"] == {
        "added": 0,
        "removed": 0,
        "modified": 0,
        "renamed": 0,
        "moved": 0,
    }


def test_modified_job_lists_attribute_and_variable_changes_and_the_commits(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_B", {"DESCRIPTION": "Loaded", "CMDLINE": None}))
    apply(repo, set_variables(repo, f"{C}/P77_B", [{"NAME": "%%X", "VALUE": "1"}]))
    commit_all(repo.root, "feat: describe P77_B")

    result = compare(repo.root, "main", "feature")

    (job,) = result.jobs
    assert (job.node, job.change, job.previous) == (f"{C}/P77_B", "modified", None)
    assert {(a.name, a.before, a.after) for a in job.attributes} == {
        ("DESCRIPTION", None, "Loaded"),
        ("CMDLINE", "/opt/p77/bin/b.ksh", None),
    }
    assert [(v.name, v.before, v.after) for v in job.variables] == [("%%X", None, "1")]
    assert (
        job.before is not None and job.after is not None and '"DESCRIPTION": "Loaded"' in job.diff
    )
    assert [c.subject for c in result.commits] == ["feat: describe P77_B"]
    assert result.base.name == "main" and result.head.name == "feature"


def test_renamed_job_and_its_condition_names(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, rename_job(repo, f"{C}/P77_B", "P77_BETA"))
    commit_all(repo.root, "refactor: rename P77_B")

    result = compare(repo.root, "main", "feature")

    (job,) = result.jobs
    assert (job.node, job.change, job.previous) == (f"{C}/P77_BETA", "renamed", f"{C}/P77_B")
    assert [(a.name, a.before, a.after) for a in job.attributes] == [
        ("JOBNAME", "P77_B", "P77_BETA")
    ]
    assert job.relations == ()  # same links, peers mapped through the rename
    renamed = {(lk.link, lk.before, lk.after) for lk in result.links if lk.change == "renamed"}
    assert ("P77_A-P77_B_OK", "P77_A-P77_B_OK", "P77_A-P77_BETA_OK") in renamed


def test_moved_job_and_renamed_folder(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, move_job(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD", C))
    apply(repo, rename_folder(repo, C, "P77_FLOW"))
    commit_all(repo.root, "refactor: reorganise")

    result = compare(repo.root, "main", "feature")

    (folder,) = [f for f in result.folders if f.change == "renamed"]
    assert (folder.node, folder.previous) == ("P77_FLOW/", f"{C}/")
    moved = _job(result, "P77_FLOW/P77_INGEST_LOAD")
    assert moved.change == "moved" and moved.previous == "P77_INGEST_DAILY/P77_INGEST_LOAD"
    assert [j.node for j in result.jobs] == [
        "P77_FLOW/P77_INGEST_LOAD"
    ]  # jobs only renamed by the folder are not listed


def test_relation_changes_keep_the_plus_minus_details(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, link_nodes(repo, f"{C}/P77_E", producer=f"{C}/P77_C"))
    apply(repo, update_relation(repo, "P77_A-P77_B_OK", f"{C}/P77_B", and_or="O", cleanup=False))
    apply(repo, unlink_nodes(repo, "P77_B-P77_C_OK", f"{C}/P77_C"))
    commit_all(repo.root, "feat: rewire")

    result = compare(repo.root, "main", "feature")

    e = {r.link: r for r in _job(result, f"{C}/P77_E").relations}
    added = e["P77_C-P77_E_OK"]
    assert (added.direction, added.change, added.peers_after) == (
        "predecessor",
        "added",
        (f"{C}/P77_C",),
    )
    b = {(r.direction, r.link): r for r in _job(result, f"{C}/P77_B").relations}
    changed = b[("predecessor", "P77_A-P77_B_OK")]
    assert changed.change == "modified"
    assert {(d.name, d.before, d.after) for d in changed.details} == {
        ("AND_OR", "A", "O"),
        ("cleanup", "yes", "no"),
    }
    removed = b[("successor", "P77_B-P77_C_OK")]
    assert (
        removed.change == "modified"
        and removed.peers_before == (f"{C}/P77_C",)
        and removed.peers_after == ()
    )
    links = {(lk.link, lk.change) for lk in result.links}
    assert ("P77_C-P77_E_OK", "added") in links


def test_added_and_removed_jobs_and_renamed_conditions(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, insert_job(repo, f"{C}/P77_NEW", after=f"{C}/P77_A", before=f"{C}/P77_B"))
    apply(repo, rename_link(repo, "P77_D-P77_NOBODY_OK", "P77_D_DONE"))
    commit_all(repo.root, "feat: insert P77_NEW")

    result = compare(repo.root, "main", "feature")

    new = _job(result, f"{C}/P77_NEW")
    assert new.change == "added" and new.before is None and new.after is not None
    assert {(lk.link, lk.change, lk.after) for lk in result.links} >= {
        ("P77_D-P77_NOBODY_OK", "renamed", "P77_D_DONE"),
        ("P77_NEW-P77_B_OK", "added", "P77_NEW-P77_B_OK"),
    }
    counts = result.summary()
    assert counts["jobs"]["added"] == 1 and counts["links"]["renamed"] >= 1


def test_merge_base_shows_only_what_the_feature_changed(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_B", {"DESCRIPTION": "feature"}))
    commit_all(repo.root, "feat: on the feature")
    git(repo.root, "checkout", "-q", "main")
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "main moved on"}))
    commit_all(repo.root, "fix: on main")

    pr_style = compare(repo.root, "main", "feature")
    direct = compare(repo.root, "main", "feature", use_merge_base=False)

    assert [j.node for j in pr_style.jobs] == [f"{C}/P77_B"]
    assert pr_style.merge_base is not None and pr_style.merge_base != pr_style.base.sha
    assert {j.node for j in direct.jobs} == {f"{C}/P77_B", f"{C}/P77_C"}


def test_uncommitted_changes_against_head(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_B", {"DESCRIPTION": "draft"}))

    result = compare(repo.root, "HEAD", WORKTREE)

    assert [j.node for j in result.jobs] == [f"{C}/P77_B"] and result.head.kind == "worktree"


def test_constant_values_per_environment(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    define_constant(
        repo, "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH", "prod": "PP77_BATCH"}
    )
    commit_all(repo.root, "constants")
    git(repo.root, "checkout", "-q", "-b", "feature")
    define_constant(repo, "node.batch", Selector("NODEID"), {"prod": "PP77_BATCH_NEW"})
    commit_all(repo.root, "new prod node")

    result = compare(repo.root, "main", "feature")

    assert [(c.env, c.name, c.before, c.after) for c in result.constants] == [
        ("prod", "node.batch", "PP77_BATCH", "PP77_BATCH_NEW")
    ]


def test_volatile_metadata_alone_is_not_a_node_change(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    meta = repo.root / "meta/folders/P77_CHAIN.json"
    meta.write_text(
        meta.read_text("utf-8").replace('"JOBISN": "2"', '"JOBISN": "20"'), encoding="utf-8"
    )
    commit_all(repo.root, "chore: metadata")

    result = compare(repo.root, "main", "feature")

    assert result.jobs == () and result.metadata_files_changed == 1


def test_unknown_ref(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)

    with pytest.raises(GitError, match="nope"):
        compare(repo.root, "main", "nope")


def test_removed_relation_shows_the_condition_name_it_had_before(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, insert_job(repo, f"{C}/P77_NEW", after=f"{C}/P77_A", before=f"{C}/P77_B"))
    commit_all(repo.root, "feat: insert P77_NEW")

    result = compare(repo.root, "main", "feature")

    b = {(r.direction, r.change): r for r in _job(result, f"{C}/P77_B").relations}
    assert b[("predecessor", "removed")].name == "P77_A-P77_B_OK"
    assert b[("predecessor", "added")].name == "P77_NEW-P77_B_OK"
