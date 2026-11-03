"""Full exports of an environment: what it lacks and what only it has.

The repository mirrors production. A full export of another environment brings jobs and
folders only that environment has, lacks some production has, and differs in ways that are
its own: by default none of that touches production.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.intake import Decision, analyze, receive
from controlm_chain_admin.core.membership import ENVS_KEY
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.envexports import both, fresh_repo, job, prod_export
from tests.support.gitrepo import APP
from tests.support.rawxml import filter_applications

C = "P77_CHAIN"
ING = "P77_INGEST_DAILY"
PROD = prod_export()


def _uat_full() -> bytes:
    data = re.sub(rb'\n\s*<JOB JOBISN="6".*?</JOB>', b"", both(), flags=re.S)  # no P77_E
    data = data.replace(
        b'<JOB JOBISN="7"',
        b'<JOB JOBISN="9" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" '
        b'MEMNAME="UP77_UATONLY" JOBNAME="UP77_UATONLY" RUN_AS="aup77proc" TASKTYPE="Dummy" '
        b'NODEID="UP77_BATCH" PARENT_FOLDER="UP77_CHAIN" />\n        <JOB JOBISN="7"',
    )
    data = data.replace(
        b'<INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" AND_OR="A" />',
        b'<INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" AND_OR="A" />\n'
        b'            <INCOND NAME="UP77_X-UP77_B_OK" ODATE="ODAT" AND_OR="A" />',
    )
    data = job(data, b"UP77_D", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    c = re.search(rb'\n\s*<JOB JOBISN="4".*?</JOB>', data, flags=re.S)
    assert c is not None
    data = data.replace(c[0], b"", 1)  # uat lists P77_C after P77_D
    d_end = data.index(b"</JOB>", data.index(b'<JOB JOBISN="5"')) + len(b"</JOB>")
    data = data[:d_end] + c[0] + data[d_end:]
    data = data.replace(b'<JOB JOBISN="2"', b'<JOB JOBISN="22"')  # volatile, uat's own
    return data.replace(b"Exported at 01-01-2026", b"Exported at 05-05-2026")


UAT = _uat_full()


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    return fresh_repo(tmp_path)


def _by_id(repo: ChainRepo, data: bytes, **kwargs: object) -> dict[str, Decision]:
    return {d.id: d for d in analyze(repo, data, **kwargs).decisions}  # type: ignore[arg-type]


def test_a_full_export_of_another_environment_leaves_production_alone(repo: ChainRepo) -> None:
    intake = analyze(repo, UAT)
    by_id = {d.id: d for d in intake.decisions}

    assert intake.full
    removed = by_id[f"{C}/P77_E#removed"]
    assert (removed.options, removed.default) == (("not-here", "remove", "keep"), "not-here")
    added = by_id[f"{C}/P77_UATONLY#added"]
    assert (added.kind, added.options, added.default) == (
        "added", ("only-here", "everywhere"), "only-here",
    )  # fmt: skip
    assert by_id[f"{C}/P77_D@TASKTYPE"].default == "exception"
    assert by_id[f"{C}/P77_B#children"].default == "ignore"


def test_taking_the_defaults_keeps_production_as_it_was(repo: ChainRepo) -> None:
    apply(repo, receive(repo, UAT))

    repo = load_repo(repo.root)
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})
    uat = export_xml(repo, "uat")
    assert b'JOBNAME="UP77_UATONLY"' in uat and b'JOBNAME="UP77_E"' not in uat
    assert b'JOBNAME="UP77_D" RUN_AS="aup77proc" TASKTYPE="Dummy"' in uat
    assert read_json(repo.job_file(C, "P77_UATONLY"))[ENVS_KEY] == ["uat"]
    assert read_json(repo.job_file(C, "P77_E"))[ENVS_KEY] == ["test", "bench", "prod"]
    again = analyze(repo, UAT).decisions  # what uat lacks or only has is known now
    assert not [d for d in again if d.kind in ("removed", "added")]


def test_a_folder_the_environment_does_not_have(repo: ChainRepo) -> None:
    assert not analyze(repo, ANOMALY_EXPORT).full  # one folder of two: a delivery
    absent = _by_id(repo, ANOMALY_EXPORT, full=True)[f"{ING}/#absent"]
    assert (absent.kind, absent.options, absent.default) == (
        "absent", ("not-here", "keep"), "not-here",
    )  # fmt: skip

    apply(repo, receive(repo, ANOMALY_EXPORT, full=True))

    repo = load_repo(repo.root)
    assert read_json(repo.folder_file(ING))[ENVS_KEY] == ["test", "bench", "prod"]
    assert b"UP77_INGEST_DAILY" not in export_xml(repo, "uat")
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})


def test_a_delivery_and_production_keep_their_defaults(repo: ChainRepo) -> None:
    delivery = _by_id(repo, re.sub(rb'\n\s*<JOB JOBISN="6".*?</JOB>', b"", ANOMALY_EXPORT,
                                   flags=re.S))  # fmt: skip
    assert delivery[f"{C}/P77_E#removed"].default == "remove"
    assert not [d for d in delivery.values() if d.kind in ("added", "absent")]
    prod = re.sub(rb'\n\s*<JOB JOBISN="6".*?</JOB>', b"", PROD, flags=re.S)
    prod = job(prod, b"PP77_D", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    production = _by_id(repo, prod)
    assert production[f"{C}/P77_E#removed"].default == "remove"
    assert production[f"{C}/P77_D@TASKTYPE"].default == "change"  # production is the truth


def test_a_value_only_a_job_of_the_environment_has_needs_no_value_elsewhere(
    repo: ChainRepo,
) -> None:
    apply(repo, receive(repo, UAT))
    bench = UAT.replace(b"UP77", b"BP77").replace(b"URQ_", b"BRQ_").replace(b"[UAT]", b"[BENCH]")
    bench = bench.replace(
        b'<JOB JOBISN="7"',
        b'<JOB JOBISN="10" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="BP77_BATCH" '
        b'MEMNAME="BP77_BENCHONLY" JOBNAME="BP77_BENCHONLY" RUN_AS="benchuser" '
        b'TASKTYPE="Dummy" PARENT_FOLDER="BP77_CHAIN" />\n        <JOB JOBISN="7"',
    )

    change = receive(load_repo(repo.root), bench)

    assert "user.benchuser" in change.summary or any(
        "user.benchuser" in e.path or "user.benchuser" in (e.after or "") for e in change.edits
    )
    assert not [w for w in change.warnings if "user.benchuser" in w]
    apply(repo, change)
    assert export_xml(load_repo(repo.root), "prod") == filter_applications(PROD, {APP})


def test_production_values_naming_another_environment_stay_as_they_are(tmp_path: Path) -> None:
    dirty = PROD.replace(b"[P77][PROD] Load failed", b"[P77][UAT] Load failed")  # prod says uat
    dirty = job(dirty, b"PP77_D", b'NODEID="PP77_BATCH"', b'NODEID="UP77_BATCH"')
    repo = fresh_repo(tmp_path, dirty)
    bench = (
        both().replace(b"UP77", b"BP77").replace(b"URQ_", b"BRQ_").replace(b"[UAT]", b"[BENCH]")
    )

    apply(repo, receive(repo, bench))

    assert export_xml(load_repo(repo.root), "prod") == filter_applications(dirty, {APP})
