"""Import the real UAT export into a temporary chain repository and export it back."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.repo import init_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.rawxml import filter_applications, split_folders
from tests.unit.test_repo_ops import snapshot

pytestmark = pytest.mark.realdata


def _main_application(data: bytes) -> str:
    """The application with most folders in the export (the chain this repo manages)."""
    counts: dict[str, int] = {}
    for folder in split_folders(data).folders:
        counts[folder.application or ""] = counts.get(folder.application or "", 0) + 1
    return max(counts, key=lambda k: counts[k])


def test_import_then_export_equals_the_application_filtered_original(
    uat_export: Path, tmp_path: Path
) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    repo = init_repo(tmp_path, app, ("test", "uat", "bench", "prod"))

    report = import_xml(repo, data)
    regenerated = export_xml(repo)

    expected = filter_applications(data, {app})
    assert len(report.folders) == len(
        [f for f in split_folders(data).folders if f.application == app]
    )
    assert report.jobs == sum(len(f.find_all("JOB")) for f in parse_xml(expected).root.elements())
    if regenerated != expected:
        first = next(
            i for i, (a, b) in enumerate(zip(expected, regenerated, strict=False)) if a != b
        )
        pytest.fail(f"first differing byte at offset {first} of {len(expected)}")


def test_reimporting_the_real_export_is_idempotent(uat_export: Path, tmp_path: Path) -> None:
    data = uat_export.read_bytes()
    repo = init_repo(tmp_path, _main_application(data), ("uat",))
    import_xml(repo, data)
    before = snapshot(tmp_path)

    import_xml(repo, export_xml(repo))

    assert snapshot(tmp_path) == before
