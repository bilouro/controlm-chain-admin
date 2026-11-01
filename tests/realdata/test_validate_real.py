"""Links and validate on the real export: structural properties and the numbers for the record."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.core.links import rebuild_links
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.repo import init_repo
from controlm_chain_admin.core.validate import validate
from tests.realdata.test_environments import _prefixes
from tests.realdata.test_import_export import _main_application

pytestmark = pytest.mark.realdata

KINDS = ("edge", "fan_in", "dangling", "unconsumed", "delete_only")


def test_links_and_validate_on_the_real_chain(uat_export: Path, tmp_path: Path) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    repo = init_repo(tmp_path, app, ("test", "uat", "bench", "prod"), prefixes=_prefixes(app))
    import_xml(repo, data, env="uat")

    links = rebuild_links(repo)
    report = validate(repo)

    assert len(links) > 1000
    assert all(
        link.consumers or link.all_producers or link.deleters or link.docond_delete
        for link in links.values()
    )
    assert report.links == len(links)
    kinds = {k: sum(1 for link in links.values() if link.kind == k) for k in KINDS}
    codes: dict[str, int] = {}
    for finding in report.findings:
        codes[finding.code] = codes.get(finding.code, 0) + 1
    print(f"links={len(links)} kinds={kinds}")
    print(f"findings={len(report.findings)} by code={dict(sorted(codes.items()))}")
    # one connected business chain: the vast majority of links are plain edges
    assert kinds["edge"] > 0.9 * len(links)
    # every link lives in the index of at least one folder
    index_entries = 0
    for folder_dir in (tmp_path / "folders").iterdir():
        index = json.loads((folder_dir / "index.json").read_text("utf-8"))
        index_entries += len(index["links"])
    assert index_entries >= len(links)
