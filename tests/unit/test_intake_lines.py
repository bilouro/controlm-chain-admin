"""Every difference a full export of another environment has, line by line (a condition, a
SHOUT, an action inside an ON block, a variable it lacks): an exception of that environment by
default, a change of the base or ignored when chosen. Production stays as it was, and an
exception equal to what production gains later goes by itself."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.intake import analyze, receive
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.overrides import load_overrides
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.envexports import fresh_repo, job, prod_export
from tests.support.gitrepo import APP
from tests.support.rawxml import filter_applications
from tests.unit.test_intake_envs import UAT

C = "P77_CHAIN"
ING = "P77_INGEST_DAILY"
PROD = prod_export()
NEW_INCOND = f"{C}/P77_B@INCOND[link=P77_X-P77_B_OK,ODATE=ODAT]"
A_SIGN = f"{C}/P77_A@OUTCOND[link=P77_A-P77_B_OK,ODATE=ODAT]/@SIGN"
C_INCOND = f"{C}/P77_C@INCOND[link=P77_B-P77_C_OK,ODATE=ODAT]"
DOCOND = "ON[STMT=*,CODE=NOTOK]/DOCOND[link=P77_B-P77_C_OK,ODATE=ODAT]"
DOCOND_SIGN = f"{C}/P77_B@{DOCOND}/@SIGN"
FOLDER_SIGN = f"{C}/@OUTCOND[link=P77_OTHER-P77_CHAIN_OK,ODATE=ODAT]/@SIGN"
GEIENV = f"{ING}/@%%GEIENV"


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    return fresh_repo(tmp_path)


def _in_job(data: bytes, name: bytes, before: bytes, after: bytes) -> bytes:
    """Replace ``before`` by ``after`` inside the element of job ``name`` only."""
    start = data.rindex(b"<JOB ", 0, data.index(b'JOBNAME="' + name + b'"'))
    end = data.index(b"</JOB>", start)
    return data[:start] + data[start:end].replace(before, after, 1) + data[end:]


def _lines(xml: bytes, name: str, tag: str) -> list[dict[str, str]]:
    for folder in parse_xml(xml).root.elements():
        if folder.get("FOLDER_NAME") == name:
            return [dict(c.attrs) for c in folder.elements() if c.tag == tag]
        for element in folder.elements():
            if element.tag == "JOB" and element.get("JOBNAME") == name:
                return [dict(c.attrs) for c in element.elements() if c.tag == tag]
    raise AssertionError(name)


def _uat_lines() -> bytes:
    """uat as UAT has it, and: P77_A emits its condition with the other sign, P77_C waits for
    nothing, the DOCOND of P77_B deletes instead of adding, the folder's own condition has the
    other sign, and the other folder has no %%GEIENV."""
    data = _in_job(UAT, b"UP77_A", b'SIGN="+"', b'SIGN="-"')
    data = _in_job(
        data, b"UP77_C",
        b'            <INCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" AND_OR="A" />\n', b"",
    )  # fmt: skip
    data = _in_job(
        data, b"UP77_B",
        b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" />',
        b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="-" />',
    )  # fmt: skip
    data = data.replace(
        b'<OUTCOND NAME="UP77_OTHER-UP77_CHAIN_OK" ODATE="ODAT" SIGN="-" />',
        b'<OUTCOND NAME="UP77_OTHER-UP77_CHAIN_OK" ODATE="ODAT" SIGN="+" />',
    )
    return data.replace(b'        <VARIABLE NAME="%%GEIENV" VALUE="u" />\n', b"")


def test_every_difference_is_an_exception_of_the_environment_by_default(repo: ChainRepo) -> None:
    uat = _uat_lines()

    intake = analyze(repo, uat)
    apply(repo, receive(repo, uat))

    by_id = {d.id: d for d in intake.decisions}
    added = by_id[NEW_INCOND]
    assert (added.kind, added.options, added.default) == (
        "element", ("change", "exception", "ignore"), "exception",
    )  # fmt: skip
    assert (added.current, added.incoming) == (None, "AND_OR=A")
    gone = by_id[C_INCOND]
    assert (gone.kind, gone.current, gone.incoming, gone.default) == (
        "element", "AND_OR=A", None, "exception",
    )  # fmt: skip
    sign = by_id[A_SIGN]
    assert (sign.kind, sign.current, sign.incoming, sign.default) == (
        "value",
        "+",
        "-",
        "exception",
    )
    assert by_id[DOCOND_SIGN].default == by_id[FOLDER_SIGN].default == "exception"
    variable = by_id[GEIENV]
    assert (variable.kind, variable.current, variable.incoming, variable.default) == (
        "value", "x", None, "exception",
    )  # fmt: skip
    assert variable.options == ("change", "exception", "ignore")
    assert not [d for d in intake.decisions if d.kind == "children"]

    repo = load_repo(repo.root)
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})
    exported = export_xml(repo, "uat")
    assert _lines(exported, "UP77_B", "INCOND") == [
        {"NAME": "UP77_A-UP77_B_OK", "ODATE": "ODAT", "AND_OR": "A"},
        {"NAME": "UP77_X-UP77_B_OK", "ODATE": "ODAT", "AND_OR": "A"},
    ]
    assert _lines(exported, "UP77_C", "INCOND") == []
    assert _lines(exported, "UP77_A", "OUTCOND")[0]["SIGN"] == "-"
    assert b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="-" />' in exported
    assert _lines(exported, "UP77_CHAIN", "OUTCOND")[0]["SIGN"] == "+"
    assert b"%%GEIENV" not in exported
    overrides = load_overrides(repo, "uat")
    assert overrides[f"{C}/P77_B"].elements == {
        "INCOND[link=P77_X-P77_B_OK,ODATE=ODAT]": {
            "AND_OR": "A", "after": "INCOND[link=P77_A-P77_B_OK,ODATE=ODAT]",
        },
        DOCOND: {"SIGN": "-"},
    }  # fmt: skip
    assert overrides[f"{C}/P77_C"].elements == {"INCOND[link=P77_B-P77_C_OK,ODATE=ODAT]": None}
    assert overrides[f"{C}/"].elements == {
        "OUTCOND[link=P77_OTHER-P77_CHAIN_OK,ODATE=ODAT]": {"SIGN": "+"}
    }
    assert overrides[f"{ING}/"].variables == {"%%GEIENV": None}


def test_receiving_the_same_export_again_changes_nothing(repo: ChainRepo) -> None:
    uat = _uat_lines()
    apply(repo, receive(repo, uat))
    repo = load_repo(repo.root)
    before = {env: export_xml(repo, env) for env in ("uat", "prod")}

    again = analyze(repo, uat)
    change = receive(repo, uat)
    apply(repo, change)

    assert again.decisions and all(d.known and d.default == "exception" for d in again.decisions)
    assert {d.id for d in again.decisions} >= {NEW_INCOND, C_INCOND, A_SIGN, DOCOND_SIGN, GEIENV}
    assert not [d for d in again.decisions if d.kind == "group"]  # known ones stay one by one
    assert change.edits == ()
    repo = load_repo(repo.root)
    assert {env: export_xml(repo, env) for env in ("uat", "prod")} == before


def test_a_line_is_a_change_of_the_base_or_ignored_when_chosen(repo: ChainRepo) -> None:
    uat = _uat_lines()
    choices = {
        NEW_INCOND: "change", C_INCOND: "ignore", A_SIGN: "change", DOCOND_SIGN: "ignore",
        FOLDER_SIGN: "ignore", GEIENV: "change",
    }  # fmt: skip

    apply(repo, receive(repo, uat, choices=choices))

    repo = load_repo(repo.root)
    prod = export_xml(repo, "prod")
    assert _lines(prod, "PP77_B", "INCOND") == [
        {"NAME": "PP77_A-PP77_B_OK", "ODATE": "ODAT", "AND_OR": "A"},
        {"NAME": "PP77_X-PP77_B_OK", "ODATE": "ODAT", "AND_OR": "A"},
    ]  # the base gained the line, after the one uat has it after
    assert len(_lines(prod, "PP77_C", "INCOND")) == 1  # ignored: the base keeps it
    assert _lines(prod, "PP77_A", "OUTCOND")[0]["SIGN"] == "-"
    assert b'<DOCOND NAME="PP77_B-PP77_C_OK" ODATE="ODAT" SIGN="+" />' in prod
    assert _lines(prod, "PP77_CHAIN", "OUTCOND")[0]["SIGN"] == "-"
    assert b"%%GEIENV" not in prod
    exported = export_xml(repo, "uat")
    assert len(_lines(exported, "UP77_C", "INCOND")) == 1  # ignored: uat follows the base
    assert b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" />' in exported
    overrides = load_overrides(repo, "uat")
    assert not {f"{C}/P77_B", f"{C}/P77_C", f"{C}/", f"{ING}/"} & set(overrides)


def test_an_exception_equal_to_what_production_gained_goes_by_itself(repo: ChainRepo) -> None:
    uat = _uat_lines()
    apply(repo, receive(repo, uat))
    repo = load_repo(repo.root)
    gained = b'<INCOND NAME="PP77_A-PP77_B_OK" ODATE="ODAT" AND_OR="A" />'
    prod = PROD.replace(
        gained,
        gained + b'\n            <INCOND NAME="PP77_X-PP77_B_OK" ODATE="ODAT" AND_OR="A" />',
    )
    prod = job(prod, b"PP77_D", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')

    apply(repo, receive(repo, prod))

    repo = load_repo(repo.root)
    overrides = load_overrides(repo, "uat")
    assert f"{C}/P77_D" not in overrides
    assert overrides[f"{C}/P77_B"].elements == {DOCOND: {"SIGN": "-"}}
    assert export_xml(repo, "prod") == filter_applications(prod, {APP})
    exported = export_xml(repo, "uat")
    assert b'<INCOND NAME="UP77_X-UP77_B_OK" ODATE="ODAT" AND_OR="A" />' in exported
    assert b'JOBNAME="UP77_D" RUN_AS="aup77proc" TASKTYPE="Dummy"' in exported


def test_a_delivery_takes_its_lines_into_the_base(repo: ChainRepo) -> None:
    delivery = re.sub(
        rb'    <SMART_FOLDER [^>]*FOLDER_NAME="UP77_INGEST_DAILY".*?</SMART_FOLDER>\n',
        b"", _uat_lines(), flags=re.S,
    )  # fmt: skip

    intake = analyze(repo, delivery)
    apply(repo, receive(repo, delivery))

    by_id = {d.id: d for d in intake.decisions}
    assert not intake.full and by_id[NEW_INCOND].default == by_id[C_INCOND].default == "change"
    repo = load_repo(repo.root)
    prod = export_xml(repo, "prod")
    assert len(_lines(prod, "PP77_B", "INCOND")) == 2 and _lines(prod, "PP77_C", "INCOND") == []
    assert load_overrides(repo, "uat") == {}


def test_an_attribute_one_side_alone_has_inside_a_line_is_an_exception(repo: ChainRepo) -> None:
    uat = _in_job(
        UAT, b"UP77_B",
        b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" />',
        b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" AND_OR="O" />',
    )  # fmt: skip
    uat = _in_job(
        uat, b"UP77_B",
        b'<INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" AND_OR="A" />',
        b'<INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" />',
    )  # fmt: skip
    incond = "INCOND[link=P77_A-P77_B_OK,ODATE=ODAT]"

    intake = analyze(repo, uat)
    apply(repo, receive(repo, uat))

    by_id = {d.id: d for d in intake.decisions}
    extra = by_id[f"{C}/P77_B@{DOCOND}/@AND_OR"]
    assert (extra.current, extra.incoming, extra.default) == (None, "O", "exception")
    missing = by_id[f"{C}/P77_B@{incond}/@AND_OR"]
    assert (missing.current, missing.incoming, missing.default) == ("A", None, "exception")
    repo = load_repo(repo.root)
    assert export_xml(repo, "prod") == filter_applications(PROD, {APP})
    exported = export_xml(repo, "uat")
    assert b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" AND_OR="O" />' in exported
    assert _lines(exported, "UP77_B", "INCOND")[0] == {"NAME": "UP77_A-UP77_B_OK", "ODATE": "ODAT"}
    lines = load_overrides(repo, "uat")[f"{C}/P77_B"].elements
    assert (lines[DOCOND], lines[incond]) == ({"AND_OR": "O"}, {"AND_OR": None})
    assert all(d.known for d in analyze(repo, uat).decisions)


def test_what_is_an_exception_already_can_become_the_base_or_go(repo: ChainRepo) -> None:
    uat = _uat_lines()
    apply(repo, receive(repo, uat))
    repo = load_repo(repo.root)

    by_id = {d.id: d for d in analyze(repo, uat).decisions}
    choices = {NEW_INCOND: "change", GEIENV: "change", DOCOND_SIGN: "ignore", C_INCOND: "ignore"}
    apply(repo, receive(repo, uat, choices=choices))

    known = by_id[NEW_INCOND]
    assert (known.kind, known.known, known.options, known.default) == (
        "element", True, ("change", "exception", "ignore"), "exception",
    )  # fmt: skip
    assert known.to_json()["known"] is True
    repo = load_repo(repo.root)
    prod = export_xml(repo, "prod")
    assert len(_lines(prod, "PP77_B", "INCOND")) == 2  # the base took the line
    assert b"%%GEIENV" not in prod  # and lost the variable
    assert len(_lines(prod, "PP77_C", "INCOND")) == 1
    exported = export_xml(repo, "uat")
    assert b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" />' in exported  # back to base
    assert len(_lines(exported, "UP77_C", "INCOND")) == 1  # the line is back in uat
    overrides = load_overrides(repo, "uat")
    assert f"{C}/P77_C" not in overrides and f"{ING}/" not in overrides
    assert f"{C}/P77_B" not in overrides  # the added line is the base's, the DOCOND went
    assert f"{C}/P77_A" in overrides  # the sign of P77_A stays its exception
