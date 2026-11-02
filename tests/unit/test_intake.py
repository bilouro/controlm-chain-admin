"""What an export of one environment brings: its environment, values to learn, differences."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.constants import define_constant, parse_spec
from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.intake import analyze
from controlm_chain_admin.core.repo import ChainRepo
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.envexports import both, constants_repo, job, to_prod
from tests.support.gitrepo import commit_all

C = "P77_CHAIN"
ING = "P77_INGEST_DAILY"


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    return constants_repo(tmp_path)


def test_the_environment_is_told_by_the_letter(repo: ChainRepo) -> None:
    prod = analyze(repo, to_prod(both()))
    uat = analyze(repo, ANOMALY_EXPORT)

    assert prod.env == "prod" and uat.env == "uat"
    assert any("letter P" in line for line in prod.evidence)
    mixed = (
        to_prod(ANOMALY_EXPORT)
        .replace(b"PP77_D", b"UP77_D")
        .replace(b'FOLDER_NAME="PP77_CHAIN"', b'FOLDER_NAME="UP77_CHAIN"')
    )
    with pytest.raises(ModelError, match="cannot tell the environment"):
        analyze(repo, mixed)
    assert analyze(repo, mixed, env="prod").warnings  # told, but the names disagree


def test_values_to_learn_exceptions_and_changes(repo: ChainRepo) -> None:
    data = to_prod(both())
    data = job(data, b"PP77_D", b'RUN_AS="app77proc"', b'RUN_AS="special"')
    data = job(data, b"PP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    data = job(data, b"PP77_A", b'NODEID="PP77_BATCH"', b'NODEID="PP77_OTHER"')

    intake = analyze(repo, data)

    by_id = {d.id: d for d in intake.decisions}
    learn = by_id["learn:user.proc"]
    assert (learn.kind, learn.incoming, learn.count, learn.default) == (
        "learn", "app77proc", 10, "learn",
    )  # fmt: skip
    assert (by_id["learn:var.geienv"].incoming, by_id["learn:var.geienv"].count) == ("x", 1)
    special = by_id[f"{C}/P77_D@RUN_AS"]  # disagrees with the value learned from the others
    assert (special.kind, special.current, special.incoming, special.default) == (
        "constant", "@{user.proc}", "special", "exception",
    )  # fmt: skip
    assert special.options == ("exception", "new", "ignore")
    other = by_id[f"{C}/P77_A@NODEID"]  # disagrees with the value prod already has
    assert (other.kind, other.expected, other.incoming, other.default) == (
        "constant", "PP77_BATCH", "PP77_OTHER", "exception",
    )  # fmt: skip
    assert other.options == ("exception", "new", "set-value", "ignore")
    dummy = by_id[f"{C}/P77_E@TASKTYPE"]
    assert (dummy.kind, dummy.current, dummy.incoming, dummy.default) == (
        "value", "Command", "Dummy", "change",
    )  # fmt: skip
    assert dummy.options == ("change", "exception", "ignore")
    assert [d.id for d in intake.decisions if d.field == "NODEID"] == [f"{C}/P77_A@NODEID"]
    assert [(f.name, f.status) for f in intake.folders] == [(ING, "changed"), (C, "changed")]
    assert not intake.partial and intake.unresolved == ()


def test_a_partial_export_with_new_and_removed_jobs(repo: ChainRepo) -> None:
    data = ANOMALY_EXPORT.replace(b'<JOB JOBISN="4"', b'<JOB JOBISN="4" X="1"')  # P77_C
    data = re.sub(rb'\n\s*<JOB JOBISN="6".*?</JOB>', b"", data, flags=re.S)  # P77_E
    data = data.replace(
        b"    </SMART_FOLDER>",
        b'        <JOB JOBISN="9" APPLICATION="P77_RISK_ENGINE" JOBNAME="UP77_NEW" '
        b'RUN_AS="nobody" PARENT_FOLDER="UP77_CHAIN" />\n    </SMART_FOLDER>',
    )

    intake = analyze(repo, data)

    assert intake.partial and [f.name for f in intake.folders] == [C]
    chain = intake.folders[0]
    assert chain.jobs_added == ("P77_NEW",)
    by_id = {d.id: d for d in intake.decisions}
    assert by_id[f"{C}/P77_C@X"].kind == "value"
    removed = by_id[f"{C}/P77_E#removed"]
    assert (removed.kind, removed.options, removed.default) == (
        "removed", ("remove", "keep"), "remove",
    )  # fmt: skip
    unmatched = by_id["unmatched:RUN_AS=nobody"]
    assert (unmatched.kind, unmatched.constant, unmatched.count, unmatched.default) == (
        "unmatched", "user.nobody", 1, "new",
    )  # fmt: skip
    assert unmatched.options == ("new", "use:user.proc", "literal")
    assert intake.unresolved == ()


def test_a_known_value_the_whole_export_contradicts_is_one_decision(repo: ChainRepo) -> None:
    define_constant(
        repo, "var.geienv", parse_spec("VARIABLE[NAME=%%GEIENV]/@VALUE"), {"prod": "p"}
    )  # fmt: skip  (wrong: prod has x)
    commit_all(repo.root, "chore: a wrong value")

    intake = analyze(repo, to_prod(both()))

    by_id = {d.id: d for d in intake.decisions}
    fix = by_id["value:var.geienv"]
    assert (fix.kind, fix.expected, fix.incoming, fix.count, fix.default) == (
        "set-value", "p", "x", 1, "set-value",
    )  # fmt: skip
    assert fix.options == ("set-value", "exceptions", "ignore")
    assert not [d for d in intake.decisions if d.field == "%%GEIENV"]


def test_volatile_attributes_are_not_differences(repo: ChainRepo) -> None:
    data = ANOMALY_EXPORT.replace(b'<JOB JOBISN="2"', b'<JOB JOBISN="22"')

    intake = analyze(repo, data)

    assert intake.decisions == () and [f.status for f in intake.folders] == ["same"]
