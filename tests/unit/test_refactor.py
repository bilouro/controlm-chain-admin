"""Refactorings: change-set preview computed in a sandbox, applied atomically."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import ChangeConflict, DuplicateName, ModelError, UnsafeName
from controlm_chain_admin.core.graph import folder_graph
from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.refactor import (
    apply,
    extract_variable,
    insert_job,
    move_job,
    rename_folder,
    rename_in_condition,
    rename_job,
    rename_subapp,
)
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from controlm_chain_admin.core.validate import validate
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT
from tests.unit.test_repo_ops import snapshot

APP = "P77_RISK_ENGINE"
PREFIXES = ("P77", "RQ_", "RC_")
CHAIN = "folders/P77_CHAIN"


def _repo(tmp_path: Path, *exports: bytes) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=PREFIXES)
    for data in exports or (ANOMALY_EXPORT,):
        import_xml(repo, data, env="uat")
    return repo


def _read(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]


def _names(tmp_path: Path, folder: str = "P77_CHAIN") -> dict[str, str]:
    data = _read(tmp_path / "folders" / folder / "links.json")["links"]
    return {k: v["name"] for k, v in data.items()}


# ---------------------------------------------------------------- condition names


@pytest.mark.parametrize(
    ("name", "old", "new", "expected"),
    [
        ("P77_A-P77_B_OK", "P77_B", "P77_BETA", "P77_A-P77_BETA_OK"),
        ("P77_A-P77_B_OK", "P77_A", "P77_ALPHA", "P77_ALPHA-P77_B_OK"),
        ("P77_A-TO-P77_B", "P77_B", "P77_X", "P77_A-TO-P77_X"),
        ("P77_A-P77_B_Ok-U26", "P77_B", "P77_X", "P77_A-P77_X_Ok-U26"),
        ("P77_A-P77_BB_OK", "P77_B", "P77_X", "P77_A-P77_BB_OK"),  # another job: untouched
        ("P77_A_P77_B_OK", "P77_B", "P77_X", "P77_A_P77_B_OK"),  # not dash-separated: untouched
    ],
)
def test_rename_in_condition(name: str, old: str, new: str, expected: str) -> None:
    assert rename_in_condition(name, old, new) == expected


# ---------------------------------------------------------------- rename-job


def test_rename_job_preview_writes_nothing_and_lists_the_file_edits(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = snapshot(tmp_path)

    change = rename_job(repo, "P77_CHAIN/P77_B", "P77_BETA")

    assert snapshot(tmp_path) == before
    kinds = {edit.path: edit.kind for edit in change.edits}
    assert kinds == {
        f"{CHAIN}/jobs/P77_B.json": "delete",
        f"{CHAIN}/jobs/P77_BETA.json": "create",
        f"{CHAIN}/folder.json": "modify",
        f"{CHAIN}/links.json": "modify",
        "meta/folders/P77_CHAIN.json": "modify",
    }
    assert "P77_B" in change.summary and "P77_BETA" in change.summary
    assert "+++ b/folders/P77_CHAIN/jobs/P77_BETA.json" in change.diff()


def test_rename_job_apply_renames_the_job_and_the_conditions_that_embed_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = apply(repo, rename_job(repo, "P77_CHAIN/P77_B", "P77_BETA"))

    assert result.written == 4 and result.deleted == 1
    assert _read(tmp_path / CHAIN / "folder.json")["jobs"][1] == "P77_BETA"
    names = _names(tmp_path)
    assert names["P77_A-P77_B_OK"] == "P77_A-P77_BETA_OK"
    assert names["P77_B-P77_C_OK"] == "P77_BETA-P77_C_OK"
    out = export_xml(repo, env="uat")
    assert b'JOBNAME="UP77_BETA"' in out and b'MEMNAME="UP77_B"' in out  # MEMNAME kept
    assert b'NAME="UP77_A-UP77_BETA_OK"' in out and b"UP77_A-UP77_B_OK" not in out
    assert (tmp_path / CHAIN / "index.json").is_file()  # derived view rebuilt
    assert {f.code for f in validate(repo).findings if f.code == "stale-name"} == {"stale-name"}


def test_rename_job_options_keep_names_and_with_memname(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    apply(
        repo,
        rename_job(repo, "P77_CHAIN/P77_B", "P77_BETA", update_names=False, with_memname=True),
    )

    assert _names(tmp_path)["P77_A-P77_B_OK"] == "P77_A-P77_B_OK"
    job = _read(tmp_path / CHAIN / "jobs/P77_BETA.json")
    assert job["JOBNAME"] == "P77_BETA" and job["MEMNAME"] == "P77_BETA"


def test_rename_job_errors_and_warnings(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(ModelError):
        rename_job(repo, "P77_CHAIN/NOPE", "P77_X")
    with pytest.raises(DuplicateName):
        rename_job(repo, "P77_CHAIN/P77_B", "P77_C")
    with pytest.raises(UnsafeName):
        rename_job(repo, "P77_CHAIN/P77_B", "../evil")
    change = rename_job(repo, "P77_CHAIN/P77_B", "UP77_LETTERED")
    assert any("environment letter" in w for w in change.warnings)


# ---------------------------------------------------------------- rename-folder


def test_rename_folder_moves_files_and_updates_parent_folder_order_and_names(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)

    apply(repo, rename_folder(repo, "P77_CHAIN", "P77_FLOW"))

    assert not (tmp_path / CHAIN).exists()
    folder = _read(tmp_path / "folders/P77_FLOW/folder.json")
    assert folder["FOLDER_NAME"] == "P77_FLOW" and folder["JOBNAME"] == "P77_FLOW"
    assert _read(tmp_path / "folders/P77_FLOW/jobs/P77_A.json")["PARENT_FOLDER"] == "P77_FLOW"
    assert (tmp_path / "meta/folders/P77_FLOW.json").is_file()
    assert _read(tmp_path / "meta/export.json")["folder_order"] == ["P77_FLOW"]
    names = _names(tmp_path, "P77_FLOW")
    assert names["P77_OTHER-P77_CHAIN_OK"] == "P77_OTHER-P77_FLOW_OK"
    assert names["P77_CHAIN-P77_NEXT_OK"] == "P77_FLOW-P77_NEXT_OK"
    out = export_xml(repo, env="uat")
    assert out.count(b'PARENT_FOLDER="UP77_FLOW"') == 7 and b"UP77_CHAIN" not in out


def test_rename_folder_to_an_existing_folder_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ANOMALY_EXPORT, SAMPLE_EXPORT)

    with pytest.raises(DuplicateName):
        rename_folder(repo, "P77_CHAIN", "P77_INGEST_DAILY")


# ---------------------------------------------------------------- rename-subapp


def test_rename_subapp_in_one_folder_only(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ANOMALY_EXPORT, SAMPLE_EXPORT)

    change = rename_subapp(repo, "P77_BATCH", "P77_CORE", folder="P77_CHAIN")
    apply(repo, change)

    assert len(change.edits) == 8  # folder.json + 7 job files
    out = export_xml(repo, env="uat")
    assert out.count(b'SUB_APPLICATION="UP77_CORE"') == 8
    assert out.count(b'SUB_APPLICATION="UP77_BATCH"') == 3  # P77_INGEST_DAILY untouched


def test_rename_subapp_everywhere_and_nothing_to_do(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ANOMALY_EXPORT, SAMPLE_EXPORT)

    assert len(rename_subapp(repo, "P77_BATCH", "P77_CORE").edits) == 11
    assert rename_subapp(repo, "P77_NOPE", "P77_CORE").edits == ()


# ---------------------------------------------------------------- move-job


def test_move_job_to_another_folder(tmp_path: Path) -> None:
    repo = _repo(tmp_path, SAMPLE_EXPORT, ANOMALY_EXPORT)

    apply(repo, move_job(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD", "P77_CHAIN"))

    assert not (tmp_path / "folders/P77_INGEST_DAILY/jobs/P77_INGEST_LOAD.json").exists()
    moved = _read(tmp_path / CHAIN / "jobs/P77_INGEST_LOAD.json")
    assert moved["PARENT_FOLDER"] == "P77_CHAIN"
    assert _read(tmp_path / CHAIN / "folder.json")["jobs"][-1] == "P77_INGEST_LOAD"
    assert _read(tmp_path / "meta/folders/P77_CHAIN.json")["jobs"]["P77_INGEST_LOAD"] == {
        "JOBISN": "3"
    }
    assert "P77_INGEST_LOAD" not in _read(tmp_path / "meta/folders/P77_INGEST_DAILY.json")["jobs"]
    assert "P77_INGEST_INIT-P77_INGEST_LOAD_OK" in _names(tmp_path)  # home follows the consumer
    link = load_links(repo)["P77_INGEST_INIT-P77_INGEST_LOAD_OK"]
    assert [str(n) for n in link.consumers] == ["P77_CHAIN/P77_INGEST_LOAD"]


def test_move_job_refuses_a_name_already_in_the_target(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ANOMALY_EXPORT, ANOMALY_EXPORT.replace(b"UP77_CHAIN", b"UP77_CHAIN2"))

    with pytest.raises(DuplicateName):
        move_job(repo, "P77_CHAIN/P77_A", "P77_CHAIN2")


# ---------------------------------------------------------------- insert-job


def test_insert_job_relinks_the_chain_around_the_new_job(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    change = insert_job(
        repo,
        "P77_CHAIN/P77_NEW",
        after="P77_CHAIN/P77_A",
        before="P77_CHAIN/P77_B",
        like="P77_CHAIN/P77_B",
    )
    apply(repo, change)

    new = _read(tmp_path / CHAIN / "jobs/P77_NEW.json")
    assert new["JOBNAME"] == "P77_NEW" and new["MEMNAME"] == "P77_NEW"
    assert new["INCOND"] == [{"link": "P77_A-P77_B_OK", "ODATE": "ODAT", "AND_OR": "A"}]
    assert new["OUTCOND"] == [
        {"link": "P77_A-P77_B_OK", "ODATE": "ODAT", "SIGN": "-"},
        {"link": "P77_NEW-P77_B_OK", "ODATE": "ODAT", "SIGN": "+"},
    ]
    assert "ON" not in new  # the cloned ON block only held a DOCOND of the original job
    b = _read(tmp_path / CHAIN / "jobs/P77_B.json")
    assert b["INCOND"][0]["link"] == "P77_NEW-P77_B_OK"
    assert {"link": "P77_NEW-P77_B_OK", "ODATE": "ODAT", "SIGN": "-"} in b["OUTCOND"]
    assert _read(tmp_path / CHAIN / "folder.json")["jobs"][:3] == ["P77_A", "P77_NEW", "P77_B"]
    names = _names(tmp_path)
    assert (
        names["P77_A-P77_B_OK"] == "P77_A-P77_NEW_OK"
        and names["P77_NEW-P77_B_OK"] == "P77_NEW-P77_B_OK"
    )
    edges = {(e.source, e.target) for e in folder_graph(repo, "P77_CHAIN").edges}
    assert ("P77_CHAIN/P77_A", "P77_CHAIN/P77_NEW") in edges
    assert ("P77_CHAIN/P77_NEW", "P77_CHAIN/P77_B") in edges
    assert ("P77_CHAIN/P77_A", "P77_CHAIN/P77_B") not in edges
    assert any("JOBISN" in w for w in change.warnings)
    assert b'NAME="UP77_NEW-UP77_B_OK"' in export_xml(repo, env="uat")


def test_insert_job_without_template_creates_a_minimal_dummy(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    apply(
        repo,
        insert_job(repo, "P77_CHAIN/P77_GATE", after="P77_CHAIN/P77_B", before="P77_CHAIN/P77_C"),
    )

    gate = _read(tmp_path / CHAIN / "jobs/P77_GATE.json")
    assert gate["TASKTYPE"] == "Dummy" and gate["APPLICATION"] == APP
    assert gate["SUB_APPLICATION"] == "P77_BATCH" and gate["PARENT_FOLDER"] == "P77_CHAIN"


def test_insert_job_needs_exactly_one_link_between_the_two_jobs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(ModelError, match="no link"):
        insert_job(repo, "P77_CHAIN/P77_X", after="P77_CHAIN/P77_A", before="P77_CHAIN/P77_D")


# ---------------------------------------------------------------- extract-variable


def test_extract_variable_from_one_job(tmp_path: Path) -> None:
    repo = _repo(tmp_path, SAMPLE_EXPORT)

    apply(
        repo,
        extract_variable(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD", "/opt/p77/bin", "%%BINDIR"),
    )

    job = _read(tmp_path / "folders/P77_INGEST_DAILY/jobs/P77_INGEST_LOAD.json")
    assert job["CMDLINE"] == "%%BINDIR/load.ksh -d %%ODATE"
    assert job["VARIABLE"] == [{"NAME": "%%BINDIR", "VALUE": "/opt/p77/bin"}]
    assert list(job).index("VARIABLE") < list(job).index("INCOND")
    out = export_xml(repo, env="uat")
    assert b'<VARIABLE NAME="%%BINDIR" VALUE="/opt/p77/bin" />' in out


def test_extract_variable_over_a_folder_and_its_errors(tmp_path: Path) -> None:
    repo = _repo(tmp_path, SAMPLE_EXPORT)

    change = extract_variable(repo, "P77_INGEST_DAILY/", "/opt/p77/bin", "%%BINDIR")
    assert {edit.path for edit in change.edits} == {
        "chain.json",  # VARIABLE was never seen under JOB here: the canonical order grows
        "folders/P77_INGEST_DAILY/jobs/P77_INGEST_INIT.json",
        "folders/P77_INGEST_DAILY/jobs/P77_INGEST_LOAD.json",
    }

    with pytest.raises(ModelError, match="%%"):
        extract_variable(repo, "P77_INGEST_DAILY/", "/opt/p77/bin", "BINDIR")
    with pytest.raises(ModelError, match="not found"):
        extract_variable(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD", "/nowhere", "%%X")


# ---------------------------------------------------------------- apply safety


def test_apply_refuses_when_a_file_changed_since_the_preview(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    change = rename_job(repo, "P77_CHAIN/P77_B", "P77_BETA")
    (tmp_path / CHAIN / "folder.json").write_text("{}\n", encoding="utf-8")
    before = snapshot(tmp_path)

    with pytest.raises(ChangeConflict, match=r"folder\.json"):
        apply(repo, change)
    assert snapshot(tmp_path) == before


def test_apply_survives_an_empty_directory_the_system_does_not_let_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A synchronised folder (or a scanner) can hold an empty directory: the change is
    written whole all the same, and what can be removed still is."""
    repo = _repo(tmp_path)
    held, free = tmp_path / "folders" / "P77_HELD", tmp_path / "folders" / "P77_FREE"
    held.mkdir()
    free.mkdir()
    rmdir = Path.rmdir

    def guarded(self: Path) -> None:
        if self.name == "P77_HELD":
            raise PermissionError(13, "Access is denied", str(self))
        rmdir(self)

    monkeypatch.setattr(Path, "rmdir", guarded)

    result = apply(repo, rename_job(repo, "P77_CHAIN/P77_B", "P77_BETA"))

    assert result.written == 4 and result.deleted == 1
    assert _names(tmp_path)["P77_A-P77_B_OK"] == "P77_A-P77_BETA_OK"  # the links were rebuilt
    assert held.is_dir() and not free.exists()


def test_change_set_json_shape(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    data = rename_job(repo, "P77_CHAIN/P77_B", "P77_BETA").to_json()

    assert set(data) == {"summary", "warnings", "files"}
    assert {"path": f"{CHAIN}/jobs/P77_BETA.json", "change": "create"} in data["files"]


def test_renamed_conditions_never_take_a_name_another_link_uses(tmp_path: Path) -> None:
    from controlm_chain_admin.core.refactor import apply as apply_change
    from controlm_chain_admin.core.refactor import insert_job as insert
    from tests.support.gitrepo import chain_git_repo

    repo = chain_git_repo(tmp_path)
    chain = "P77_CHAIN"
    apply_change(repo, insert(repo, f"{chain}/P77_INGEST_INIT", after=f"{chain}/P77_A",
                              before=f"{chain}/P77_B"))  # fmt: skip
    # INIT -> B would follow the downstream job and become INIT-LOAD_OK: the ingest folder's
    change = insert(
        repo, f"{chain}/P77_INGEST_LOAD", after=f"{chain}/P77_INGEST_INIT", before=f"{chain}/P77_B"
    )
    apply_change(repo, change)

    names = [link.name for link in load_links(repo).values()]
    assert len(names) == len(set(names)), sorted(names)
    assert any("already used by link" in w for w in change.warnings), change.warnings
