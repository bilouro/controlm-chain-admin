"""Element <-> JSON conversion: grouped children where the order is canonical, lists elsewhere."""

from __future__ import annotations

from controlm_chain_admin.core.jsonmodel import (
    GROUPED_PARENTS,
    OWN_ORDER_KEY,
    element_to_json,
    json_to_element,
    merge_orders,
    merge_volatile,
    observe_sequences,
    split_volatile,
    with_own_order,
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


def test_the_orders_of_the_sample() -> None:
    attr_seen, child_seen = observe_sequences(parse_xml(SAMPLE_EXPORT))
    attr_order, child_order = merge_orders({}, attr_seen), merge_orders({}, child_seen)

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


def test_observe_sequences_leaves_out_grouped_parents_with_contradictory_child_order() -> None:
    data = (
        b'<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE>\n'
        b"    <SMART_FOLDER>\n        <JOB />\n        <VARIABLE />\n    </SMART_FOLDER>\n"
        b"    <SMART_FOLDER>\n        <VARIABLE />\n        <JOB />\n    </SMART_FOLDER>\n"
        b"</DEFTABLE>\n"
    )

    _, child_seen = observe_sequences(parse_xml(data))

    assert "SMART_FOLDER" not in child_seen
    assert child_seen["DEFTABLE"] == (("SMART_FOLDER",),)


def test_observe_sequences_keeps_what_each_element_shows() -> None:
    data = (
        b'<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE>\n'
        b'    <JOB A="1" W="2" />\n    <JOB A="1" D="3" />\n    <JOB A="1" W="4" />\n'
        b"</DEFTABLE>\n"
    )

    attr_seen, _ = observe_sequences(parse_xml(data))

    assert attr_seen["JOB"] == (("A", "W"), ("A", "D"))


def test_observe_sequences_keeps_both_orders_of_an_export_written_two_ways() -> None:
    data = (
        b'<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE>\n'
        b'    <JOB A="1" B="2" />\n    <JOB B="2" A="1" />\n'
        b"</DEFTABLE>\n"
    )

    attr_seen, _ = observe_sequences(parse_xml(data))

    assert attr_seen["JOB"] == (("A", "B"), ("B", "A"))


def test_merge_orders_extends_without_contradiction() -> None:
    merged = merge_orders({"JOB": ("A", "C")}, {"JOB": (("A", "B", "C"),), "X": (("P",),)})

    assert merged == {"JOB": ("A", "B", "C"), "X": ("P",)}


def test_merge_orders_keeps_the_recorded_order_against_an_element_written_another_way() -> None:
    # that element keeps its own order in its metadata (with_own_order)
    merged = merge_orders({"JOB": ("A", "B")}, {"JOB": (("B", "A"), ("A", "C"), ("B", "X", "A"))})

    assert merged == {"JOB": ("A", "B", "C", "X")}


def test_merge_orders_keeps_the_place_of_names_that_never_meet() -> None:
    # W and D are never in one element: no export says which comes first, so the order recorded
    # stays, although this export alone would put D first (it shows D first)
    merged = merge_orders(
        {"JOB": ("A", "W", "D", "Z")}, {"JOB": (("A", "D", "Z"), ("A", "W", "Z"))}
    )

    assert merged == {"JOB": ("A", "W", "D", "Z")}


def test_an_element_in_the_canonical_order_needs_no_order_of_its_own() -> None:
    attrs = (("JOBISN", "3"), ("JOBNAME", "J"), ("RUN_AS", "u"))

    assert with_own_order(attrs, {"JOBISN": "3"}, ("JOBISN", "JOBNAME", "RUN_AS")) == {
        "JOBISN": "3"
    }


def test_an_element_written_another_way_is_merged_back_in_its_own_order() -> None:
    attrs = (("JOBISN", "3"), ("RUN_AS", "u"), ("JOBNAME", "J"))
    order = ("JOBISN", "JOBNAME", "RUN_AS")
    kept, meta = split_volatile(attrs, ("JOBISN",))

    meta = with_own_order(attrs, meta, order)

    assert meta == {"JOBISN": "3", OWN_ORDER_KEY: "JOBISN RUN_AS JOBNAME"}
    assert merge_volatile(dict(kept), meta, order) == attrs


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
