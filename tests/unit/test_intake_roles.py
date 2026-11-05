"""A role a few jobs have in one environment (another user, another machine) is a constant of
its own, bound job by job: it shares production's value with the constant most jobs have, and
the exports keep each job's constant, since their values there cannot tell the two apart."""

from __future__ import annotations

from pathlib import Path

from controlm_chain_admin.core.intake import analyze, receive
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.overrides import load_overrides
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from tests.support.envexports import fresh_repo, job, prod_export
from tests.support.gitrepo import APP
from tests.support.rawxml import filter_applications

C = "P77_CHAIN"
PROD = prod_export()
ROLE = "user.special_user_proc"
ROLE_GROUP = "group:RUN_AS=app77proc>auspecial"


def _as(letter: bytes, data: bytes, user: bytes) -> bytes:
    """The prod export as another environment has it: its letter in names, its user."""
    for prefix in (b"P77", b"RQ_", b"RC_"):
        data = data.replace(b"P" + prefix, letter + prefix)
    return data.replace(b'RUN_AS="app77proc"', b'RUN_AS="' + user + b'"')


def _uat_with_a_role() -> bytes:
    """uat's user everywhere but in two jobs, which run as another one there."""
    data = _as(b"U", PROD, b"aup77proc")
    for name in (b"UP77_A", b"UP77_B"):
        data = job(data, name, b'RUN_AS="aup77proc"', b'RUN_AS="auspecial"')
    return data


def _with_role(tmp_path: Path) -> tuple[ChainRepo, bytes]:
    repo = fresh_repo(tmp_path)
    uat = _uat_with_a_role()
    apply(repo, receive(repo, uat, choices={ROLE_GROUP: f"new:{ROLE}"}))
    return load_repo(repo.root), uat


def test_a_role_of_some_jobs_can_be_a_constant_beside_the_one_most_jobs_have(
    tmp_path: Path,
) -> None:
    repo = fresh_repo(tmp_path)
    uat = _uat_with_a_role()

    intake = analyze(repo, uat)
    role = {d.id: d for d in intake.decisions}[ROLE_GROUP]
    apply(repo, receive(repo, uat, choices={ROLE_GROUP: f"new:{ROLE}"}))

    assert (role.kind, role.count, role.default) == ("group", 2, "exceptions")
    assert role.options == ("new", "exceptions", "change", "ignore")
    assert role.values == {
        "test": "app77proc", "uat": "auspecial", "bench": "app77proc", "prod": "app77proc",
    }  # fmt: skip
    repo = load_repo(repo.root)
    assert export_xml(repo, "uat") == filter_applications(uat, {APP})
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})
    assert load_overrides(repo, "uat") == {}
    assert read_json(repo.job_file(C, "P77_A"))["RUN_AS"] == "@{" + ROLE + "}"
    assert read_json(repo.job_file(C, "P77_C"))["RUN_AS"] == "@{user.app77proc}"
    assert repo.load_env("prod").constants[ROLE] == "app77proc"


def test_an_export_where_both_constants_have_one_value_keeps_each_job_s_own(
    tmp_path: Path,
) -> None:
    repo, uat = _with_role(tmp_path)

    intake = analyze(repo, PROD)  # production: the same user behind both constants
    apply(repo, receive(repo, PROD))

    assert not [d for d in intake.decisions if d.kind in ("value", "group", "children")]
    assert {f.status for f in intake.folders} == {"same"}
    repo = load_repo(repo.root)
    assert read_json(repo.job_file(C, "P77_A"))["RUN_AS"] == "@{" + ROLE + "}"
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})
    assert export_xml(repo, "uat") == filter_applications(uat, {APP})


def test_an_environment_without_the_role_gives_both_constants_its_user(tmp_path: Path) -> None:
    repo, _ = _with_role(tmp_path)
    bench = _as(b"B", PROD, b"abp77proc")

    apply(repo, receive(repo, bench))

    repo = load_repo(repo.root)
    assert repo.load_env("bench").constants[ROLE] == "abp77proc"
    assert repo.load_env("bench").constants["user.app77proc"] == "abp77proc"
    assert load_overrides(repo, "bench") == {}
    assert export_xml(repo, "bench") == filter_applications(bench, {APP})


def test_a_role_of_production_bound_to_its_jobs_when_the_environment_has_one_user(
    tmp_path: Path,
) -> None:
    prod = PROD
    for name in (b"PP77_A", b"PP77_B"):  # two jobs run as another user in production
        prod = job(prod, name, b'RUN_AS="app77proc"', b'RUN_AS="approle"')
    repo = fresh_repo(tmp_path, prod)
    uat = _as(b"U", prod, b"aup77proc").replace(b'RUN_AS="approle"', b'RUN_AS="aup77proc"')
    group = "group:RUN_AS=approle>aup77proc"

    role = {d.id: d for d in analyze(repo, uat).decisions}[group]
    apply(repo, receive(repo, uat, choices={group: f"new:{ROLE}"}))

    assert (role.count, role.default) == (2, "exceptions")
    assert role.values == {
        "test": "approle", "uat": "aup77proc", "bench": "approle", "prod": "approle",
    }  # fmt: skip
    repo = load_repo(repo.root)
    assert read_json(repo.job_file(C, "P77_A"))["RUN_AS"] == "@{" + ROLE + "}"
    assert export_xml(repo, "prod") == filter_applications(prod, {APP})
    assert export_xml(repo, "uat") == filter_applications(uat, {APP})
