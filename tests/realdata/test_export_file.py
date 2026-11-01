"""Sanity checks on the real export in the private data repository (skipped without it)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.rawxml import filter_applications, split_folders

pytestmark = pytest.mark.realdata


def test_export_is_a_deftable_with_top_level_folders(uat_export: Path) -> None:
    data = uat_export.read_bytes()
    raw = split_folders(data)

    assert raw.header.startswith(b'<?xml version="1.0" encoding="utf-8"?>')
    assert raw.footer == b"</DEFTABLE>\n"
    assert len(raw.folders) > 0
    assert all(f.application for f in raw.folders), "every folder has an APPLICATION"


def test_folder_ranges_rebuild_the_file_byte_for_byte(uat_export: Path) -> None:
    data = uat_export.read_bytes()
    raw = split_folders(data)

    rebuilt = raw.header + b"".join(data[f.start : f.end] for f in raw.folders) + raw.footer
    assert rebuilt == data


def test_filtering_to_all_applications_is_the_identity(uat_export: Path) -> None:
    data = uat_export.read_bytes()
    applications = {f.application for f in split_folders(data).folders if f.application}

    assert filter_applications(data, applications) == data
    assert len(applications) >= 1
