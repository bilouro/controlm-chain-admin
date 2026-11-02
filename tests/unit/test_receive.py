"""Receiving an export: the decisions of the intake applied as one previewed change."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import InvalidChange
from controlm_chain_admin.core.intake import receive
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.overrides import Override, load_overrides
from controlm_chain_admin.core.refactor import apply, run_operation
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.envexports import both, constants_repo, job, to_prod
from tests.support.rawxml import filter_applications

C = "P77_CHAIN"
APP = "P77_RISK_ENGINE"


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    return constants_repo(tmp_path)


def _job(repo: ChainRepo, name: str) -> dict:  # type: ignore[type-arg]
    return read_json(repo.root / "folders" / C / "jobs" / f"{name}.json")  # type: ignore[no-any-return]


def test_by_default_values_are_learned_and_changes_go_to_the_base(repo: ChainRepo) -> None:
    data = job(to_prod(both()), b"PP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')

    change = receive(repo, data)
    apply(repo, change)

    assert change.summary.startswith("receive a prod export: 2 folders")
    prod = load_repo(repo.root).load_env("prod").constants
    assert (prod["user.proc"], prod["var.geienv"]) == ("app77proc", "x")
    assert _job(repo, "P77_A")["RUN_AS"] == "@{user.proc}"  # still neutral
    assert _job(repo, "P77_E")["TASKTYPE"] == "Dummy"
    assert export_xml(repo, "prod") == filter_applications(data, {APP})


def test_an_exception_keeps_the_base_for_the_other_environments(repo: ChainRepo) -> None:
    data = job(to_prod(both()), b"PP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')

    apply(repo, receive(repo, data, choices={f"{C}/P77_E@TASKTYPE": "exception"}))

    assert _job(repo, "P77_E")["TASKTYPE"] == "Command"
    assert load_overrides(repo, "prod") == {
        f"{C}/P77_E": Override(attributes={"TASKTYPE": "Dummy"})
    }
    assert export_xml(repo, "prod") == filter_applications(data, {APP})
    assert b'JOBNAME="UP77_E" RUN_AS="aup77proc" TASKTYPE="Command"' in export_xml(repo, "uat")


def test_ignored_values_and_kept_jobs_leave_the_repository_as_it_was(repo: ChainRepo) -> None:
    data = job(ANOMALY_EXPORT, b"UP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    data = re.sub(rb'\n\s*<JOB JOBISN="5".*?</JOB>', b"", data, flags=re.S)  # P77_D
    before = export_xml(repo, "uat")

    change = receive(
        repo, data, choices={f"{C}/P77_E@TASKTYPE": "ignore", f"{C}/P77_D#removed": "keep"}
    )

    assert change.edits == () or all(e.path.startswith("chain.json") for e in change.edits)
    apply(repo, change)
    assert export_xml(repo, "uat") == before


def test_bad_choices_and_unresolved_values_are_refused(repo: ChainRepo) -> None:
    data = job(ANOMALY_EXPORT, b"UP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    with pytest.raises(InvalidChange, match="choose one of change, exception, ignore"):
        receive(repo, data, choices={f"{C}/P77_E@TASKTYPE": "learn"})
    with pytest.raises(InvalidChange, match="unknown decision"):
        receive(repo, data, choices={"nope": "ignore"})

    new = ANOMALY_EXPORT.replace(
        b"    </SMART_FOLDER>",
        b'        <JOB JOBISN="9" APPLICATION="P77_RISK_ENGINE" JOBNAME="UP77_NEW" '
        b'RUN_AS="nobody" PARENT_FOLDER="UP77_CHAIN" />\n    </SMART_FOLDER>',
    )
    with pytest.raises(InvalidChange, match="RUN_AS=nobody"):
        receive(repo, new)


def test_receive_is_an_operation_with_the_xml_as_text(repo: ChainRepo) -> None:
    data = job(to_prod(both()), b"PP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')

    change = run_operation(repo, "receive", {"xml": data.decode(), "env": "prod"})

    assert change.summary == receive(repo, data).summary
