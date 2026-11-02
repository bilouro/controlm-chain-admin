"""Branch comparison on the real chain: a few edits on a branch are found, nothing else is."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.refactor import apply, rename_job, set_attributes
from controlm_chain_admin.core.repo import init_repo
from tests.realdata.test_environments import _prefixes
from tests.realdata.test_import_export import _main_application
from tests.support.gitrepo import commit_all, git

pytestmark = pytest.mark.realdata


def test_compare_finds_only_what_the_branch_changed(uat_export: Path, tmp_path: Path) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    git(tmp_path, "init", "-q", "-b", "develop")
    repo = init_repo(tmp_path, app, ("uat", "prod"), prefixes=_prefixes(app))
    import_xml(repo, data, env="uat")
    commit_all(repo.root, "import")
    git(repo.root, "checkout", "-q", "-b", "feature")
    edge = next(link for link in load_links(repo).values() if link.kind == "edge")
    producer, consumer = edge.producers[0], edge.consumers[0]
    assert producer.job is not None
    apply(repo, rename_job(repo, str(producer), producer.job + "_RENAMED"))
    commit_all(repo.root, "rename")
    apply(repo, set_attributes(repo, str(consumer), {"DESCRIPTION": "changed on the branch"}))
    commit_all(repo.root, "describe")

    started = time.perf_counter()
    result = compare(repo.root, "develop", "feature")
    seconds = time.perf_counter() - started

    kinds = {j.node: j.change for j in result.jobs}
    assert kinds[f"{producer.folder}/{producer.job}_RENAMED"] == "renamed"
    assert kinds[str(consumer)] == "modified"
    assert len(result.jobs) <= 6, kinds  # the renamed job, the edited one and their peers
    assert len(result.commits) == 2
    assert seconds < 30
    print(f"compare on the real repo: {seconds:.2f}s, {len(result.jobs)} jobs changed")
