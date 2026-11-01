"""Constants on the real export: map the main NODEID group, export another environment."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core.constants import Selector, build_draft, define_constant
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.repo import init_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.realdata.test_environments import _prefixes
from tests.realdata.test_import_export import _main_application
from tests.support.rawxml import filter_applications

pytestmark = pytest.mark.realdata

ENVS = ("test", "uat", "bench", "prod")


def test_nodeid_constant_from_a_pattern_round_trips_and_re_letters(
    uat_export: Path, tmp_path: Path
) -> None:
    data = uat_export.read_bytes()
    app = _main_application(data)
    code = _prefixes(app)[0]
    repo = init_repo(tmp_path, app, ENVS, prefixes=_prefixes(app))
    own = filter_applications(data, {app})  # the import only sees this application
    draft = build_draft(repo, parse_xml(own), ["NODEID", "RUN_AS"], env="uat")
    most_common = max(draft["NODEID"].items(), key=lambda kv: kv[1]["count"])[0]
    assert most_common.startswith("U" + code), "the main node group carries the letter"

    repo = define_constant(
        repo,
        "node.batch",
        Selector("NODEID"),
        {env: letter + most_common[1:] for env, letter in repo.env_letters().items()},
    )
    report = import_xml(repo, data, env="uat")

    assert report.constants_replaced == draft["NODEID"][most_common]["count"]
    assert export_xml(repo, env="uat") == filter_applications(data, {app})
    prod = export_xml(repo, env="prod")
    assert len(re.findall(rb'NODEID="P' + code.encode(), prod)) == report.constants_replaced
    print(
        f"nodeid groups={len(draft['NODEID'])} run_as values={len(draft['RUN_AS'])}",
        f"replaced={report.constants_replaced}",
        f"unmapped_nodeid={len(report.unmapped.get('NODEID', ()))}",
    )
