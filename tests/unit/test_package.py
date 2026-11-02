"""The import package for Control-M: every folder a branch changed, whole, for one environment."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.errors import UnresolvedConstant
from controlm_chain_admin.core.history import WORKTREE
from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.package import build_package
from controlm_chain_admin.core.refactor import (
    apply,
    link_nodes,
    move_job,
    rename_folder,
    rename_link,
    set_attributes,
    unlink_nodes,
)
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.gitrepo import APP, chain_git_repo, commit_all, git
from tests.support.samples import SAMPLE_EXPORT

C, ING = "P77_CHAIN", "P77_INGEST_DAILY"
TODAY = "2026-11-02"


def _feature(tmp_path: Path) -> ChainRepo:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "feature/x")
    return repo


def _exported(xml: bytes) -> dict[str, list[str]]:
    """Folder name -> JOBNAMEs in the package."""
    root = parse_xml(xml).root
    return {
        str(dict(f.attrs).get("FOLDER_NAME")): [
            str(dict(j.attrs).get("JOBNAME")) for j in f.children if j.tag == "JOB"
        ]
        for f in root.children
    }


def _reasons(package) -> dict[str, tuple[str, ...]]:  # type: ignore[no-untyped-def]
    return {f.name: f.reasons for f in package.folders}


def test_a_changed_job_deploys_its_whole_folder_for_the_environment(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    commit_all(repo.root, "feat: describe P77_C")

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    assert _reasons(package) == {C: ("job P77_C modified",)}
    exported = _exported(package.xml or b"")
    assert list(exported) == ["UP77_CHAIN"]  # the letter rule applied for uat
    assert len(exported["UP77_CHAIN"]) == 7 and "UP77_C" in exported["UP77_CHAIN"]
    assert package.filename == f"deploy_uat_feature-x_{TODAY}.xml"
    assert package.size == len(package.xml or b"") and package.warnings == ()
    assert package.folders[0].jobs == 7


def test_nothing_changed_means_nothing_to_deploy(tmp_path: Path) -> None:
    repo = _feature(tmp_path)

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    assert package.folders == () and package.xml is None and package.size == 0


def test_a_moved_job_deploys_the_folder_it_left_and_the_one_it_joined(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, move_job(repo, f"{ING}/P77_INGEST_LOAD", C))
    commit_all(repo.root, "refactor: move the load job")

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    reasons = _reasons(package)
    assert reasons[C] == ("job P77_INGEST_LOAD moved here from P77_INGEST_DAILY",)
    assert reasons[ING] == ("job P77_INGEST_LOAD moved to P77_CHAIN",)
    assert set(_exported(package.xml or b"")) == {"UP77_CHAIN", "UP77_INGEST_DAILY"}


def test_a_folder_left_without_jobs_is_a_warning(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, move_job(repo, f"{ING}/P77_INGEST_LOAD", C))
    apply(repo, move_job(repo, f"{ING}/P77_INGEST_INIT", C))
    commit_all(repo.root, "refactor: empty the ingest folder")

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    assert {f.name: f.jobs for f in package.folders}[ING] == 0
    (warning,) = [w for w in package.warnings if ING in w]
    assert "no jobs left" in warning


def test_relation_changes_seen_only_from_the_other_end_do_not_pull_a_folder(
    tmp_path: Path,
) -> None:
    repo = chain_git_repo(tmp_path)
    apply(repo, link_nodes(repo, f"{ING}/P77_INGEST_INIT", link="P77_A-P77_B_OK"))
    commit_all(repo.root, "feat: the ingest also waits for P77_A")
    git(repo.root, "checkout", "-q", "-b", "feature/x")
    apply(repo, unlink_nodes(repo, "P77_A-P77_B_OK", f"{ING}/P77_INGEST_INIT"))
    commit_all(repo.root, "revert: it does not wait")

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    # P77_A loses a successor but its file is unchanged: only the ingest folder is deployed
    assert set(_reasons(package)) == {ING}


def test_a_renamed_condition_deploys_every_folder_that_uses_it(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    apply(repo, link_nodes(repo, f"{ING}/P77_INGEST_INIT", producer=f"{C}/P77_A"))
    commit_all(repo.root, "feat: the ingest waits for P77_A")
    (link,) = [
        lk.id
        for lk in load_links(repo).values()
        if [str(n) for n in lk.consumers] == [f"{ING}/P77_INGEST_INIT"]
        and [str(n) for n in lk.producers] == [f"{C}/P77_A"]
    ]
    git(repo.root, "checkout", "-q", "-b", "feature/x")
    apply(repo, rename_link(repo, link, "P77_A_DONE"))
    commit_all(repo.root, "refactor: rename the condition")

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    reasons = _reasons(package)
    assert set(reasons) == {C, ING}
    assert all(
        r[0].startswith("condition ") and "renamed to P77_A_DONE" in r[0] for r in reasons.values()
    )


def _constant_repo(tmp_path: Path) -> ChainRepo:
    root = tmp_path / "repo"
    repo = init_repo(root, APP, ("uat", "prod"), prefixes=("P77", "RQ_", "RC_"))
    repo = define_constant(
        repo, "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH", "prod": "PP77_BATCH"}
    )
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    git(root, "init", "-q", "-b", "main")
    commit_all(root, "import")
    git(root, "checkout", "-q", "-b", "feature/x")
    return repo


def test_a_constant_changed_for_one_environment_deploys_its_users_there_only(
    tmp_path: Path,
) -> None:
    repo = _constant_repo(tmp_path)
    users = sorted(
        p.parent.parent.name
        for p in (repo.root / "folders").rglob("jobs/*.json")
        if "@{node.batch}" in p.read_text("utf-8")
    )
    define_constant(repo, "node.batch", Selector("NODEID"), {"prod": "PP77_BATCH_NEW"})
    commit_all(repo.root, "feat: new prod node")

    prod = build_package(repo.root, "main", "feature/x", env="prod", today=TODAY)
    uat = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    assert sorted(_reasons(prod)) == sorted(set(users)) and users
    assert all(r == ("constant node.batch changed for prod",) for r in _reasons(prod).values())
    assert b"PP77_BATCH_NEW" in (prod.xml or b"")
    assert uat.folders == ()


def test_a_constant_without_a_value_blocks_the_package(tmp_path: Path) -> None:
    repo = _constant_repo(tmp_path)
    env = repo.root / "envs/prod/env.json"
    text = env.read_text("utf-8").replace('"PP77_BATCH"', "null")
    env.write_text(text, encoding="utf-8", newline="\n")
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"NODEID": "@{node.batch}"}))
    commit_all(repo.root, "feat: prod node unknown")

    with pytest.raises(UnresolvedConstant, match=r"node\.batch"):
        build_package(repo.root, "main", "feature/x", env="prod", today=TODAY)


def test_only_the_selected_commits_are_packaged(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    commit_all(repo.root, "feat: describe P77_C")
    apply(repo, set_attributes(repo, f"{ING}/P77_INGEST_LOAD", {"DESCRIPTION": "Ingest"}))
    ingest = commit_all(repo.root, "feat: describe the load")

    package = build_package(
        repo.root, "main", "feature/x", env="uat", commits=[ingest], today=TODAY
    )

    assert _reasons(package) == {ING: ("job P77_INGEST_LOAD modified",)}
    assert package.selected == (ingest,) and len(package.commits) == 2
    assert package.filename == f"deploy_uat_feature-x_1-of-2_{TODAY}.xml"


def test_renamed_and_removed_folders_are_warnings(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, rename_folder(repo, C, "P77_FLOW"))
    commit_all(repo.root, "refactor: rename the chain folder")
    shutil.rmtree(repo.root / "folders" / ING)
    commit_all(repo.root, "chore: drop the ingest folder")

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    reasons = _reasons(package)
    assert list(reasons) == ["P77_FLOW"]  # the ingest folder is gone: nothing to import
    assert reasons["P77_FLOW"][0] == "folder renamed from P77_CHAIN"
    assert "condition P77_CHAIN-P77_NEXT_OK renamed to P77_FLOW-P77_NEXT_OK" in reasons["P77_FLOW"]
    assert any("P77_CHAIN" in w and "delete it in Control-M" in w for w in package.warnings)
    assert any(ING in w and "removed" in w for w in package.warnings)


def test_new_validation_findings_are_reported(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    commit_all(repo.root, "feat: describe P77_C")
    before = len(build_package(repo.root, "main", "feature/x", env="uat", today=TODAY).findings)
    apply(repo, link_nodes(repo, f"{C}/P77_E", producer=f"{C}/P77_C"))
    job = repo.root / "folders" / C / "jobs" / "P77_C.json"
    text = job.read_text("utf-8").replace('"SIGN": "+"', '"SIGN": "-"')
    job.write_text(text, encoding="utf-8", newline="\n")
    commit_all(repo.root, "feat: a link nobody produces")

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    assert before == 0 and package.findings
    assert all(f.severity in ("error", "warning", "info") for f in package.findings)


def test_the_base_moving_on_in_a_packaged_folder_is_a_warning(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    commit_all(repo.root, "feat: describe P77_C")
    git(repo.root, "checkout", "-q", "main")
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "on main"}))
    commit_all(repo.root, "fix: on main")
    git(repo.root, "checkout", "-q", "feature/x")

    package = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY)

    (warning,) = package.warnings
    assert "P77_CHAIN" in warning and "main" in warning and "undo" in warning


def test_the_working_tree_can_be_packaged_with_a_warning(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "draft"}))

    package = build_package(repo.root, "main", WORKTREE, env="uat", today=TODAY)

    assert set(_reasons(package)) == {C}
    assert any("uncommitted" in w for w in package.warnings)
    assert package.filename == f"deploy_uat_worktree_{TODAY}.xml"


def test_package_json_has_no_xml_but_its_size(tmp_path: Path) -> None:
    repo = _feature(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    commit_all(repo.root, "feat: describe P77_C")

    data = build_package(repo.root, "main", "feature/x", env="uat", today=TODAY).to_json()

    assert "xml" not in data and data["size"] > 0 and data["env"] == "uat"
    assert data["folders"] == [{"name": C, "jobs": 7, "reasons": ["job P77_C modified"]}]
    assert data["head"]["name"] == "feature/x" and data["selected"] is None
