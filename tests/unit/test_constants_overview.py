"""The constants of every environment at a glance: values, what is missing, where each is used."""

from __future__ import annotations

from pathlib import Path

from controlm_chain_admin.core.constants import constants_overview
from controlm_chain_admin.core.overrides import Override, write_overrides
from tests.support.envexports import constants_repo


def test_every_constant_with_its_values_and_uses(tmp_path: Path) -> None:
    repo = constants_repo(tmp_path)
    write_overrides(
        repo, "prod", {"P77_CHAIN/P77_E": Override(attributes={"RUN_AS": "@{user.proc}"})}
    )

    rows = {row.name: row for row in constants_overview(repo)}

    proc = rows["user.proc"]
    assert proc.spec == "RUN_AS" and proc.values == {"uat": "aup77proc", "prod": None}
    assert proc.missing == ("prod",)
    assert proc.uses == 12  # 11 nodes and one exception
    assert proc.nodes[:2] == ("P77_CHAIN/", "P77_CHAIN/P77_A")
    batch = rows["node.batch"]
    assert batch.values == {"uat": "UP77_BATCH", "prod": "PP77_BATCH"} and batch.missing == ()
    assert rows["var.geienv"].spec == "VARIABLE[NAME=%%GEIENV]/@VALUE"
    assert rows["var.geienv"].to_json()["missing"] == ["prod"]
