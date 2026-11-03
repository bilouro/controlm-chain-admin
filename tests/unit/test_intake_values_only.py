"""Only the values of an environment: a full export whose jobs carry releases not installed in
production yet teaches the machines, users, mails and texts of its environment, and nothing
else enters the repository."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.intake import analyze, receive
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.overrides import load_overrides
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo, read_json
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.envexports import both, fresh_repo, job, prod_export
from tests.support.gitrepo import APP, commit_all, git
from tests.support.rawxml import filter_applications
from tests.support.samples import SAMPLE_EXPORT
from tests.unit.test_intake_envs import UAT

C = "P77_CHAIN"
PROD = prod_export()


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    return fresh_repo(tmp_path)


def test_only_the_values_of_the_environment_are_taken_by_default(repo: ChainRepo) -> None:
    intake = analyze(repo, UAT, values_only=True)
    by_id = {d.id: d for d in intake.decisions}

    assert intake.values_only and intake.to_json()["values_only"] is True
    groups = [d for d in intake.decisions if d.kind == "group"]
    assert groups and {d.default for d in groups} == {"new"}  # machines, users, mail, [UAT]
    assert by_id[f"{C}/P77_D@TASKTYPE"].default == "ignore"  # a release's change
    assert by_id[f"{C}/P77_B#children"].default == "ignore"
    assert by_id[f"{C}/P77_E#removed"].default == "keep"
    added = by_id[f"{C}/P77_UATONLY#added"]
    assert (added.options, added.default) == (("only-here", "everywhere", "skip"), "skip")


def test_receiving_only_the_values_leaves_the_jobs_alone(repo: ChainRepo) -> None:
    apply(repo, receive(repo, UAT, values_only=True))

    repo = load_repo(repo.root)
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})
    uat = export_xml(repo, "uat")
    for value in (b'RUN_AS="aup77proc"', b'VALUE="u"', b'DEST="ops@example.com"', b"[UAT]"):
        assert value in uat
    assert b"UP77_UATONLY" not in uat and not repo.job_file(C, "P77_UATONLY").exists()
    assert b'JOBNAME="UP77_E"' in uat  # what uat lacks is a release's business too
    assert b'JOBNAME="UP77_D" RUN_AS="aup77proc" TASKTYPE="Command"' in uat
    assert b"UP77_X-UP77_B_OK" not in uat
    assert load_overrides(repo, "uat") == {}
    assert "envs" not in read_json(repo.job_file(C, "P77_E"))


def test_a_repeated_difference_that_is_not_a_value_of_the_environment_is_ignored(
    repo: ChainRepo,
) -> None:
    data = job(UAT, b"UP77_C", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')

    [group] = [d for d in analyze(repo, data, values_only=True).decisions if d.field == "TASKTYPE"]

    assert (group.kind, group.count, group.default) == ("group", 2, "ignore")


def test_a_new_folder_of_a_delivery_is_left_out_too(repo: ChainRepo) -> None:
    folder = ANOMALY_EXPORT.replace(b"UP77_CHAIN", b"UP77_NEWCHAIN")  # a folder prod lacks
    delivery = ANOMALY_EXPORT.replace(
        b"</DEFTABLE>",
        re.search(rb"    <SMART_FOLDER.*</SMART_FOLDER>\n", folder, re.S)[0]  # type: ignore[index]
        + b"</DEFTABLE>",
    )
    intake = analyze(repo, delivery, values_only=True)
    [added] = [d for d in intake.decisions if d.kind == "added"]

    assert not intake.full and (added.node, added.default) == ("P77_NEWCHAIN/", "skip")
    apply(repo, receive(repo, delivery, values_only=True))
    repo = load_repo(repo.root)
    assert not repo.folder_dir("P77_NEWCHAIN").exists()
    assert not repo.folder_meta_file("P77_NEWCHAIN").exists()
    assert "P77_NEWCHAIN" not in read_json(repo.export_meta_file).get("folder_order", [])
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})


def test_a_folder_or_job_can_be_left_out_of_any_full_export(repo: ChainRepo) -> None:
    apply(repo, receive(repo, UAT, choices={f"{C}/P77_UATONLY#added": "skip"}))

    repo = load_repo(repo.root)
    assert not repo.job_file(C, "P77_UATONLY").exists()
    assert "P77_UATONLY" not in read_json(repo.folder_file(C))["jobs"]
    assert b"UP77_UATONLY" not in export_xml(repo, "uat")


def _deduped(tmp_path: Path) -> ChainRepo:
    """A prod baseline whose folder has two jobs called P77_F: the second one is P77_F2."""
    root = tmp_path / "deduped"
    repo = init_repo(root, APP, ("test", "uat", "bench", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, PROD, env="prod", dedupe_jobnames=True)
    git(root, "init", "-q", "-b", "main")
    commit_all(root, "the prod baseline")
    return load_repo(root)


@pytest.mark.parametrize("values_only", [True, False])
def test_a_numbered_job_another_environment_names_otherwise_keeps_its_name(
    tmp_path: Path, values_only: bool
) -> None:
    repo = _deduped(tmp_path)
    second = b'<JOB JOBISN="8" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" '
    second += b'MEMNAME="UP77_F" JOBNAME="UP77_F"'
    uat = both().replace(second, second.replace(b'JOBNAME="UP77_F"', b'JOBNAME="UP77_G"'))
    assert uat != both()

    apply(repo, receive(repo, uat, values_only=values_only))

    repo = load_repo(repo.root)
    assert export_xml(repo, "prod", jobnames="original") == filter_applications(PROD, {APP})


def test_a_value_the_repository_still_has_as_production_has_it_takes_the_constant(
    repo: ChainRepo,
) -> None:
    apply(repo, receive(repo, ANOMALY_EXPORT, values_only=True))  # uat lacks P77_INGEST_DAILY
    repo = load_repo(repo.root)
    bench = both().replace(b"UP77", b"BP77").replace(b"URQ_", b"BRQ_")
    bench = bench.replace(b"[UAT]", b"[BENCH]")

    [adopt] = [d for d in analyze(repo, bench, values_only=True).decisions if d.kind == "adopt"]

    assert (adopt.options, adopt.default) == (("adopt", "ignore"), "adopt")
    assert adopt.constant is not None and adopt.constant.startswith("node.")
    assert (adopt.current, adopt.incoming) == ("PP77_BATCH", "@{" + adopt.constant + "}")
    assert {site.node.partition("/")[0] for site in adopt.sites} == {"P77_INGEST_DAILY"}
    apply(repo, receive(repo, bench, values_only=True))
    repo = load_repo(repo.root)
    assert b"PP77_BATCH" not in export_xml(repo, "bench")
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})


@pytest.mark.parametrize("values_only", [True, False])
def test_the_values_inside_children_left_as_they_were_are_still_taken(
    repo: ChainRepo, values_only: bool
) -> None:
    uat = UAT.replace(
        b'<INCOND NAME="UP77_INGEST_INIT-UP77_INGEST_LOAD_OK" ODATE="ODAT" AND_OR="A" />',
        b'<INCOND NAME="UP77_INGEST_INIT-UP77_INGEST_LOAD_OK" ODATE="ODAT" AND_OR="A" />\n'
        b'            <INCOND NAME="UP77_NEW-UP77_INGEST_LOAD_OK" ODATE="ODAT" AND_OR="A" />',
    )  # a release's new condition on the job that sends the mail
    by_id = {d.id: d for d in analyze(repo, uat, values_only=values_only).decisions}
    assert by_id["P77_INGEST_DAILY/P77_INGEST_LOAD#children"].default == "ignore"

    apply(repo, receive(repo, uat, values_only=values_only))

    exported = export_xml(load_repo(repo.root), "uat")
    assert b'DEST="ops@example.com" SUBJECT="[P77][UAT] Load failed"' in exported
    assert b"UP77_NEW-UP77_INGEST_LOAD_OK" not in exported


def test_a_text_with_production_s_name_inside_takes_the_inline_constant(tmp_path: Path) -> None:
    mail = (
        b'            <ON STMT="*" CODE="NOTOK">\n'
        b'                <DOMAIL URGENCY="R" DEST="ops-prod@example.com" '
        b'SUBJECT="[P77][PROD] D failed" MESSAGE="x" ATTACH_SYSOUT="Y" />\n'
        b"            </ON>\n"
    )
    emits = b'<OUTCOND NAME="PP77_D-PP77_NOBODY_OK" ODATE="ODAT" SIGN="+" />\n'
    prod = PROD.replace(emits, emits + mail)
    repo = fresh_repo(tmp_path, prod)
    apply(repo, receive(repo, SAMPLE_EXPORT, values_only=True))  # uat: the other folder only
    repo = load_repo(repo.root)
    assert "env.subject" in repo.config.constants
    bench = (
        both()
        .replace(emits.replace(b"PP77", b"UP77"), emits.replace(b"PP77", b"UP77") + mail)
        .replace(b"UP77", b"BP77")
        .replace(b"[PROD]", b"[BENCH]")
        .replace(b"[UAT]", b"[BENCH]")
    )

    adopt = {d.constant: d for d in analyze(repo, bench, values_only=True).decisions
             if d.kind == "adopt"}  # fmt: skip

    assert (adopt["env.subject"].current, adopt["env.subject"].incoming) == (
        "PROD", "@{env.subject}",
    )  # fmt: skip
    apply(repo, receive(repo, bench, values_only=True))
    repo = load_repo(repo.root)
    assert b'SUBJECT="[P77][BENCH] D failed"' in export_xml(repo, "bench")
    assert export_xml(repo, "prod") == filter_applications(prod, {APP})
