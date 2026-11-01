"""Round trip of the real UAT export: XML -> model -> XML must be byte-identical."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.xmlio import parse_xml, serialize_xml
from tests.support.rawxml import split_folders

pytestmark = pytest.mark.realdata


def test_parser_sees_the_same_top_level_folders_as_the_raw_oracle(uat_export: Path) -> None:
    data = uat_export.read_bytes()

    doc = parse_xml(data)

    raw_names = [f.name for f in split_folders(data).folders]
    parsed_names = [el.get("FOLDER_NAME") for el in doc.root.elements()]
    assert parsed_names == raw_names


def test_full_export_round_trip_is_byte_identical(uat_export: Path) -> None:
    data = uat_export.read_bytes()

    regenerated = serialize_xml(parse_xml(data))

    if regenerated != data:  # report the first difference without dumping real content
        first = next(i for i, (a, b) in enumerate(zip(data, regenerated, strict=False)) if a != b)
        pytest.fail(f"first differing byte at offset {first} of {len(data)}")
    assert len(regenerated) == len(data)
