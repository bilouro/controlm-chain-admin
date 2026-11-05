"""The values of an environment from its full export: machines, users, mails and texts become
constants with a value per environment; a job's own difference is its exception; what the
repository still has as production has it takes the constant another export created."""

from __future__ import annotations

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


def test_a_numbered_job_another_environment_names_otherwise_keeps_its_name(
    tmp_path: Path,
) -> None:
    repo = _deduped(tmp_path)
    second = b'<JOB JOBISN="8" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" '
    second += b'MEMNAME="UP77_F" JOBNAME="UP77_F"'
    uat = both().replace(second, second.replace(b'JOBNAME="UP77_F"', b'JOBNAME="UP77_G"'))
    assert uat != both()

    apply(repo, receive(repo, uat))

    repo = load_repo(repo.root)
    assert export_xml(repo, "prod", jobnames="original") == filter_applications(PROD, {APP})


def test_a_value_the_repository_still_has_as_production_has_it_takes_the_constant(
    repo: ChainRepo,
) -> None:
    apply(repo, receive(repo, ANOMALY_EXPORT))  # uat lacks P77_INGEST_DAILY
    repo = load_repo(repo.root)
    bench = both().replace(b"UP77", b"BP77").replace(b"URQ_", b"BRQ_")
    bench = bench.replace(b"[UAT]", b"[BENCH]")

    [adopt] = [d for d in analyze(repo, bench).decisions if d.kind == "adopt"]

    assert (adopt.options, adopt.default) == (("adopt", "ignore"), "adopt")
    assert adopt.constant is not None and adopt.constant.startswith("node.")
    assert (adopt.current, adopt.incoming) == ("PP77_BATCH", "@{" + adopt.constant + "}")
    assert {site.node.partition("/")[0] for site in adopt.sites} == {"P77_INGEST_DAILY"}
    apply(repo, receive(repo, bench))
    repo = load_repo(repo.root)
    assert b"PP77_BATCH" not in export_xml(repo, "bench")
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})


def test_a_new_line_on_the_job_that_sends_the_mail_is_its_exception_and_the_mail_is_taken(
    repo: ChainRepo,
) -> None:
    uat = UAT.replace(
        b'<INCOND NAME="UP77_INGEST_INIT-UP77_INGEST_LOAD_OK" ODATE="ODAT" AND_OR="A" />',
        b'<INCOND NAME="UP77_INGEST_INIT-UP77_INGEST_LOAD_OK" ODATE="ODAT" AND_OR="A" />\n'
        b'            <INCOND NAME="UP77_NEW-UP77_INGEST_LOAD_OK" ODATE="ODAT" AND_OR="A" />',
    )  # a release's new condition on the job that sends the mail
    by_id = {d.id: d for d in analyze(repo, uat).decisions}
    line = "P77_INGEST_DAILY/P77_INGEST_LOAD@INCOND[link=P77_NEW-P77_INGEST_LOAD_OK,ODATE=ODAT]"
    assert (by_id[line].kind, by_id[line].default) == ("element", "exception")

    apply(repo, receive(repo, uat))

    repo = load_repo(repo.root)
    exported = export_xml(repo, "uat")
    assert b'DEST="ops@example.com" SUBJECT="[P77][UAT] Load failed"' in exported
    assert b"UP77_NEW-UP77_INGEST_LOAD_OK" in exported
    assert b"PP77_NEW-PP77_INGEST_LOAD_OK" not in export_xml(repo, "prod")


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
    apply(repo, receive(repo, SAMPLE_EXPORT))  # uat: the other folder only
    repo = load_repo(repo.root)
    assert "env.subject" in repo.config.constants
    bench = (
        both()
        .replace(emits.replace(b"PP77", b"UP77"), emits.replace(b"PP77", b"UP77") + mail)
        .replace(b"UP77", b"BP77")
        .replace(b"[PROD]", b"[BENCH]")
        .replace(b"[UAT]", b"[BENCH]")
    )

    adopt = {d.constant: d for d in analyze(repo, bench).decisions if d.kind == "adopt"}

    assert (adopt["env.subject"].current, adopt["env.subject"].incoming) == (
        "PROD", "@{env.subject}",
    )  # fmt: skip
    apply(repo, receive(repo, bench))
    repo = load_repo(repo.root)
    assert b'SUBJECT="[P77][BENCH] D failed"' in export_xml(repo, "bench")
    assert export_xml(repo, "prod") == filter_applications(prod, {APP})


def _machines(data: bytes, env: bytes, b: bytes) -> bytes:
    """``data`` with the machines of ``env`` (no letter in them): P77_B on ``b``, the rest on 1."""
    data = data.replace(b'NODEID="PP77_BATCH"', b'NODEID="srv' + env + b'-bat1"')
    return job(data, b"PP77_B", b"-bat1", b"-" + b)


def _as(env_letter: bytes, data: bytes) -> bytes:
    """A prod export as the environment of ``env_letter`` has it (its letter in names)."""
    for prefix in (b"P77", b"RQ_", b"RC_"):
        data = data.replace(b"P" + prefix, env_letter + prefix)
    return data


@pytest.mark.parametrize("uat_first", [False, True], ids=["new constants", "known constants"])
def test_two_machines_of_production_that_are_one_in_test_stay_two(
    tmp_path: Path, uat_first: bool
) -> None:
    prod = _machines(PROD, b"p", b"bat2")
    repo = fresh_repo(tmp_path, prod)
    if uat_first:  # two machines in uat as well: the constants exist when test comes
        apply(repo, receive(repo, _as(b"U", _machines(PROD, b"u", b"bat2"))))
    test = _as(b"T", _machines(PROD, b"t", b"bat1"))  # one machine in test for both

    apply(repo, receive(load_repo(repo.root), test))

    repo = load_repo(repo.root)
    assert export_xml(repo, "prod") == filter_applications(prod, {APP})
    assert export_xml(repo, "test") == filter_applications(test, {APP})


def test_the_machine_most_jobs_have_becomes_the_value_and_the_guess_an_exception(
    repo: ChainRepo,
) -> None:
    apply(repo, receive(repo, _as(b"U", PROD)))  # guesses TP77_BATCH for test
    repo = load_repo(repo.root)
    [node] = [n for n, s in repo.config.constants.items() if s.attribute == "NODEID"]
    test = _as(b"T", PROD).replace(b'NODEID="TP77_BATCH"', b'NODEID="srvt-main"')
    test = job(test, b"TP77_A", b'NODEID="srvt-main"', b'NODEID="TP77_BATCH"')  # one job on it

    intake = analyze(repo, test)
    apply(repo, receive(repo, test))

    by_id = {d.id: d for d in intake.decisions}
    value = by_id[f"value:{node}"]
    assert (value.kind, value.incoming, value.default) == ("set-value", "srvt-main", "set-value")
    [guess] = [d for d in intake.decisions if d.kind == "constant"]
    assert (guess.node, guess.incoming, guess.default) == (f"{C}/P77_A", "TP77_BATCH", "exception")
    repo = load_repo(repo.root)
    assert repo.load_env("test").constants[node] == "srvt-main"
    assert list(load_overrides(repo, "test")) == [f"{C}/P77_A"]
    assert export_xml(repo, "test") == filter_applications(test, {APP})
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})


def test_a_delivery_does_not_move_the_value_of_a_constant(repo: ChainRepo) -> None:
    apply(repo, receive(repo, _as(b"U", PROD)))
    repo = load_repo(repo.root)
    delivery = _as(b"T", ANOMALY_EXPORT.replace(b"UP77", b"PP77"))  # one folder of two
    delivery = delivery.replace(b'NODEID="TP77_BATCH"', b'NODEID="srvt-main"')
    delivery = job(delivery, b"TP77_A", b'NODEID="srvt-main"', b'NODEID="TP77_BATCH"')

    intake = analyze(repo, delivery)

    assert not intake.full
    assert not [d for d in intake.decisions if d.kind == "set-value"]
