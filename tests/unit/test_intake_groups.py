"""A new repository learns its environments from their exports: repeated differences are groups.

The repository starts from the prod export alone (no constant). The uat export then differs in
the same way in many jobs; each such difference is one decision, and taking it creates the
constant that makes both exports come out as they were.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.intake import Decision, analyze, receive
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.overrides import load_overrides
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from tests.support.envexports import both, fresh_repo, job, prod_export
from tests.support.gitrepo import APP
from tests.support.rawxml import filter_applications

C = "P77_CHAIN"
UAT = both()
PROD = prod_export()


def fresh(tmp_path: Path, data: bytes = PROD) -> ChainRepo:
    return fresh_repo(tmp_path, data)


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    return fresh(tmp_path)


def _groups(repo: ChainRepo, data: bytes = UAT) -> dict[str, Decision]:
    return {d.field or "": d for d in analyze(repo, data).decisions if d.kind == "group"}


def test_each_repeated_difference_is_one_decision(repo: ChainRepo) -> None:
    intake = analyze(repo, UAT)

    groups = {d.field: d for d in intake.decisions if d.kind == "group"}
    run_as = groups["RUN_AS"]
    assert (run_as.current, run_as.incoming, run_as.count) == (
        "app77proc", "aup77proc", UAT.count(b'RUN_AS="aup77proc"'),
    )  # fmt: skip
    assert (run_as.default, run_as.suggested) == ("new", "user.app77proc")
    assert run_as.options == ("new", "exceptions", "change", "ignore")
    assert run_as.values == {"test": "app77proc", "uat": "aup77proc", "bench": "app77proc",
                             "prod": "app77proc"}  # fmt: skip
    geienv = groups["VARIABLE[NAME=%%GEIENV]/@VALUE"]  # one site is enough for a variable
    assert (geienv.count, geienv.default, geienv.suggested) == (1, "new", "var.geienv")
    mail = groups["DOMAIL/@DEST"]  # inside an ON block: no exception there
    assert (mail.incoming, mail.default, mail.options) == (
        "ops@example.com", "new", ("new", "change", "ignore"),
    )  # fmt: skip
    assert not [d for d in intake.decisions if d.kind in ("value", "children")]


def test_a_value_with_the_letter_of_the_environment_fills_every_environment(
    repo: ChainRepo,
) -> None:
    node = _groups(repo)["NODEID"]

    assert (node.current, node.incoming, node.suggested) == (
        "PP77_BATCH", "UP77_BATCH", "node.p77_batch",
    )  # fmt: skip
    assert node.values == {"test": "TP77_BATCH", "uat": "UP77_BATCH", "bench": "BP77_BATCH",
                           "prod": "PP77_BATCH"}  # fmt: skip


def test_the_name_of_the_environment_inside_a_text(repo: ChainRepo) -> None:
    subject = _groups(repo)["DOMAIL/@SUBJECT"]

    assert subject.inline and subject.default == "new"
    assert subject.suggested == "env.subject"
    assert subject.values == {"test": "TEST", "uat": "UAT", "bench": "BENCH", "prod": "PROD"}


def test_other_repeated_differences_default_to_exceptions(tmp_path: Path) -> None:
    data = job(UAT, b"UP77_D", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    data = job(data, b"UP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    once = job(UAT, b"UP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    repo = fresh(tmp_path)

    dummy = _groups(repo, data)["TASKTYPE"]
    single = {d.id: d for d in analyze(repo, once).decisions}

    assert (dummy.count, dummy.default) == (2, "exceptions")
    assert single[f"{C}/P77_E@TASKTYPE"].kind == "value"  # once is not a group


def test_a_value_that_means_two_things_is_exceptions_by_default_or_a_role(tmp_path: Path) -> None:
    data = job(UAT, b"UP77_D", b'NODEID="UP77_BATCH"', b'NODEID="UP77_OTHER"')
    data = job(data, b"UP77_E", b'NODEID="UP77_BATCH"', b'NODEID="UP77_OTHER"')
    repo = fresh(tmp_path)

    groups = [
        d for d in analyze(repo, data).decisions if d.kind == "group" and d.field == "NODEID"
    ]

    most, other = sorted(groups, key=lambda d: -d.count)
    assert most.default == "new"  # prod PP77_BATCH is uat UP77_BATCH almost everywhere
    assert other.default == "exceptions"  # the two jobs on another machine there
    assert "new" in other.options  # or a constant of their own, with prod's value of the first


def test_taking_the_groups_keeps_both_exports_as_they_were(repo: ChainRepo) -> None:
    apply(repo, receive(repo, UAT, choices={"group:RUN_AS=app77proc>aup77proc":
                                             "new:user.batch_user_proc"}))  # fmt: skip

    repo = load_repo(repo.root)
    job_a = read_json(repo.job_file(C, "P77_A"))
    assert (job_a["RUN_AS"], job_a["NODEID"]) == ("@{user.batch_user_proc}", "@{node.p77_batch}")
    assert repo.config.constants["env.subject"].inline
    assert export_xml(repo, "uat") == filter_applications(UAT, {APP})
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})
    bench = export_xml(repo, "bench")
    assert b'NODEID="BP77_BATCH"' in bench and b"[P77][BENCH]" in bench
    assert repo.load_env("bench").constants["user.batch_user_proc"] == "app77proc"


def test_exceptions_for_every_job_of_a_group(repo: ChainRepo) -> None:
    apply(repo, receive(repo, UAT, choices={"group:RUN_AS=app77proc>aup77proc": "exceptions"}))

    repo = load_repo(repo.root)
    exceptions = load_overrides(repo, "uat")
    assert read_json(repo.job_file(C, "P77_A"))["RUN_AS"] == "app77proc"
    assert exceptions[f"{C}/P77_A"].attributes["RUN_AS"] == "aup77proc"
    assert export_xml(repo, "uat") == filter_applications(UAT, {APP})


def _mail(data: bytes, name: bytes, subject: bytes) -> bytes:
    """Give job ``name`` an ON block, after its conditions, that mails ``subject``."""
    end = data.index(b"        </JOB>", data.index(b'JOBNAME="' + name + b'"'))
    block = (
        b'            <ON STMT="*" CODE="NOTOK">\n                <DOMAIL URGENCY="R" '
        b'DEST="ops@example.com" SUBJECT="' + subject + b'" />\n            </ON>\n'
    )
    return data[:end] + block + data[end:]


def test_a_text_that_also_changes_otherwise_is_its_own_decision(tmp_path: Path) -> None:
    prod = _mail(PROD, b"PP77_A", b"[P77][PROD] A failed!")
    uat = _mail(UAT, b"UP77_A", b"[P77][UAT] A failed")
    repo = fresh(tmp_path, prod)

    decisions = analyze(repo, uat).decisions

    subject = next(d for d in decisions if d.id == "group:DOMAIL/@SUBJECT~env")
    assert (subject.count, subject.default) == (1, "new")
    assert [d.incoming for d in decisions if d.kind == "value"] == ["[P77][UAT] A failed"]


def test_jobs_the_export_does_not_change_stay_as_they_were(tmp_path: Path) -> None:
    prod = _mail(PROD, b"PP77_A", b"UAT checks")  # prod names uat: dirty, but it is prod
    prod = job(prod, b"PP77_B", b'NODEID="PP77_BATCH"', b'NODEID="UP77_BATCH"')
    repo = fresh(tmp_path, prod)
    uat = _mail(UAT, b"UP77_A", b"UAT checks")

    apply(repo, receive(repo, uat))

    repo = load_repo(repo.root)
    assert read_json(repo.job_file(C, "P77_B"))["NODEID"] == "UP77_BATCH"
    assert export_xml(repo, "prod") == filter_applications(prod, {APP})
    assert export_xml(repo, "uat") == filter_applications(uat, {APP})


def test_the_value_most_jobs_share_becomes_the_constant(tmp_path: Path) -> None:
    prod = job(PROD, b"PP77_D", b'RUN_AS="app77proc"', b'RUN_AS="other"')
    prod = job(prod, b"PP77_E", b'RUN_AS="app77proc"', b'RUN_AS="other"')
    repo = fresh(tmp_path, prod)

    groups = [d for d in analyze(repo, UAT).decisions if d.kind == "group" and d.field == "RUN_AS"]

    most, other = sorted(groups, key=lambda d: -d.count)
    assert (most.current, most.default) == ("app77proc", "new")
    assert (other.current, other.count, other.default) == ("other", 2, "exceptions")
    assert "new" in other.options  # a role of those two jobs: uat's user, bound job by job


def _flip(data: bytes, name: bytes) -> bytes:
    """Flip the sign of the first OUTCOND of job ``name``: + becomes -."""
    start = data.index(b'JOBNAME="' + name + b'"')
    at = data.index(b'SIGN="+"', start)
    assert at < data.index(b"</JOB>", start)
    return data[:at] + b'SIGN="-"' + data[at + len(b'SIGN="+"') :]


def test_a_member_of_a_group_is_decided_on_its_own(tmp_path: Path) -> None:
    data = job(UAT, b"UP77_D", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    data = job(data, b"UP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    repo = fresh(tmp_path)
    apart = f"{C}/P77_E@TASKTYPE"

    dummy = _groups(repo, data)["TASKTYPE"]
    apply(repo, receive(repo, data, choices={dummy.id: "exceptions", apart: "ignore"}))

    assert [m.id for m in dummy.members] == [f"{C}/P77_D@TASKTYPE", apart]
    assert [(m.kind, m.node, m.options) for m in dummy.members] == [
        ("value", f"{C}/P77_D", ("change", "exception", "ignore")),
        ("value", f"{C}/P77_E", ("change", "exception", "ignore")),
    ]
    assert [m["id"] for m in dummy.to_json()["members"]] == [m.id for m in dummy.members]
    repo = load_repo(repo.root)
    assert sorted(load_overrides(repo, "uat")) == [f"{C}/P77_D"]
    assert read_json(repo.job_file(C, "P77_E"))["TASKTYPE"] == "Command"
    expected = filter_applications(data, {APP})
    expected = job(expected, b"UP77_E", b'TASKTYPE="Dummy"', b'TASKTYPE="Command"')
    assert export_xml(repo, "uat") == expected


def test_a_group_decided_member_by_member_has_nothing_left(tmp_path: Path) -> None:
    data = job(UAT, b"UP77_D", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    data = job(data, b"UP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    repo = fresh(tmp_path)
    choices = {f"{C}/P77_D@TASKTYPE": "ignore", f"{C}/P77_E@TASKTYPE": "exception"}

    apply(repo, receive(repo, data, choices=choices))

    repo = load_repo(repo.root)
    assert sorted(load_overrides(repo, "uat")) == [f"{C}/P77_E"]
    assert read_json(repo.job_file(C, "P77_D"))["TASKTYPE"] == "Command"


def test_a_condition_of_one_job_is_decided_apart_from_its_group(tmp_path: Path) -> None:
    data = _flip(_flip(UAT, b"UP77_A"), b"UP77_B")
    repo = fresh(tmp_path)

    [signs] = [
        d
        for d in analyze(repo, data).decisions
        if d.kind == "group" and (d.field or "").endswith("SIGN")
    ]
    first, second = signs.members
    apply(repo, receive(repo, data, choices={signs.id: "change", second.id: "ignore"}))

    assert (signs.count, signs.options) == (2, ("new", "change", "ignore"))
    assert (first.node, second.node) == (f"{C}/P77_A", f"{C}/P77_B")
    assert first.options == ("change", "ignore")  # a condition cannot be an exception
    repo = load_repo(repo.root)
    assert export_xml(repo, "uat") == _flip(filter_applications(UAT, {APP}), b"UP77_A")
