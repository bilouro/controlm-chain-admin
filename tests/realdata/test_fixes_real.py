"""Fixes on the real chain: every offered fix of two kinds, applied as one batch, clears them."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import pytest

from controlm_chain_admin.core.fixes import by_kind, fixes_for
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.refactor import apply, run_operation
from controlm_chain_admin.core.repo import init_repo
from controlm_chain_admin.core.validate import validate
from tests.realdata.test_environments import _prefixes
from tests.realdata.test_import_export import _main_application

pytestmark = pytest.mark.realdata


def test_batch_of_fixes_clears_those_findings(uat_export: Path, tmp_path: Path) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    repo = init_repo(tmp_path, app, ("uat", "prod"), prefixes=_prefixes(app))
    import_xml(repo, data, env="uat")
    findings = validate(repo).findings
    started = time.perf_counter()
    fixes = fixes_for(repo, findings)
    offering = time.perf_counter() - started
    choice = {"never-cleaned": "add-cleanup", "stale-name": "standard-name"}
    changes, skipped = by_kind(findings, fixes, choice)

    started = time.perf_counter()
    change = run_operation(repo, "batch", {"changes": changes})
    batching = time.perf_counter() - started
    apply(repo, change)

    left = Counter(f.code for f in validate(repo).findings)
    before = Counter(f.code for f in findings)
    assert left["never-cleaned"] == 0
    assert left["stale-name"] <= len([s for s in skipped if s.code == "stale-name"])
    assert export_xml(repo, "uat")  # still exports
    assert offering < 10 and batching < 120
    print(
        f"fixes: {offering:.2f}s to offer, {batching:.1f}s for {len(changes)} changes; "
        f"never-cleaned {before['never-cleaned']} -> 0, stale-name {before['stale-name']} -> "
        f"{left['stale-name']}, skipped {len(skipped)}"
    )
