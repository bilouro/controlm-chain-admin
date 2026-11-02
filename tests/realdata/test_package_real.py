"""The import package on the real chain: two commits on a branch, one of them selected."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.package import build_package
from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.core.repo import init_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.realdata.test_environments import _prefixes
from tests.realdata.test_import_export import _main_application
from tests.support.gitrepo import commit_all, git

pytestmark = pytest.mark.realdata


def test_package_holds_only_the_folders_of_the_selected_commit(
    uat_export: Path, tmp_path: Path
) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    git(tmp_path, "init", "-q", "-b", "develop")
    repo = init_repo(tmp_path, app, ("uat", "prod"), prefixes=_prefixes(app))
    import_xml(repo, data, env="uat")
    commit_all(repo.root, "import")
    git(repo.root, "checkout", "-q", "-b", "feature")
    edges = [link for link in load_links(repo).values() if link.kind == "edge"]
    first = edges[0].consumers[0]
    second = next(e.consumers[0] for e in edges if e.consumers[0].folder != first.folder)
    apply(repo, set_attributes(repo, str(first), {"DESCRIPTION": "first change"}))
    commit_all(repo.root, "first")
    apply(repo, set_attributes(repo, str(second), {"DESCRIPTION": "second change"}))
    picked = commit_all(repo.root, "second")

    started = time.perf_counter()
    package = build_package(repo.root, "develop", "feature", env="uat", commits=[picked])
    seconds = time.perf_counter() - started

    assert [f.name for f in package.folders] == [second.folder]
    assert package.folders[0].reasons == (f"job {second.job} modified",)
    folders = parse_xml(package.require_xml()).root.children
    assert len(folders) == 1 and b"second change" in package.require_xml()
    assert b"first change" not in package.require_xml()
    assert seconds < 60
    print(f"package on the real repo: {seconds:.2f}s, {package.size} bytes")
