"""A name that carries the environment's letter inside a text (``-j UP77_LOAD`` in a command
line) is a token an inline constant replaces, with the letter of each environment: a constant
by default when two jobs or more carry it, an exception of the one job otherwise."""

from __future__ import annotations

from pathlib import Path

from controlm_chain_admin.core.intake import analyze, receive
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.overrides import load_overrides
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import load_repo, read_json
from tests.support.envexports import fresh_repo, job, prod_export
from tests.support.gitrepo import APP
from tests.support.rawxml import filter_applications

F = "P77_INGEST_DAILY"
PROD = prod_export()
TOKEN = "cmdline.p77_ingest_init"


def _as(letter: bytes, data: bytes) -> bytes:
    """The prod export as another environment has it: its letter in names, its user."""
    for prefix in (b"P77", b"RQ_", b"RC_"):
        data = data.replace(b"P" + prefix, letter + prefix)
    return data.replace(b'RUN_AS="app77proc"', b'RUN_AS="a' + letter.lower() + b'p77proc"')


def _commands(data: bytes, names: tuple[bytes, ...]) -> bytes:
    """The jobs ``names`` name the init job in their command line."""
    for name in names:
        data = job(data, name, b'.ksh -d %%ODATE"', b'.ksh -j PP77_INGEST_INIT -d %%ODATE"')
    return data


def test_a_name_with_the_letter_inside_two_commands_is_an_inline_constant(tmp_path: Path) -> None:
    prod = _commands(PROD, (b"PP77_INGEST_INIT", b"PP77_INGEST_LOAD"))
    repo = fresh_repo(tmp_path, prod)
    uat = _as(b"U", prod)

    intake = analyze(repo, uat)
    [group] = [d for d in intake.decisions if d.field == "CMDLINE"]
    apply(repo, receive(repo, uat))

    assert (group.kind, group.inline, group.count, group.default) == ("group", True, 2, "new")
    assert (group.current, group.incoming) == ("PP77_INGEST_INIT", "UP77_INGEST_INIT")
    assert group.id == f"group:CMDLINE~{group.current}>{group.incoming}"
    assert group.suggested == TOKEN
    assert group.values == {
        "test": "TP77_INGEST_INIT", "uat": "UP77_INGEST_INIT",
        "bench": "BP77_INGEST_INIT", "prod": "PP77_INGEST_INIT",
    }  # fmt: skip
    repo = load_repo(repo.root)
    load = read_json(repo.job_file(F, "P77_INGEST_LOAD"))
    assert load["CMDLINE"] == "/opt/p77/bin/load.ksh -j @{" + TOKEN + "} -d %%ODATE"
    assert repo.config.constants[TOKEN].inline
    assert export_xml(repo, "uat") == filter_applications(uat, {APP})
    assert export_xml(repo, "prod") == filter_applications(prod, {APP})
    assert b"-j BP77_INGEST_INIT" in export_xml(repo, "bench")


def test_one_job_with_the_letter_inside_its_command_is_an_exception_by_default(
    tmp_path: Path,
) -> None:
    prod = _commands(PROD, (b"PP77_INGEST_INIT",))
    repo = fresh_repo(tmp_path, prod)
    uat = _as(b"U", prod)

    intake = analyze(repo, uat)
    [group] = [d for d in intake.decisions if d.field == "CMDLINE"]
    apply(repo, receive(repo, uat))

    assert (group.kind, group.inline, group.count) == ("group", True, 1)
    assert group.options == ("new", "exceptions", "change", "ignore")
    assert group.default == "exceptions"
    repo = load_repo(repo.root)
    [(node, exception)] = load_overrides(repo, "uat").items()
    assert node == f"{F}/P77_INGEST_INIT"
    assert exception.attributes == {
        "CMDLINE": "/opt/p77/bin/init.ksh -j UP77_INGEST_INIT -d %%ODATE"
    }
    assert read_json(repo.job_file(F, "P77_INGEST_INIT"))["CMDLINE"].count("PP77_INGEST_INIT") == 1
    assert export_xml(repo, "uat") == filter_applications(uat, {APP})
    assert export_xml(repo, "prod") == filter_applications(prod, {APP})


def test_a_command_that_differs_in_more_than_the_letter_is_that_job_s_own(
    tmp_path: Path,
) -> None:
    prod = _commands(PROD, (b"PP77_INGEST_INIT",))
    repo = fresh_repo(tmp_path, prod)
    uat = job(_as(b"U", prod), b"UP77_INGEST_INIT", b'-d %%ODATE"', b'-d %%ODATE -v"')

    intake = analyze(repo, uat)

    [decision] = [d for d in intake.decisions if d.field == "CMDLINE"]
    assert (decision.kind, decision.inline, decision.default) == ("value", False, "exception")
