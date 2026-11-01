"""Letter rule on the real export: neutral repo, identical export, other-environment export."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.repo import init_repo
from tests.realdata.test_import_export import _main_application
from tests.support.rawxml import filter_applications, split_folders

pytestmark = pytest.mark.realdata

ENVS = ("test", "uat", "bench", "prod")


def _prefixes(application: str) -> tuple[str, ...]:
    """The application code is the first token of APPLICATION; resources use RQ_/RC_."""
    return (application.split("_")[0], "RQ_", "RC_")


def test_import_with_the_letter_rule_gives_neutral_names_and_identical_export(
    uat_export: Path, tmp_path: Path
) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    repo = init_repo(tmp_path, app, ENVS, prefixes=_prefixes(app))

    report = import_xml(repo, data, env="uat")

    letter = "U"
    code = _prefixes(app)[0]
    dirs = sorted(p.name for p in (tmp_path / "folders").iterdir())
    assert dirs and all(not d.startswith(letter + code) for d in dirs), "folder dirs are neutral"
    assert sum(d.startswith(code) for d in dirs) == len(dirs)
    assert export_xml(repo, env="uat") == filter_applications(data, {app})
    # the report is informative, never a failure: print counts for the PoC record
    print(
        f"folders={len(report.folders)} jobs={report.jobs}",
        f"literal_marks={len(report.literal_marks)}",
        f"suspicious={len(report.suspicious_values)}",
        f"duplicate_jobnames={len(report.duplicate_job_names)}",
    )


def test_export_for_another_environment_moves_every_prefixed_name(
    uat_export: Path, tmp_path: Path
) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    code = _prefixes(app)[0]
    repo = init_repo(tmp_path, app, ENVS, prefixes=_prefixes(app))
    import_xml(repo, data, env="uat")

    prod = export_xml(repo, env="prod")

    folder_names = re.findall(rb'FOLDER_NAME="([^"]*)"', prod)
    assert folder_names and all(n.startswith(b"P" + code.encode()) for n in folder_names)
    assert len(folder_names) == len(
        [f for f in split_folders(data).folders if f.application == app]
    )
    assert len(prod) == len(filter_applications(data, {app})), "same length: letters swapped 1:1"
