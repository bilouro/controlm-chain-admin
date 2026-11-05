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
    promote_exception,
    rename_constant,
    run_operation,
    set_exception,
)
from controlm_chain_admin.core.repo import load_repo, read_json
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


# ---------------------------------------------------------------- lines (child elements)


def _lines(xml: bytes, jobname: str, tag: str) -> list[dict[str, str]]:
    for folder in parse_xml(xml).root.elements():
        for job in folder.elements():
            if job.tag == "JOB" and job.get("JOBNAME") == jobname:
                return [dict(c.attrs) for c in job.elements() if c.tag == tag]
    raise AssertionError(jobname)


def test_an_exception_changes_one_line_of_a_job_in_one_environment(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    write_overrides(
        repo,
        "prod",
        {
            f"{C}/P77_B": Override(
                elements={"OUTCOND[link=P77_A-P77_B_OK,ODATE=ODAT]": {"SIGN": "+"}}
            )
        },
    )

    prod, _ = export_document(repo, "prod")
    uat, _ = export_document(repo, "uat")

    assert _lines(prod, "PP77_B", "OUTCOND") == [
        {"NAME": "PP77_A-PP77_B_OK", "ODATE": "ODAT", "SIGN": "+"},
        {"NAME": "PP77_B-PP77_C_OK", "ODATE": "ODAT", "SIGN": "+"},
    ]
    assert _lines(uat, "UP77_B", "OUTCOND")[0]["SIGN"] == "-"


def test_an_exception_adds_and_removes_lines_and_reaches_inside_an_on_block(
    tmp_path: Path,
) -> None:
    repo = chain_git_repo(tmp_path)
    write_overrides(
        repo,
        "prod",
        {
            f"{C}/P77_B": Override(
                elements={
                    "INCOND[link=P77_X-P77_B_OK,ODATE=ODAT]": {
                        "AND_OR": "O",
                        "after": None,  # the first INCOND there
                    },
                    "OUTCOND[link=P77_B-P77_C_OK,ODATE=ODAT]": None,  # not in prod
                    "ON[STMT=*,CODE=NOTOK]/DOCOND[link=P77_B-P77_C_OK,ODATE=ODAT]": {"SIGN": "-"},
                    "SHOUT[WHEN=NOTOK,DEST=EM]": {
                        "URGENCY": "R",
                        "MESSAGE": "B failed",
                        "after": "SHOUT[WHEN=OK,DEST=EM]",  # unknown there: last of its tag
                    },
                }
            ),
            f"{ING}/": Override(variables={"%%GEIENV": None}),
        },
    )

    prod, _ = export_document(repo, "prod")
    uat, _ = export_document(repo, "uat")

    assert _lines(prod, "PP77_B", "INCOND") == [
        {"NAME": "PP77_X-PP77_B_OK", "ODATE": "ODAT", "AND_OR": "O"},
        {"NAME": "PP77_A-PP77_B_OK", "ODATE": "ODAT", "AND_OR": "A"},
    ]
    assert _lines(prod, "PP77_B", "OUTCOND") == [
        {"NAME": "PP77_A-PP77_B_OK", "ODATE": "ODAT", "SIGN": "-"}
    ]
    assert _lines(prod, "PP77_B", "SHOUT") == [
        {"WHEN": "NOTOK", "DEST": "EM", "URGENCY": "R", "MESSAGE": "B failed"}
    ]
    assert b'<DOCOND NAME="PP77_B-PP77_C_OK" ODATE="ODAT" SIGN="-" />' in prod
    assert _folder_variables(prod, "PP77_INGEST_DAILY") == {}
    assert len(_lines(uat, "UP77_B", "INCOND")) == 1 and len(_lines(uat, "UP77_B", "OUTCOND")) == 2
    assert _lines(uat, "UP77_B", "SHOUT") == []
    assert _folder_variables(uat, "UP77_INGEST_DAILY") == {"%%GEIENV": "u"}


def test_a_stale_exception_on_a_line_that_is_gone_is_skipped(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    write_overrides(
        repo,
        "prod",
        {
            f"{C}/P77_B": Override(
                elements={
                    "ON[STMT=*,CODE=OK]/DOCOND[link=P77_B-P77_C_OK,ODATE=ODAT]": {"SIGN": "-"}
                }
            )
        },
    )

    prod, _ = export_document(repo, "prod")

    assert b'<DOCOND NAME="PP77_B-PP77_C_OK" ODATE="ODAT" SIGN="+" />' in prod


def test_overrides_with_lines_are_read_back_and_checked(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    override = Override(
        variables={"%%X": None},
        elements={"INCOND[link=P77_X,ODATE=ODAT]": {"AND_OR": "A"}, "SHOUT[0]": None},
    )
    write_overrides(repo, "prod", {f"{C}/P77_B": override})

    assert load_overrides(repo, "prod") == {f"{C}/P77_B": override}
    text = (repo.root / "envs/prod/overrides.json").read_text(encoding="utf-8")
    assert '"elements"' in text and '"%%X": null' in text

    (repo.root / "envs/prod/overrides.json").write_text(
        '{"X/Y": {"elements": {"INCOND[NAME=A]": "yes"}}}', encoding="utf-8"
    )
    with pytest.raises(ModelError, match="elements"):
        load_overrides(repo, "prod")


def test_set_exception_takes_and_drops_lines(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    line = "OUTCOND[link=P77_A-P77_B_OK,ODATE=ODAT]"

    change = run_operation(
        repo,
        "set-exception",
        {"env": "prod", "node": f"{C}/P77_B", "elements": {line: {"SIGN": "+"}}},
    )
    apply(repo, change)

    assert change.summary == f"exception for prod on {C}/P77_B: {line}: SIGN=+"
    assert load_overrides(repo, "prod") == {f"{C}/P77_B": Override(elements={line: {"SIGN": "+"}})}
    with pytest.raises(InvalidChange, match="not a locator"):
        set_exception(repo, "prod", f"{C}/P77_B", elements={"nope": None})
    apply(repo, set_exception(repo, "prod", f"{C}/P77_B", drop=[line]))
    assert load_overrides(repo, "prod") == {}


# ---------------------------------------------------------------- promote-exception


def test_an_exception_can_be_made_the_base(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    added = "INCOND[link=P77_X-P77_B_OK,ODATE=ODAT]"
    gone = "OUTCOND[link=P77_B-P77_C_OK,ODATE=ODAT]"
    write_overrides(
        repo,
        "prod",
        {
            f"{C}/P77_B": Override(
                attributes={"TASKTYPE": "Dummy"},
                variables={"%%X": "1"},
                elements={added: {"AND_OR": "A", "after": None}, gone: None},
            )
        },
    )
    write_overrides(repo, "uat", {f"{C}/P77_B": Override(attributes={"TASKTYPE": "Dummy"})})

    change = run_operation(
        repo,
        "promote-exception",
        {"env": "prod", "node": f"{C}/P77_B", "names": ["TASKTYPE", added]},
    )
    apply(repo, change)

    assert change.summary == f"the base takes what prod has on {C}/P77_B: TASKTYPE, {added}"
    repo = load_repo(repo.root)
    job = read_json(repo.job_file(C, "P77_B"))
    assert job["TASKTYPE"] == "Dummy"
    assert [c["link"] for c in job["INCOND"]] == ["P77_X-P77_B_OK", "P77_A-P77_B_OK"]
    assert load_overrides(repo, "prod") == {
        f"{C}/P77_B": Override(variables={"%%X": "1"}, elements={gone: None})
    }
    assert load_overrides(repo, "uat") == {}  # the same value as the new base: gone
    uat, _ = export_document(repo, "uat")
    assert _job(uat, "UP77_B")["TASKTYPE"] == "Dummy"
    assert _lines(uat, "UP77_B", "INCOND")[0]["NAME"] == "UP77_X-UP77_B_OK"
    with pytest.raises(InvalidChange, match="no exception NOPE"):
        promote_exception(repo, "prod", f"{C}/P77_B", ["NOPE"])
    with pytest.raises(InvalidChange, match="nothing"):
        promote_exception(repo, "prod", f"{C}/P77_B", [])
