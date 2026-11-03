"""The check of an environment's export: where the repository's export of that environment
still differs from it, field by field and node by node, and where the environment differs from
production. Counts and node names only, never values."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.check import Check, FieldCheck, check_export
from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.intake import receive
from controlm_chain_admin.core.overrides import Override, write_overrides
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from tests.support.envexports import both, constants_repo, fresh_repo, job, prod_export, to_prod
from tests.unit.test_intake_envs import UAT

C = "P77_CHAIN"
PROD = prod_export()


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    return fresh_repo(tmp_path)


def _fields(check: Check) -> dict[str, FieldCheck]:
    return {f.field: f for f in check.fields}


def test_production_comes_back_byte_for_byte(repo: ChainRepo) -> None:
    check = check_export(repo, PROD, "prod")

    assert (check.env, check.identical, check.clean) == ("prod", True, True)
    assert check.fields == () and check.only_export == () and check.only_repository == ()
    assert check.nodes == check.both == 11  # the folder of the other application is left out
    assert check.production is None


def test_what_the_repository_does_not_know_of_an_environment_yet(repo: ChainRepo) -> None:
    check = check_export(repo, UAT, "uat")
    fields = _fields(check)

    assert not check.identical and not check.clean
    assert (check.nodes, check.both, check.production) == (11, 10, "prod")
    assert check.only_export == (f"{C}/P77_UATONLY",)
    assert check.only_repository == (f"{C}/P77_E",)
    assert {f: (len(fields[f].differs), fields[f].from_production) for f in fields} == {
        "RUN_AS": (10, 10),
        "NODEID": (8, 8),
        "INCOND": (1, 1),
        "ON/DOMAIL": (1, 1),
        "TASKTYPE": (1, 1),
        "VARIABLE": (1, 1),
    }  # JOBISN is volatile, the place of P77_C is not a field
    assert fields["TASKTYPE"].differs == (f"{C}/P77_D",)


def test_after_its_values_only_what_the_releases_changed_is_left(repo: ChainRepo) -> None:
    apply(repo, receive(repo, UAT, values_only=True))

    check = check_export(load_repo(repo.root), UAT, "uat")
    fields = _fields(check)

    assert fields["RUN_AS"] == FieldCheck("RUN_AS", (), 10)  # uat's own, now in the repository
    assert fields["NODEID"].differs == fields["ON/DOMAIL"].differs == ()
    assert fields["VARIABLE"].differs == ()
    assert fields["TASKTYPE"].differs == (f"{C}/P77_D",)
    assert fields["INCOND"].differs == (f"{C}/P77_B",)
    assert check.exceptions == 0 and check.constants > 0 and check.unresolved == ()
    assert check_export(load_repo(repo.root), PROD, "prod").identical


def test_an_exception_makes_its_job_agree(tmp_path: Path) -> None:
    repo = constants_repo(tmp_path)
    data = job(both(), b"UP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    assert _fields(check_export(repo, data, "uat"))["TASKTYPE"].differs == (f"{C}/P77_E",)

    write_overrides(repo, "uat", {f"{C}/P77_E": Override({"TASKTYPE": "Dummy"})})
    check = check_export(repo, data, "uat")

    assert _fields(check)["TASKTYPE"] == FieldCheck("TASKTYPE", (), 1)  # prod's is Command
    assert check.exceptions == 1 and check.identical


def test_constants_without_a_value_are_told(tmp_path: Path) -> None:
    check = check_export(constants_repo(tmp_path), to_prod(both()), "prod")

    assert check.unresolved == ("user.proc", "var.geienv") and check.constants == 1


def test_a_job_name_twice_in_a_folder_is_paired_by_its_place(repo: ChainRepo) -> None:
    data = re.sub(rb'(<JOB JOBISN="8"[^>]*)TASKTYPE="Dummy"', rb'\1TASKTYPE="Command"', PROD)

    check = check_export(repo, data, "prod")

    assert check.fields == (FieldCheck("TASKTYPE", (f"{C}/P77_F#2",), None),)


def test_the_environment_is_told_by_the_names(repo: ChainRepo) -> None:
    check = check_export(repo, UAT)

    assert check.env == "uat" and "carry the letter U of uat" in check.evidence[0]
    assert check_export(repo, UAT, "bench").warnings == ("the names say uat, not bench",)
    with pytest.raises(ModelError, match="cannot tell the environment"):
        check_export(repo, PROD.replace(b"PP77", b"P77"))


def test_the_report_is_serialisable(repo: ChainRepo) -> None:
    body = check_export(repo, UAT, "uat").to_json()

    assert body["env"] == "uat" and body["production"] == "prod" and body["clean"] is False
    assert {"field": "TASKTYPE", "differs": [f"{C}/P77_D"], "from_production": 1} in body["fields"]
    assert body["only_export"] == [f"{C}/P77_UATONLY"]
