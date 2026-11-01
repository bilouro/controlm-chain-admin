"""The table view on the real chain: complete, consistent and fast enough for the UI."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.relations import all_relations, chain_table
from controlm_chain_admin.core.repo import init_repo
from tests.realdata.test_environments import _prefixes
from tests.realdata.test_import_export import _main_application

pytestmark = pytest.mark.realdata


def test_table_covers_every_folder_and_job_with_consistent_neighbours(
    uat_export: Path, tmp_path: Path
) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    repo = init_repo(tmp_path, app, ("uat", "prod"), prefixes=_prefixes(app))
    report = import_xml(repo, data, env="uat")

    started = time.perf_counter()
    table = chain_table(repo)
    seconds = time.perf_counter() - started

    assert len(table) == len(report.folders)
    assert sum(len(f["jobs"]) for f in table) == report.jobs
    relations = all_relations(repo)
    for node, rel in relations.items():  # every predecessor edge is the mirror of a successor edge
        for pred in rel.predecessors:
            for peer in pred.peers:
                if peer.conditional is None:
                    assert any(s.link == pred.link for s in relations[peer.node].successors), node
    print(f"table: {len(table)} folders, {report.jobs} jobs in {seconds:.2f}s")
    assert seconds < 5
