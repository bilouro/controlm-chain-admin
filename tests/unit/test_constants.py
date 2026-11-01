"""Constants: selectors, pattern filling, import/export substitution, name proposals."""

from __future__ import annotations

import pytest

from controlm_chain_admin.core.constants import (
    ExportConstantsReport,
    Selector,
    apply_export,
    apply_import,
    parse_spec,
    placeholder,
    propose_name,
    values_from_pattern,
)
from controlm_chain_admin.core.errors import ModelError, UnresolvedConstant
from controlm_chain_admin.core.model import XmlDocument, XmlElement
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.samples import SAMPLE_EXPORT

LETTERS = {"test": "T", "uat": "U", "bench": "B", "prod": "P"}


def _values(doc: XmlDocument, tag: str, attr: str) -> list[str]:
    out: list[str] = []

    def walk(el: XmlElement) -> None:
        if el.tag == tag and el.get(attr) is not None:
            out.append(el.get(attr) or "")
        for child in el.elements():
            walk(child)

    walk(doc.root)
    return out


# ---------------------------------------------------------------- selectors


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("NODEID", Selector("NODEID")),
        ("DOMAIL/@DEST", Selector("DEST", tag="DOMAIL")),
        (
            "VARIABLE[NAME=%%GEIENV]/@VALUE",
            Selector("VALUE", tag="VARIABLE", where={"NAME": "%%GEIENV"}),
        ),
    ],
)
def test_parse_spec_and_back(spec: str, expected: Selector) -> None:
    selector = parse_spec(spec)

    assert selector == expected
    assert selector.spec == spec
    assert Selector.from_json(selector.to_json()) == selector


def test_parse_spec_rejects_garbage() -> None:
    with pytest.raises(ModelError):
        parse_spec("DOMAIL/DEST")


def test_values_from_pattern_fills_every_environment() -> None:
    assert values_from_pattern("{L}P77_BATCH", LETTERS) == {
        "test": "TP77_BATCH", "uat": "UP77_BATCH", "bench": "BP77_BATCH", "prod": "PP77_BATCH",
    }  # fmt: skip
    assert values_from_pattern("a{l}p77proc", LETTERS)["prod"] == "app77proc"


# ---------------------------------------------------------------- import


def test_import_replaces_whole_values_bound_to_constants() -> None:
    bindings = {
        "node.batch": Selector("NODEID"),
        "user.proc": Selector("RUN_AS"),
        "mail.ops": parse_spec("DOMAIL/@DEST"),
        "env.lower": parse_spec("VARIABLE[NAME=%%GEIENV]/@VALUE"),
    }
    env = {
        "node.batch": "UP77_BATCH",
        "user.proc": "aup77proc",
        "mail.ops": "ops@example.com",
        "env.lower": "u",
    }

    doc, report = apply_import(parse_xml(SAMPLE_EXPORT), bindings, env)

    assert _values(doc, "JOB", "NODEID") == ["@{node.batch}", "@{node.batch}", "srvu-oth-bat1"]
    assert _values(doc, "JOB", "RUN_AS") == ["@{user.proc}", "@{user.proc}"]
    assert _values(doc, "SMART_FOLDER", "RUN_AS") == ["@{user.proc}", "root"]
    assert _values(doc, "DOMAIL", "DEST") == ["@{mail.ops}"]
    assert _values(doc, "VARIABLE", "VALUE") == ["@{env.lower}"]
    assert report.replaced == 7
    assert report.unmapped == {"NODEID": ("srvu-oth-bat1",), "RUN_AS": ("root",)}


def test_import_inline_mode_replaces_token_bounded_occurrences_only() -> None:
    doc = XmlDocument(
        XmlElement(
            "R",
            (),
            (
                XmlElement("DOMAIL", (("SUBJECT", "[P77][UAT] Load failed"),)),
                XmlElement("DOMAIL", (("SUBJECT", "[UAT_eepe] BACKUATING done"),)),
            ),
        )
    )
    bindings = {"env.display": parse_spec("DOMAIL/@SUBJECT", inline=True)}

    out, report = apply_import(doc, bindings, {"env.display": "UAT"})

    assert _values(out, "DOMAIL", "SUBJECT") == [
        "[P77][@{env.display}] Load failed",
        "[@{env.display}_eepe] BACKUATING done",
    ]
    assert report.replaced == 2 and report.unmapped == {}


def test_import_with_a_null_value_for_the_environment_touches_nothing() -> None:
    doc, report = apply_import(
        parse_xml(SAMPLE_EXPORT), {"node.batch": Selector("NODEID")}, {"node.batch": None}
    )

    assert _values(doc, "JOB", "NODEID")[0] == "UP77_BATCH"
    assert report.replaced == 0 and report.unmapped["NODEID"] == ("UP77_BATCH", "srvu-oth-bat1")


# ---------------------------------------------------------------- export


def test_export_resolves_placeholders_for_the_target_environment() -> None:
    bindings = {
        "node.batch": Selector("NODEID"),
        "env.display": parse_spec("DOMAIL/@SUBJECT", inline=True),
    }
    doc, _ = apply_import(
        parse_xml(SAMPLE_EXPORT), bindings, {"node.batch": "UP77_BATCH", "env.display": "UAT"}
    )

    prod, report = apply_export(doc, bindings, {"node.batch": "PP77_BATCH", "env.display": "PROD"})

    assert _values(prod, "JOB", "NODEID")[:2] == ["PP77_BATCH", "PP77_BATCH"]
    assert _values(prod, "DOMAIL", "SUBJECT") == ["[P77][PROD] Load failed"]
    assert report == ExportConstantsReport(resolved=3, unresolved=())


def test_export_round_trip_restores_the_source_environment() -> None:
    original = parse_xml(SAMPLE_EXPORT)
    bindings = {"node.batch": Selector("NODEID"), "user.proc": Selector("RUN_AS")}
    env = {"node.batch": "UP77_BATCH", "user.proc": "aup77proc"}
    stripped, _ = apply_import(original, bindings, env)

    restored, _ = apply_export(stripped, bindings, env)

    assert restored == original


def test_export_fails_on_unresolved_unless_allowed() -> None:
    doc = XmlDocument(
        XmlElement("R", (), (XmlElement("JOB", (("NODEID", placeholder("node.bat1")),)),))
    )
    bindings = {"node.bat1": Selector("NODEID")}

    with pytest.raises(UnresolvedConstant, match=r"node\.bat1"):
        apply_export(doc, bindings, {"node.bat1": None})

    out, report = apply_export(doc, bindings, {"node.bat1": None}, allow_unresolved=True)
    assert _values(out, "JOB", "NODEID") == ["@{node.bat1}"]
    assert report.unresolved == ("node.bat1",)


def test_export_rejects_placeholders_of_unknown_constants() -> None:
    doc = XmlDocument(XmlElement("R", (), (XmlElement("JOB", (("NODEID", "@{nope}"),)),)))

    with pytest.raises(UnresolvedConstant, match="nope"):
        apply_export(doc, {}, {})


# ---------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("spec", "value", "expected"),
    [
        ("NODEID", "UP77_BATCH", "node.p77_batch"),
        ("NODEID", "srvu-p77-bat1", "node.srvu_p77_bat1"),
        ("RUN_AS", "aup77proc", "user.aup77proc"),
        ("DOMAIL/@DEST", "ops_it@example.com", "mail.ops_it"),
        ("DOMAIL/@CC_DEST", "ld-x@example.com", "mail.ld_x"),
        ("VARIABLE[NAME=%%GEIENV]/@VALUE", "u", "var.geienv"),
        ("CMDLINE", "/x/y", "cmdline.x_y"),
    ],
)
def test_propose_name(spec: str, value: str, expected: str) -> None:
    assert propose_name(parse_spec(spec), value, ("P77", "RQ_", "RC_")) == expected
