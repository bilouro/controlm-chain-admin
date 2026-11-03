"""XML reader and serializer: faithful to the Control-M export layout, byte for byte."""

from __future__ import annotations

import codecs

import pytest

from controlm_chain_admin.core.errors import XmlFormatError
from controlm_chain_admin.core.model import XmlComment, XmlDeclaration, XmlDocument, XmlElement
from controlm_chain_admin.core.xmlio import parse_xml, serialize_xml
from tests.support.samples import SAMPLE_EXPORT

# ---------------------------------------------------------------- parsing


def test_parse_reads_declaration_prolog_comment_and_root() -> None:
    doc = parse_xml(SAMPLE_EXPORT)

    assert doc.declaration == XmlDeclaration(version="1.0", encoding="utf-8", standalone=None)
    assert doc.prolog_comments == ("Exported at 01-01-2026 00:00:00",)
    assert doc.root.tag == "DEFTABLE"
    assert [k for k, _ in doc.root.attrs] == ["xmlns:xsi", "xsi:noNamespaceSchemaLocation"]


def test_parse_keeps_attribute_order_and_child_order() -> None:
    doc = parse_xml(SAMPLE_EXPORT)
    folder = doc.root.find_all("SMART_FOLDER")[0]

    first_four = [k for k, _ in folder.attrs][:4]
    assert first_four == ["JOBISN", "APPLICATION", "SUB_APPLICATION", "JOBNAME"]
    assert [c.tag for c in folder.elements()] == ["JOB", "JOB", "VARIABLE", "INCOND", "OUTCOND"]
    load = folder.find_all("JOB")[1]
    assert [c.tag for c in load.find_all("ON")[0].elements()] == ["DOSHOUT", "DOMAIL"]


def test_parse_unescapes_attribute_values() -> None:
    doc = parse_xml(SAMPLE_EXPORT)
    init = doc.root.find_all("SMART_FOLDER")[0].find_all("JOB")[0]

    assert init.get("DESCRIPTION") == 'Init <run> "daily"'
    assert doc.root.find_all("SMART_FOLDER")[0].get("DESCRIPTION") == "Daily ingest & load"
    assert init.get("MISSING") is None
    assert init.get("MISSING", "x") == "x"


def test_parse_keeps_comments_inside_elements_in_place() -> None:
    data = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b"<ROOT>\n"
        b'    <A X="1" />\n'
        b"    <!--between-->\n"
        b'    <B Y="2" />\n'
        b"</ROOT>\n"
    )

    doc = parse_xml(data)

    assert doc.root.children == (
        XmlElement("A", (("X", "1"),)),
        XmlComment("between"),
        XmlElement("B", (("Y", "2"),)),
    )


def test_parse_rejects_text_content() -> None:
    data = b'<?xml version="1.0" encoding="utf-8"?>\n<ROOT><A>text</A></ROOT>\n'

    with pytest.raises(XmlFormatError, match="text content"):
        parse_xml(data)


def test_parse_rejects_missing_declaration() -> None:
    with pytest.raises(XmlFormatError, match="declaration"):
        parse_xml(b"<ROOT />\n")


def test_parse_rejects_malformed_xml() -> None:
    with pytest.raises(XmlFormatError):
        parse_xml(b'<?xml version="1.0" encoding="utf-8"?>\n<ROOT><A></ROOT>\n')


# ---------------------------------------------------------------- serializing


def test_round_trip_of_sample_is_byte_identical() -> None:
    assert serialize_xml(parse_xml(SAMPLE_EXPORT)) == SAMPLE_EXPORT


def test_serialize_escapes_attribute_values_like_the_control_m_client() -> None:
    doc = XmlDocument(root=XmlElement("R", (("V", "a&b<c>d\"e\tf\ng\rh'i"),)))

    out = serialize_xml(doc)

    assert out == (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b'<R V="a&amp;b&lt;c&gt;d&quot;e&#x9;f&#xA;g&#xD;h\'i" />\n'
    )


def test_serialize_indents_four_spaces_and_self_closes_empty_elements() -> None:
    doc = XmlDocument(
        root=XmlElement("R", (), (XmlElement("A", (("X", "1"),), (XmlElement("B"),)),)),
        prolog_comments=("c",),
    )

    out = serialize_xml(doc)

    assert out == (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b"<!--c-->\n"
        b"<R>\n"
        b'    <A X="1">\n'
        b"        <B />\n"
        b"    </A>\n"
        b"</R>\n"
    )


@pytest.mark.parametrize(
    ("standalone", "expected"),
    [(None, b""), (True, b' standalone="yes"'), (False, b' standalone="no"')],
)
def test_serialize_writes_standalone_only_when_present(
    standalone: bool | None, expected: bytes
) -> None:
    doc = XmlDocument(root=XmlElement("R"), declaration=XmlDeclaration(standalone=standalone))

    head = b'<?xml version="1.0" encoding="utf-8"' + expected + b"?>\n"
    assert serialize_xml(doc).startswith(head)


def test_serialize_writes_non_ascii_as_utf8() -> None:
    doc = XmlDocument(root=XmlElement("R", (("D", "Préparation"),)))

    assert 'D="Préparation"'.encode() in serialize_xml(doc)
    assert parse_xml(serialize_xml(doc)).root.get("D") == "Préparation"


def test_a_byte_order_mark_is_read_and_written_back() -> None:
    with_bom = codecs.BOM_UTF8 + SAMPLE_EXPORT

    doc = parse_xml(with_bom)

    assert doc.bom and not parse_xml(SAMPLE_EXPORT).bom
    assert serialize_xml(doc) == with_bom


def test_windows_line_endings_are_read_and_written_back() -> None:
    crlf = SAMPLE_EXPORT.replace(b"\n", b"\r\n")

    doc = parse_xml(crlf)

    assert doc.newline == "\r\n" and parse_xml(SAMPLE_EXPORT).newline == "\n"
    assert serialize_xml(doc) == crlf
