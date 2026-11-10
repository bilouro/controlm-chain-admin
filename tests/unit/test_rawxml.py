"""The raw-bytes test oracle splits and filters an export without parsing it."""

from __future__ import annotations

from tests.support.rawxml import filter_applications, split_folders
from tests.support.samples import SAMPLE_APPLICATIONS, SAMPLE_EXPORT, SAMPLE_FOLDER_NAMES


def test_split_finds_every_top_level_folder_with_identity() -> None:
    raw = split_folders(SAMPLE_EXPORT)

    assert [f.name for f in raw.folders] == list(SAMPLE_FOLDER_NAMES)
    assert [f.application for f in raw.folders] == list(SAMPLE_APPLICATIONS)


def test_split_ranges_cover_the_file_exactly() -> None:
    raw = split_folders(SAMPLE_EXPORT)

    body = b"".join(SAMPLE_EXPORT[f.start : f.end] for f in raw.folders)
    assert raw.header + body + raw.footer == SAMPLE_EXPORT
    assert raw.header.startswith(b"<?xml")
    assert raw.footer == b"</DEFTABLE>\n"


def test_each_folder_range_is_a_complete_element() -> None:
    raw = split_folders(SAMPLE_EXPORT)

    for folder in raw.folders:
        chunk = SAMPLE_EXPORT[folder.start : folder.end]
        assert chunk.startswith(b"    <SMART_FOLDER ")
        assert chunk.endswith(b"    </SMART_FOLDER>\n")


def test_filter_keeps_only_the_requested_applications() -> None:
    kept = filter_applications(SAMPLE_EXPORT, {"P77_RISK_ENGINE"})

    assert b'APPLICATION="OTHER_APP"' not in kept
    assert b'FOLDER_NAME="UP77_INGEST_DAILY"' in kept
    assert kept.startswith(b"<?xml") and kept.endswith(b"</DEFTABLE>\n")
    assert split_folders(kept).folders[0].start == split_folders(SAMPLE_EXPORT).folders[0].start


def test_filter_with_all_applications_is_the_identity() -> None:
    assert filter_applications(SAMPLE_EXPORT, set(SAMPLE_APPLICATIONS)) == SAMPLE_EXPORT


def test_filter_with_no_match_keeps_header_and_footer_only() -> None:
    raw = split_folders(SAMPLE_EXPORT)

    assert filter_applications(SAMPLE_EXPORT, {"NOPE"}) == raw.header + raw.footer


def test_an_export_with_windows_line_ends_splits_the_same() -> None:
    """Control-M on Windows writes CRLF and a byte-order mark."""
    windows = b"\xef\xbb\xbf" + SAMPLE_EXPORT.replace(b"\n", b"\r\n")

    raw = split_folders(windows)

    assert [f.name for f in raw.folders] == list(SAMPLE_FOLDER_NAMES)
    body = b"".join(windows[f.start : f.end] for f in raw.folders)
    assert raw.header + body + raw.footer == windows
    assert all(windows[f.start : f.end].endswith(b"</SMART_FOLDER>\r\n") for f in raw.folders)
