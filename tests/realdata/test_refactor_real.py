"""Refactorings on the real chain: small change sets, and rename + rename back is lossless."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.refactor import apply, rename_folder, rename_job
from controlm_chain_admin.core.repo import init_repo
from tests.realdata.test_environments import _prefixes
from tests.realdata.test_import_export import _main_application
from tests.support.rawxml import filter_applications

pytestmark = pytest.mark.realdata


def test_rename_job_and_folder_there_and_back_restore_the_export(
    uat_export: Path, tmp_path: Path
) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    repo = init_repo(tmp_path, app, ("uat", "prod"), prefixes=_prefixes(app))
    import_xml(repo, data, env="uat")
    expected = filter_applications(data, {app})
    edge = next(link for link in load_links(repo).values() if link.kind == "edge")
    job = edge.producers[0]
    assert job.job is not None

    started = time.perf_counter()
    change = rename_job(repo, str(job), job.job + "_RENAMED")
    preview_seconds = time.perf_counter() - started
    assert 3 <= len(change.edits) <= 8, change.stat()
    apply(repo, change)
    renamed = export_xml(repo, env="uat")
    assert renamed != expected
    apply(repo, rename_job(repo, f"{job.folder}/{job.job}_RENAMED", job.job))
    assert export_xml(repo, env="uat") == expected

    folder = job.folder
    apply(repo, rename_folder(repo, folder, folder + "_X"))
    apply(repo, rename_folder(repo, folder + "_X", folder))
    assert export_xml(repo, env="uat") == expected
    print(
        f"rename-job preview on the real repo: {preview_seconds:.2f}s, {len(change.edits)} files"
    )
