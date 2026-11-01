"""Element <-> JSON conversion: grouped children where the order is canonical, lists elsewhere."""

from __future__ import annotations

import pytest

from controlm_chain_admin.core.errors import OrderConflict
from controlm_chain_admin.core.jsonmodel import (
    GROUPED_PARENTS,
    element_to_json,
    json_to_element,
    merge_orders,
    merge_volatile,
    observe_orders,
    split_volatile,
)
from controlm_chain_admin.core.model import XmlComment, XmlElement
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.samples import SAMPLE_EXPORT

CHILD_ORDER = {
    "SMART_FOLDER": (
        "JOB", "VARIABLE", "CONTROL", "SHOUT", "INCOND", "OUTCOND", "RULE_BASED_CALENDAR", "ON",
    ),
    "JOB": (
        "VARIABLE", "SHOUT", "CONTROL", "INCOND", "QUANTITATIVE", "OUTCOND",
        "RULE_BASED_CALENDARS", "ON",
    ),
}  # fmt: skip


def _load_job() -> XmlElement:
    doc = parse_xml(SAMPLE_EXPORT)
    return doc.root.find_all("SMART_FOLDER")[0].find_all("JOB")[1]  # UP77_INGEST_LOAD


def test_job_attributes_come_first_in_source_order_then_groups_in_canonical_order() -> None:
    data = element_to_json(_load_job(), CHILD_ORDER)

    keys = list(data)
    assert keys[:3] == ["JOBISN", "APPLICATION", "SUB_APPLICATION"]
    assert [k for k in keys if isinstance(data[k], list)] == ["INCOND", "OUTCOND", "ON"]
    assert data["INCOND"] == [
        {"NAME": "UP77_INGEST_INIT-UP77_INGEST_LOAD_OK", "ODATE": "ODAT", "AND_OR": "A"}
    ]


def test_on_block_keeps_its_actions_as_an_ordered_list_with_tags() -> None:
    data = element_to_json(_load_job(), CHILD_ORDER)

    on = data["ON"][0]
    assert on["STMT"] == "*" and on["CODE"] == "NOTOK"
    assert [action["tag"] for action in on["children"]] == ["DOSHOUT", "DOMAIL"]
    assert on["children"][0] == {
        "tag": "DOSHOUT",
        "URGENCY": "R",
        "MESSAGE": "Alert",
        "DEST": "EM",
    }


def test_json_round_trip_rebuilds_the_identical_element() -> None:
    job = _load_job()

    assert json_to_element("JOB", element_to_json(job, CHILD_ORDER), CHILD_ORDER) == job


def test_folder_round_trip_including_jobs_and_folder_level_children() -> None:
    folder = parse_xml(SAMPLE_EXPORT).root.find_all("SMART_FOLDER")[0]

    rebuilt = json_to_element("SMART_FOLDER", element_to_json(folder, CHILD_ORDER), CHILD_ORDER)
    assert rebuilt == folder


def test_element_with_a_comment_falls_back_to_the_ordered_list() -> None:
    element = XmlElement(
        "JOB", (("JOBNAME", "X"),), (XmlComment("c"), XmlElement("INCOND", (("NAME", "n"),)))
    )

    data = element_to_json(element, CHILD_ORDER)

    assert data == {
        "JOBNAME": "X",
        "children": [{"tag": "#comment", "text": "c"}, {"tag": "INCOND", "NAME": "n"}],
    }
    assert json_to_element("JOB", data, CHILD_ORDER) == element


def test_observe_orders_from_the_sample() -> None:
    attr_order, child_order = observe_orders(parse_xml(SAMPLE_EXPORT))

    assert attr_order["INCOND"] == ("NAME", "ODATE", "AND_OR")
    assert attr_order["JOB"][:5] == (
        "JOBISN",
        "APPLICATION",
        "SUB_APPLICATION",
        "MEMNAME",
        "JOBNAME",
    )
    assert child_order["SMART_FOLDER"] == ("JOB", "VARIABLE", "INCOND", "OUTCOND")
    assert child_order["JOB"] == (
        "QUANTITATIVE",
        "INCOND",
        "OUTCOND",
        "RULE_BASED_CALENDARS",
        "ON",
    )
    assert set(child_order) <= set(GROUPED_PARENTS), "ON and other parents are never grouped"


def test_observe_orders_leaves_out_grouped_parents_with_contradictory_child_order() -> None:
    data = (
        b'<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE>\n'
        b"    <SMART_FOLDER>\n        <JOB />\n        <VARIABLE />\n    </SMART_FOLDER>\n"
        b"    <SMART_FOLDER>\n        <VARIABLE />\n        <JOB />\n    </SMART_FOLDER>\n"
        b"</DEFTABLE>\n"
    )

    _, child_order = observe_orders(parse_xml(data))

    assert "SMART_FOLDER" not in child_order
    assert child_order["DEFTABLE"] == ("SMART_FOLDER",)


def test_merge_orders_extends_without_contradiction() -> None:
    merged = merge_orders({"JOB": ("A", "C")}, {"JOB": ("A", "B", "C"), "X": ("P",)})

    assert merged == {"JOB": ("A", "B", "C"), "X": ("P",)}


def test_merge_orders_raises_on_contradiction() -> None:
    with pytest.raises(OrderConflict):
        merge_orders({"JOB": ("A", "B")}, {"JOB": ("B", "A")})


def test_split_and_merge_volatile_restore_the_original_attribute_tuple() -> None:
    attrs = (("JOBISN", "3"), ("APPLICATION", "P77"), ("VERSION", "9"), ("JOBNAME", "J"))
    order = ("JOBISN", "APPLICATION", "VERSION", "JOBNAME")

    kept, meta = split_volatile(attrs, ("JOBISN", "VERSION"))

    assert kept == (("APPLICATION", "P77"), ("JOBNAME", "J"))
    assert meta == {"JOBISN": "3", "VERSION": "9"}
    assert merge_volatile(dict(kept), meta, order) == attrs


def test_merge_volatile_appends_unknown_attributes_after_the_known_ones() -> None:
    merged = merge_volatile({"B": "2", "NEW": "n"}, {"A": "1"}, ("A", "B"))

    assert merged == (("A", "1"), ("B", "2"), ("NEW", "n"))
