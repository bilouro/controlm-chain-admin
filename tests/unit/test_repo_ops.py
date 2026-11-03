"""Chain repository on disk: init, import an export to JSON, export it back, idempotency."""

from __future__ import annotations

import codecs
import json
from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import DuplicateName, NotAChainRepo, RepoExists, UnsafeName
from controlm_chain_admin.core.ops import export_xml, import_xml, job_ids
from controlm_chain_admin.core.repo import DEFAULT_VOLATILE_ATTRIBUTES, init_repo, load_repo
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.rawxml import filter_applications
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"
ENVS = ("test", "uat", "bench", "prod")
FOLDER = "folders/UP77_INGEST_DAILY"


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` (relative path -> bytes), for idempotency comparisons."""
    files = (p for p in sorted(root.rglob("*")) if p.is_file())
    return {str(p.relative_to(root)): p.read_bytes() for p in files}


def _read(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# ---------------------------------------------------------------- init / load


def test_init_writes_chain_json_and_one_env_file_per_environment(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)

    chain = _read(tmp_path / "chain.json")
    assert chain["application"] == APP
    assert chain["environments"] == list(ENVS)
    assert "JOBISN" in chain["volatile_attributes"]
    for env in ENVS:
        assert (tmp_path / "envs" / env / "env.json").is_file()
    assert repo.config.application == APP


def test_init_refuses_to_overwrite_an_existing_repo(tmp_path: Path) -> None:
    init_repo(tmp_path, APP, ENVS)

    with pytest.raises(RepoExists):
        init_repo(tmp_path, APP, ENVS)


def test_load_requires_chain_json(tmp_path: Path) -> None:
    with pytest.raises(NotAChainRepo):
        load_repo(tmp_path)


def test_load_reads_back_what_init_wrote(tmp_path: Path) -> None:
    init_repo(tmp_path, APP, ENVS)

    repo = load_repo(tmp_path)

    assert repo.config.application == APP
    assert repo.config.environments == ENVS


# ---------------------------------------------------------------- import


def test_import_writes_one_dir_per_folder_and_one_file_per_job(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)

    report = import_xml(repo, SAMPLE_EXPORT)

    assert report.folders == ("UP77_INGEST_DAILY",)
    assert report.jobs == 2
    assert [(s.folder, s.application) for s in report.skipped] == [
        ("UOTH_HOUSEKEEPING", "OTHER_APP")
    ]
    assert (tmp_path / FOLDER / "folder.json").is_file()
    assert (tmp_path / FOLDER / "jobs/UP77_INGEST_INIT.json").is_file()
    assert (tmp_path / FOLDER / "jobs/UP77_INGEST_LOAD.json").is_file()
    assert not (tmp_path / "folders/UOTH_HOUSEKEEPING").exists()


def test_import_separates_volatile_metadata_into_the_sidecar(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, SAMPLE_EXPORT)

    folder = _read(tmp_path / FOLDER / "folder.json")
    job = _read(tmp_path / FOLDER / "jobs/UP77_INGEST_LOAD.json")
    meta = _read(tmp_path / "meta/folders/UP77_INGEST_DAILY.json")

    assert "JOBISN" not in folder and "JOBISN" not in job
    assert folder["jobs"] == ["UP77_INGEST_INIT", "UP77_INGEST_LOAD"]
    assert folder["FOLDER_NAME"] == "UP77_INGEST_DAILY"
    assert job["CMDLINE"] == "/opt/p77/bin/load.ksh -d %%ODATE"
    assert meta == {
        "attrs": {"JOBISN": "1"},
        "jobs": {"UP77_INGEST_INIT": {"JOBISN": "2"}, "UP77_INGEST_LOAD": {"JOBISN": "3"}},
    }


def test_import_records_orders_and_export_header(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, SAMPLE_EXPORT)

    chain = _read(tmp_path / "chain.json")
    export_meta = _read(tmp_path / "meta/export.json")

    assert chain["attribute_order"]["INCOND"] == ["NAME", "ODATE", "AND_OR"]
    assert chain["child_order"]["SMART_FOLDER"] == ["JOB", "VARIABLE", "INCOND", "OUTCOND"]
    assert export_meta["prolog_comments"] == ["Exported at 01-01-2026 00:00:00"]
    assert export_meta["folder_order"] == ["UP77_INGEST_DAILY"]


def test_duplicate_job_names_in_a_folder_get_numbered_file_names() -> None:
    assert job_ids(["A", "B", "A", "A"]) == ["A", "B", "A~2", "A~3"]


def test_import_keeps_jobs_with_the_same_name_as_distinct_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    data = SAMPLE_EXPORT.replace(b'JOBNAME="UP77_INGEST_LOAD"', b'JOBNAME="UP77_INGEST_INIT"')

    report = import_xml(repo, data)

    assert report.duplicate_job_names == ("UP77_INGEST_DAILY/UP77_INGEST_INIT",)
    assert (tmp_path / FOLDER / "jobs/UP77_INGEST_INIT.json").is_file()
    assert (tmp_path / FOLDER / "jobs/UP77_INGEST_INIT~2.json").is_file()
    assert _read(tmp_path / FOLDER / "folder.json")["jobs"] == [
        "UP77_INGEST_INIT",
        "UP77_INGEST_INIT~2",
    ]
    assert export_xml(repo) == filter_applications(data, {APP})


def test_import_rejects_a_folder_name_repeated_in_the_export(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    data = SAMPLE_EXPORT.replace(b'APPLICATION="OTHER_APP"', f'APPLICATION="{APP}"'.encode())
    data = data.replace(b'FOLDER_NAME="UOTH_HOUSEKEEPING"', b'FOLDER_NAME="UP77_INGEST_DAILY"')

    with pytest.raises(DuplicateName):
        import_xml(repo, data)


def test_import_rejects_names_that_are_not_safe_path_components(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    data = SAMPLE_EXPORT.replace(b'FOLDER_NAME="UP77_INGEST_DAILY"', b'FOLDER_NAME="../UP77"')

    with pytest.raises(UnsafeName):
        import_xml(repo, data)


# ---------------------------------------------------------------- export / idempotency


def test_export_reproduces_the_original_filtered_to_the_application(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, SAMPLE_EXPORT)

    assert export_xml(repo) == filter_applications(SAMPLE_EXPORT, {APP})


def test_reimporting_the_export_changes_no_file(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, SAMPLE_EXPORT)
    before = snapshot(tmp_path)

    import_xml(repo, export_xml(repo))

    assert snapshot(tmp_path) == before


def test_reimport_removes_jobs_that_disappeared_from_the_export(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, SAMPLE_EXPORT)
    stale = tmp_path / FOLDER / "jobs/UP77_OLD.json"
    stale.write_text("{}", encoding="utf-8")

    import_xml(repo, SAMPLE_EXPORT)

    assert not stale.exists()


# ---------------------------------------------------------------- partial exports


def test_windows_line_endings_survive_import_and_export(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, SAMPLE_EXPORT.replace(b"\n", b"\r\n"))

    assert _read(tmp_path / "meta/export.json")["newline"] == "\r\n"
    assert export_xml(repo) == filter_applications(SAMPLE_EXPORT, {APP}).replace(b"\n", b"\r\n")


def test_a_byte_order_mark_survives_import_and_export(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, codecs.BOM_UTF8 + SAMPLE_EXPORT)

    assert _read(tmp_path / "meta/export.json")["bom"] is True
    assert export_xml(repo) == codecs.BOM_UTF8 + filter_applications(SAMPLE_EXPORT, {APP})


def _calendar(first: bytes, second: bytes) -> bytes:
    """The sample with one calendar attribute on each of two jobs: no job has both."""
    return SAMPLE_EXPORT.replace(
        b'CMDLINE="/opt/p77/bin/init.ksh', first + b' CMDLINE="/opt/p77/bin/init.ksh'
    ).replace(b'CMDLINE="/opt/p77/bin/load.ksh', second + b' CMDLINE="/opt/p77/bin/load.ksh')


def test_attributes_never_in_one_job_take_either_order_in_a_later_export(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, _calendar(b'WEEKDAYS="1"', b'DAYS="ALL"'))
    later = _calendar(b'DAYS="ALL"', b'WEEKDAYS="1"')  # alone, it would put DAYS first

    import_xml(repo, later)

    assert export_xml(repo) == filter_applications(later, {APP})


@pytest.mark.parametrize(
    ("written", "node"),
    [
        (b'TASKTYPE="Command" RUN_AS="aup77proc" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/init',
         "UP77_INGEST_INIT"),
        (b'RUN_AS="aup77proc" CREATED_BY="user01" TASKTYPE="SMART Table" FOLDER_NAME="UP77_INGEST',
         None),
    ],
    ids=["job", "folder"],
)  # fmt: skip
def test_an_element_written_another_way_is_exported_as_it_came(
    tmp_path: Path, written: bytes, node: str | None
) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, SAMPLE_EXPORT)
    canonical = written.replace(
        b'TASKTYPE="Command" RUN_AS="aup77proc"', b'RUN_AS="aup77proc" TASKTYPE="Command"'
    ).replace(b'RUN_AS="aup77proc" CREATED_BY="user01"', b'CREATED_BY="user01" RUN_AS="aup77proc"')
    assert canonical in SAMPLE_EXPORT
    later = SAMPLE_EXPORT.replace(canonical, written)  # another client, another order

    import_xml(repo, later)

    assert export_xml(repo) == filter_applications(later, {APP})
    meta = _read(tmp_path / "meta/folders/UP77_INGEST_DAILY.json")
    own = meta["jobs"][node] if node else meta["attrs"]
    assert "@order" in own
    others = [m for j, m in meta["jobs"].items() if j != node]
    assert all("@order" not in m for m in others), "only the element written another way"


def test_a_partial_export_keeps_the_header_of_the_full_one(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)
    import_xml(repo, SAMPLE_EXPORT)
    later = ANOMALY_EXPORT.replace(b"02-01-2026", b"14-07-2026").replace(b"\n", b"\r\n")

    import_xml(repo, later)  # one folder only: an EGMA delivery

    meta = _read(tmp_path / "meta/export.json")
    assert meta["prolog_comments"] == ["Exported at 01-01-2026 00:00:00"]
    assert meta.get("newline", "\n") == "\n"
    assert meta["folder_order"] == ["UP77_INGEST_DAILY", "UP77_CHAIN"]

    full = export_xml(repo).replace(b"01-01-2026", b"20-07-2026")
    import_xml(repo, full)  # every folder: a full export sets the header again

    assert _read(tmp_path / "meta/export.json")["prolog_comments"] == [
        "Exported at 20-07-2026 00:00:00"
    ]


def test_jobs_in_group_is_volatile_by_default() -> None:
    assert "JOBS_IN_GROUP" in DEFAULT_VOLATILE_ATTRIBUTES
