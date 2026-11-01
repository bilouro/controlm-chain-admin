"""--dedupe-jobnames on the real export: originals restorable, fewer standard-name collisions."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.links import load_links, standard_names
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.repo import init_repo
from tests.realdata.test_environments import _prefixes
from tests.realdata.test_import_export import _main_application
from tests.support.rawxml import filter_applications

pytestmark = pytest.mark.realdata


def _collisions(root: Path) -> int:
    """Links that standard naming had to prefix with the producer folder."""
    from controlm_chain_admin.core.repo import load_repo

    links = load_links(load_repo(root))
    names = standard_names(links)
    return sum(1 for link_id, name in names.items() if links[link_id].standard_name() != name)


def test_dedupe_on_the_real_export(uat_export: Path, tmp_path: Path) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    plain = init_repo(tmp_path / "plain", app, ("uat", "prod"), prefixes=_prefixes(app))
    import_xml(plain, data, env="uat")
    deduped = init_repo(tmp_path / "dedupe", app, ("uat", "prod"), prefixes=_prefixes(app))

    report = import_xml(deduped, data, env="uat", dedupe_jobnames=True)

    assert report.jobnames_deduped and report.duplicate_job_names == ()
    assert export_xml(deduped, env="uat", jobnames="original") == filter_applications(data, {app})
    exported = export_xml(deduped, env="uat")
    names = re.findall(rb'<JOB [^>]*?JOBNAME="([^"]*)"', exported)
    assert len(names) == len(set(names)), "every exported JOBNAME is unique"
    before, after = _collisions(tmp_path / "plain"), _collisions(tmp_path / "dedupe")
    print(f"deduped={len(report.jobnames_deduped)} standard collisions: {before} -> {after}")
    assert after <= before
