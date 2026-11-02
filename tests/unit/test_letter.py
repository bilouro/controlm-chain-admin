"""Environment-letter rule: strip on import, add on export, literal marks, suspicious values."""

from __future__ import annotations

import pytest

from controlm_chain_admin.core.letter import LetterReport, LetterRule, add_letter, strip_letter
from controlm_chain_admin.core.model import XmlDocument, XmlElement
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.samples import SAMPLE_EXPORT

RULE = LetterRule(prefixes=("P77", "RQ_", "RC_"))
LETTERS = ("T", "U", "B", "P")


def _values(doc: XmlDocument, tag: str, attr: str) -> list[str]:
    out: list[str] = []

    def walk(el: XmlElement) -> None:
        if el.tag == tag:
            value = el.get(attr)
            if value is not None:
                out.append(value)
        for child in el.elements():
            walk(child)

    walk(doc.root)
    return out


def _single(tag: str, attr: str, value: str) -> XmlDocument:
    return XmlDocument(XmlElement("R", (), (XmlElement(tag, ((attr, value),)),)))


def test_strip_removes_the_letter_only_where_a_known_prefix_follows() -> None:
    doc, report = strip_letter(parse_xml(SAMPLE_EXPORT), "U", RULE, LETTERS)

    assert _values(doc, "SMART_FOLDER", "FOLDER_NAME") == ["P77_INGEST_DAILY", "UOTH_HOUSEKEEPING"]
    assert _values(doc, "JOB", "JOBNAME")[:2] == ["P77_INGEST_INIT", "P77_INGEST_LOAD"]
    assert _values(doc, "QUANTITATIVE", "NAME") == ["RQ_AM"]
    assert _values(doc, "JOB", "MEMNAME")[2] == "cleanup.ksh"  # no prefix: untouched
    assert report == LetterReport((), ())


def test_strip_handles_the_letter_at_every_token_boundary_of_a_condition_name() -> None:
    doc, _ = strip_letter(parse_xml(SAMPLE_EXPORT), "U", RULE, LETTERS)

    assert _values(doc, "INCOND", "NAME") == [
        "P77_INGEST_INIT-P77_INGEST_LOAD_OK",
        "P77_PRICING-P77_INGEST_DAILY_OK",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("UP77_A_UP77_B_OK", "P77_A_P77_B_OK"),  # underscore-joined names
        ("UP77_A-TO-UP77_B", "P77_A-TO-P77_B"),  # A-TO-B pattern
        ("UP77DNOUNDERSCORE", "P77DNOUNDERSCORE"),  # prefix glued to the name
        ("XUP77_A", "XUP77_A"),  # letter not at a boundary: untouched
        ("SUB_URQ_X", "SUB_RQ_X"),  # resource token after a separator
    ],
)
def test_strip_examples(value: str, expected: str) -> None:
    doc, report = strip_letter(_single("INCOND", "NAME", value), "U", RULE, LETTERS)

    assert _values(doc, "INCOND", "NAME") == [expected]
    assert report == LetterReport((), ())


def test_strip_never_touches_attributes_outside_the_whitelist() -> None:
    doc, _ = strip_letter(parse_xml(SAMPLE_EXPORT), "U", RULE, LETTERS)

    assert _values(doc, "SMART_FOLDER", "APPLICATION") == ["P77_RISK_ENGINE", "OTHER_APP"]
    assert _values(doc, "JOB", "NODEID")[0] == "UP77_BATCH"
    assert _values(doc, "DOMAIL", "SUBJECT") == ["[P77][UAT] Load failed"]


@pytest.mark.parametrize("value", ["P77_RAW", "UP77_A-P77_B_OK", "X_RC_NOT_A_CONTROL"])
def test_strip_marks_ambiguous_values_as_literal_and_keeps_them_whole(value: str) -> None:
    doc, report = strip_letter(_single("JOB", "JOBNAME", value), "U", RULE, LETTERS)

    assert _values(doc, "JOB", "JOBNAME") == [f"literal:{value}"]
    assert report.literal_marks == (f"JOB/@JOBNAME={value}",)


def test_strip_reports_values_carrying_another_environments_letter() -> None:
    doc, report = strip_letter(_single("INCOND", "NAME", "PP77_X-UP77_Y_OK"), "U", RULE, LETTERS)

    assert _values(doc, "INCOND", "NAME") == ["PP77_X-P77_Y_OK"]  # the P token is kept
    assert report.suspicious == ("INCOND/@NAME=PP77_X-UP77_Y_OK",)
    assert report.literal_marks == ()


def test_add_restores_the_original_document() -> None:
    original = parse_xml(SAMPLE_EXPORT)
    stripped, _ = strip_letter(original, "U", RULE, LETTERS)

    assert add_letter(stripped, "U", RULE) == original


def test_add_with_another_letter_moves_every_prefixed_token_to_that_environment() -> None:
    stripped, _ = strip_letter(parse_xml(SAMPLE_EXPORT), "U", RULE, LETTERS)

    prod = add_letter(stripped, "P", RULE)

    assert _values(prod, "SMART_FOLDER", "FOLDER_NAME") == [
        "PP77_INGEST_DAILY",
        "UOTH_HOUSEKEEPING",
    ]
    assert _values(prod, "INCOND", "NAME")[0] == "PP77_INGEST_INIT-PP77_INGEST_LOAD_OK"
    assert _values(prod, "QUANTITATIVE", "NAME") == ["PRQ_AM"]
    assert _values(prod, "JOB", "NODEID")[0] == "UP77_BATCH"  # not a name attribute


def test_add_removes_the_literal_marker_without_adding_a_letter() -> None:
    doc = _single("JOB", "JOBNAME", "literal:P77_RAW")

    assert _values(add_letter(doc, "P", RULE), "JOB", "JOBNAME") == ["P77_RAW"]


def test_add_does_not_touch_tokens_that_already_carry_a_letter() -> None:
    doc = _single("INCOND", "NAME", "PP77_X-P77_Y_OK")

    assert _values(add_letter(doc, "U", RULE), "INCOND", "NAME") == ["PP77_X-UP77_Y_OK"]


def test_disabled_rule_changes_nothing() -> None:
    original = parse_xml(SAMPLE_EXPORT)

    stripped, report = strip_letter(original, "U", LetterRule(), LETTERS)

    assert stripped == original and add_letter(original, "P", LetterRule()) == original
    assert report == LetterReport((), ())


RESOURCES = LetterRule(prefixes=("P77", "RQ_", "RC_"), leading_only=("RQ_", "RC_"))


@pytest.mark.parametrize(
    ("tag", "value", "neutral", "prod"),
    [
        ("QUANTITATIVE", "URQ_P77_AGGREGATION", "RQ_P77_AGGREGATION", "PRQ_P77_AGGREGATION"),
        ("CONTROL", "URC_P77ALIMECO", "RC_P77ALIMECO", "PRC_P77ALIMECO"),
        ("QUANTITATIVE", "URQ_AM", "RQ_AM", "PRQ_AM"),
        ("INCOND", "UP77_A-UP77_B_OK", "P77_A-P77_B_OK", "PP77_A-PP77_B_OK"),
    ],
)
def test_resource_names_carry_the_letter_on_their_first_prefix_only(
    tag: str, value: str, neutral: str, prod: str
) -> None:
    doc, report = strip_letter(_single(tag, "NAME", value), "U", RESOURCES, LETTERS)

    assert _values(doc, tag, "NAME") == [neutral]
    assert report == LetterReport((), ())
    assert _values(add_letter(doc, "P", RESOURCES), tag, "NAME") == [prod]


def test_a_resource_of_another_environment_is_kept_and_reported() -> None:
    doc, report = strip_letter(_single("QUANTITATIVE", "NAME", "TRQ_AM"), "U", RESOURCES, LETTERS)

    assert _values(doc, "QUANTITATIVE", "NAME") == ["TRQ_AM"]
    assert report.suspicious == ("QUANTITATIVE/@NAME=TRQ_AM",)
    assert _values(add_letter(doc, "P", RESOURCES), "QUANTITATIVE", "NAME") == ["TRQ_AM"]


def test_a_bare_resource_name_is_still_a_literal() -> None:
    doc, report = strip_letter(_single("QUANTITATIVE", "NAME", "RQ_P77"), "U", RESOURCES, LETTERS)

    assert _values(doc, "QUANTITATIVE", "NAME") == ["literal:RQ_P77"]
    assert report.literal_marks == ("QUANTITATIVE/@NAME=RQ_P77",)
