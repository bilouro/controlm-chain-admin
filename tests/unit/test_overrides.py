"""Exceptions: whole values one environment uses for one job or folder, applied at export."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.errors import InvalidChange, ModelError, UnknownEnvironment
from controlm_chain_admin.core.ops import export_document, import_xml
from controlm_chain_admin.core.overrides import Override, load_overrides, write_overrides
from controlm_chain_admin.core.package import build_package
from controlm_chain_admin.core.refactor import (
    apply,
    rename_constant,
    run_operation,
    set_exception,
)
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.gitrepo import chain_git_repo, commit_all, git

C = "P77_CHAIN"
ING = "P77_INGEST_DAILY"
TODAY = "2026-11-02"


def _job(xml: bytes, jobname: str) -> dict[str, str]:
    for folder in parse_xml(xml).root.elements():
        for job in folder.elements():
            if job.tag == "JOB" and job.get("JOBNAME") == jobname:
                return dict(job.attrs)
    raise AssertionError(jobname)


def _folder_variables(xml: bytes, folder_name: str) -> dict[str, str]:
    for folder in parse_xml(xml).root.elements():
        if folder.get("FOLDER_NAME") == folder_name:
            return {
                str(v.get("NAME")): str(v.get("VALUE"))
                for v in folder.elements()
                if v.tag == "VARIABLE"
            }
    raise AssertionError(folder_name)


def test_an_exception_changes_one_job_in_one_environment_only(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    write_overrides(
        repo,
        "prod",
        {f"{C}/P77_E": Override(attributes={"TASKTYPE": "Dummy", "CMDLINE": None})},
    )

    prod, _ = export_document(repo, "prod")
    uat, _ = export_document(repo, "uat")

    assert _job(prod, "PP77_E")["TASKTYPE"] == "Dummy" and "CMDLINE" not in _job(prod, "PP77_E")
    assert _job(prod, "PP77_D")["TASKTYPE"] == "Command"
    assert _job(uat, "UP77_E")["TASKTYPE"] == "Command"
    assert list(_job(prod, "PP77_E"))[:6] == list(_job(uat, "UP77_E"))[:6]  # order kept


def test_an_exception_sets_variables_of_a_folder(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    write_overrides(repo, "prod", {f"{ING}/": Override(variables={"%%GEIENV": "x", "%%NEW": "1"})})

    prod, _ = export_document(repo, "prod")

    assert _folder_variables(prod, "PP77_INGEST_DAILY") == {"%%GEIENV": "x", "%%NEW": "1"}
    assert _folder_variables(export_document(repo, "uat")[0], "UP77_INGEST_DAILY") == {
        "%%GEIENV": "u"
    }


def test_overrides_are_read_back_and_checked(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    assert load_overrides(repo, "prod") == {}
    write_overrides(repo, "prod", {f"{C}/P77_E": Override(attributes={"MAXWAIT": "3"})})

    assert load_overrides(repo, "prod") == {f"{C}/P77_E": Override(attributes={"MAXWAIT": "3"})}
    assert (repo.root / "envs/prod/overrides.json").is_file()

    (repo.root / "envs/prod/overrides.json").write_text('{"X/Y": {"set": 3}}', encoding="utf-8")
    with pytest.raises(ModelError, match=r"overrides\.json"):
        load_overrides(repo, "prod")


def test_a_changed_exception_puts_its_folder_in_that_environment_package(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "switch", "-q", "-c", "release/march")
    write_overrides(repo, "prod", {f"{C}/P77_E": Override(attributes={"TASKTYPE": "Dummy"})})
    commit_all(repo.root, "feat: P77_E does nothing in prod")

    prod = build_package(repo.root, "main", "release/march", env="prod", today=TODAY)
    uat = build_package(repo.root, "main", "release/march", env="uat", today=TODAY)

    assert [(f.name, f.reasons) for f in prod.folders] == [
        (C, ("exception for prod changed: P77_E",))
    ]
    assert uat.folders == ()


# ---------------------------------------------------------------- set-exception


def test_set_exception_is_a_previewed_change(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)

    change = run_operation(
        repo,
        "set-exception",
        {"env": "prod", "node": f"{C}/P77_E", "attributes": {"TASKTYPE": "Dummy"}},
    )

    assert change.summary == f"exception for prod on {C}/P77_E: TASKTYPE=Dummy"
    assert [(e.path, e.kind) for e in change.edits] == [("envs/prod/overrides.json", "create")]
    apply(repo, change)
    assert load_overrides(repo, "prod") == {
        f"{C}/P77_E": Override(attributes={"TASKTYPE": "Dummy"})
    }

    apply(repo, run_operation(repo, "set-exception", {
        "env": "prod", "node": f"{C}/P77_E", "variables": {"%%X": "1"}, "drop": ["TASKTYPE"],
    }))  # fmt: skip
    assert load_overrides(repo, "prod") == {f"{C}/P77_E": Override(variables={"%%X": "1"})}
    apply(repo, run_operation(repo, "set-exception", {
        "env": "prod", "node": f"{C}/P77_E", "drop": ["%%X"],
    }))  # fmt: skip
    assert load_overrides(repo, "prod") == {}


def test_set_exception_checks_its_target(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)

    with pytest.raises(UnknownEnvironment):
        set_exception(repo, "bench", f"{C}/P77_E", {"TASKTYPE": "Dummy"})
    with pytest.raises(ModelError, match="unknown job"):
        set_exception(repo, "prod", f"{C}/NOPE", {"TASKTYPE": "Dummy"})
    with pytest.raises(InvalidChange, match="nothing"):
        set_exception(repo, "prod", f"{C}/P77_E")
    with pytest.raises(InvalidChange, match="JOBNAME"):
        set_exception(repo, "prod", f"{C}/P77_E", {"JOBNAME": "X"})


# ---------------------------------------------------------------- rename-constant


def test_rename_constant_follows_every_use(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    define_constant(
        repo, "node.p77_batch", Selector("NODEID"), {"uat": "UP77_BATCH", "prod": "PP77_BATCH"}
    )
    import_xml(repo, ANOMALY_EXPORT, env="uat")  # the base gets @{node.p77_batch}
    write_overrides(
        repo, "prod", {f"{C}/P77_E": Override(attributes={"NODEID": "@{node.p77_batch}"})}
    )

    change = rename_constant(repo, "node.p77_batch", "node.bat1")
    apply(repo, change)

    assert change.summary.startswith("rename constant node.p77_batch -> node.bat1 (")
    text = (repo.root / "folders" / C / "jobs" / "P77_E.json").read_text(encoding="utf-8")
    assert "@{node.bat1}" in text and "node.p77_batch" not in text
    repo = load_repo(repo.root)
    assert "node.bat1" in repo.config.constants and "node.p77_batch" not in repo.config.constants
    assert repo.load_env("prod").constants["node.bat1"] == "PP77_BATCH"
    assert load_overrides(repo, "prod")[f"{C}/P77_E"].attributes == {"NODEID": "@{node.bat1}"}
    assert export_document(repo, "prod")[0].count(b'NODEID="PP77_BATCH"') > 0


def test_rename_constant_refuses_bad_names(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    define_constant(repo, "node.a", Selector("NODEID"), {"uat": "UP77_BATCH"})
    define_constant(repo, "user.b", Selector("RUN_AS"), {"uat": "aup77proc"})

    with pytest.raises(InvalidChange, match="unknown constant"):
        rename_constant(repo, "node.nope", "node.c")
    with pytest.raises(InvalidChange, match="already exists"):
        rename_constant(repo, "node.a", "user.b")
    with pytest.raises(InvalidChange, match="invalid constant name"):
        rename_constant(repo, "node.a", "Node A")
