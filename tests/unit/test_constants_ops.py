"""Constants wired into the repository: define, draft, import --mappings, export, CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.constants import (
    Selector,
    apply_draft,
    build_draft,
    constants_table,
    define_constant,
)
from controlm_chain_admin.core.errors import ConstantConflict, UnresolvedConstant
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.rawxml import filter_applications
from tests.support.samples import SAMPLE_EXPORT
from tests.unit.test_repo_ops import snapshot

APP = "P77_RISK_ENGINE"
ENVS = ("test", "uat", "bench", "prod")
PREFIXES = ("P77", "RQ_", "RC_")
JOB = "folders/P77_INGEST_DAILY/jobs/P77_INGEST_LOAD.json"


def _repo(tmp_path: Path) -> ChainRepo:
    return init_repo(tmp_path, APP, ENVS, prefixes=PREFIXES)


def _read(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]


# ---------------------------------------------------------------- define / table


def test_define_constant_writes_the_binding_and_the_values(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    repo = define_constant(
        repo, "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH", "prod": "PP77_BATCH"}
    )

    chain = _read(tmp_path / "chain.json")
    assert chain["constants"] == {"node.batch": {"attribute": "NODEID"}}
    assert _read(tmp_path / "envs/uat/env.json")["constants"] == {"node.batch": "UP77_BATCH"}
    assert _read(tmp_path / "envs/test/env.json")["constants"] == {"node.batch": None}
    assert constants_table(repo) == {
        "node.batch": {"test": None, "uat": "UP77_BATCH", "bench": None, "prod": "PP77_BATCH"}
    }


def test_define_constant_rejects_conflicts(tmp_path: Path) -> None:
    repo = define_constant(
        _repo(tmp_path), "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH"}
    )

    with pytest.raises(ConstantConflict):  # same name, different selector
        define_constant(repo, "node.batch", Selector("RUN_AS"), {"uat": "x"})
    with pytest.raises(ConstantConflict):  # same selector and same uat value as another constant
        define_constant(repo, "node.other", Selector("NODEID"), {"uat": "UP77_BATCH"})
    with pytest.raises(ConstantConflict):  # attribute governed by the letter rule
        define_constant(repo, "bad", Selector("JOBNAME"), {"uat": "x"})
    with pytest.raises(ConstantConflict):  # unknown environment
        define_constant(repo, "node.x", Selector("NODEID"), {"staging": "x"})


def test_redefining_a_constant_updates_its_values(tmp_path: Path) -> None:
    repo = define_constant(
        _repo(tmp_path), "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH"}
    )

    repo = define_constant(repo, "node.batch", Selector("NODEID"), {"prod": "PP77_BATCH"})

    assert constants_table(repo)["node.batch"]["uat"] == "UP77_BATCH"
    assert constants_table(repo)["node.batch"]["prod"] == "PP77_BATCH"


# ---------------------------------------------------------------- import / export


def test_import_replaces_mapped_values_and_reports_unmapped(tmp_path: Path) -> None:
    repo = define_constant(
        _repo(tmp_path), "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH"}
    )
    repo = define_constant(repo, "user.proc", Selector("RUN_AS"), {"uat": "aup77proc"})

    report = import_xml(repo, SAMPLE_EXPORT, env="uat")

    job = _read(tmp_path / JOB)
    assert job["NODEID"] == "@{node.batch}" and job["RUN_AS"] == "@{user.proc}"
    assert report.constants_replaced == 5  # 2 NODEID + 3 RUN_AS in the imported folder
    assert report.unmapped == {}  # the unmapped values were in the skipped folder


def test_export_resolves_constants_and_restores_the_source_environment(tmp_path: Path) -> None:
    repo = define_constant(
        _repo(tmp_path),
        "node.batch",
        Selector("NODEID"),
        {"uat": "UP77_BATCH", "prod": "PP77_BATCH"},
    )
    import_xml(repo, SAMPLE_EXPORT, env="uat")

    assert export_xml(repo, env="uat") == filter_applications(SAMPLE_EXPORT, {APP})
    prod = export_xml(repo, env="prod")
    assert b'NODEID="PP77_BATCH"' in prod and b'NODEID="UP77_BATCH"' not in prod


def test_export_fails_when_the_environment_has_no_value(tmp_path: Path) -> None:
    repo = define_constant(
        _repo(tmp_path), "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH"}
    )
    import_xml(repo, SAMPLE_EXPORT, env="uat")

    with pytest.raises(UnresolvedConstant, match=r"node\.batch"):
        export_xml(repo, env="prod")
    assert b'NODEID="@{node.batch}"' in export_xml(repo, env="prod", allow_unresolved=True)


def test_reimport_with_constants_is_idempotent(tmp_path: Path) -> None:
    repo = define_constant(
        _repo(tmp_path), "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH"}
    )
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    before = snapshot(tmp_path)

    import_xml(repo, export_xml(repo, env="uat"), env="uat")

    assert snapshot(tmp_path) == before


# ---------------------------------------------------------------- draft


def test_build_draft_proposes_names_and_prefills_the_source_environment(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    draft = build_draft(repo, parse_xml(SAMPLE_EXPORT), ["NODEID", "DOMAIL/@DEST"], env="uat")

    assert draft["environment"] == "uat"
    batch = draft["NODEID"]["UP77_BATCH"]
    assert batch["count"] == 2 and batch["as"] == "node.p77_batch"
    assert batch["values"] == {"test": None, "uat": "UP77_BATCH", "bench": None, "prod": None}
    assert draft["DOMAIL/@DEST"]["ops@example.com"]["as"] == "mail.ops"


def test_apply_draft_defines_constants_from_values_or_pattern_and_skips_literals(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    draft = {
        "environment": "uat",
        "NODEID": {
            "UP77_BATCH": {"as": "node.batch", "pattern": "{L}P77_BATCH"},
            "srvu-oth-bat1": {"as": None},
        },
        "RUN_AS": {
            "aup77proc": {"as": "user.proc", "values": {"uat": "aup77proc", "prod": "app77proc"}}
        },
    }

    repo, defined = apply_draft(repo, draft)

    assert defined == ("node.batch", "user.proc")
    table = constants_table(repo)
    assert table["node.batch"] == {
        "test": "TP77_BATCH",
        "uat": "UP77_BATCH",
        "bench": "BP77_BATCH",
        "prod": "PP77_BATCH",
    }
    assert table["user.proc"] == {
        "test": None,
        "uat": "aup77proc",
        "bench": None,
        "prod": "app77proc",
    }


# ---------------------------------------------------------------- CLI


def _init_cli(root: Path) -> None:
    assert (
        main(
            [
                "init",
                "--repo",
                str(root),
                "--application",
                APP,
                "--envs",
                "test=T,uat=U,bench=B,prod=P",
                "--prefixes",
                "P77,RQ_,RC_",
            ]
        )
        == 0
    )


def test_cli_distinct_write_then_import_with_mappings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    _init_cli(root)
    xml = tmp_path / "export.xml"
    xml.write_bytes(SAMPLE_EXPORT)
    draft_file = tmp_path / "mappings.json"

    assert (
        main(
            [
                "distinct",
                "NODEID",
                "RUN_AS",
                "--xml",
                str(xml),
                "--repo",
                str(root),
                "--env",
                "uat",
                "--write",
                str(draft_file),
            ]
        )
        == 0
    )
    draft = _read(draft_file)
    assert draft["NODEID"]["UP77_BATCH"]["values"]["uat"] == "UP77_BATCH"
    draft["NODEID"]["UP77_BATCH"]["pattern"] = "{L}P77_BATCH"
    draft["RUN_AS"]["aup77proc"]["values"]["prod"] = "app77proc"
    draft_file.write_text(json.dumps(draft), encoding="utf-8")
    capsys.readouterr()

    assert (
        main(
            [
                "import",
                str(xml),
                "--repo",
                str(root),
                "--env",
                "uat",
                "--mappings",
                str(draft_file),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "constants" in out.lower()
    assert _read(root / JOB)["NODEID"] == "@{node.p77_batch}"
    assert load_repo(root).load_env("prod").constants["node.p77_batch"] == "PP77_BATCH"


def test_cli_map_and_env_constants(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "repo"
    _init_cli(root)
    capsys.readouterr()

    assert (
        main(
            [
                "map",
                "NODEID",
                "UP77_BATCH",
                "--as",
                "node.batch",
                "--pattern",
                "{L}P77_BATCH",
                "--repo",
                str(root),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "map",
                "RUN_AS",
                "aup77proc",
                "--as",
                "user.proc",
                "--value",
                "uat=aup77proc",
                "--value",
                "prod=app77proc",
                "--repo",
                str(root),
            ]
        )
        == 0
    )
    assert (
        main(["map", "RUN_AS", "aup77proc", "--as", "user.proc", "--repo", str(root)]) == 3
    )  # no values
    capsys.readouterr()
