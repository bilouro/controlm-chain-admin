"""Links as the source of truth: nodes reference link ids, names live in links.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.links import load_links, rebuild_links
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.rawxml import filter_applications
from tests.support.samples import SAMPLE_EXPORT
from tests.unit.test_repo_ops import snapshot

APP = "P77_RISK_ENGINE"
PREFIXES = ("P77", "RQ_", "RC_")
F = "folders/P77_INGEST_DAILY"


def _import(tmp_path: Path, data: bytes = SAMPLE_EXPORT) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=PREFIXES)
    import_xml(repo, data, env="uat")
    return repo


def _read(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]


def test_nodes_reference_links_by_id_instead_of_carrying_the_condition_name(
    tmp_path: Path,
) -> None:
    _import(tmp_path)

    load = _read(tmp_path / F / "jobs/P77_INGEST_LOAD.json")
    folder = _read(tmp_path / F / "folder.json")

    assert load["INCOND"] == [
        {"link": "P77_INGEST_INIT-P77_INGEST_LOAD_OK", "ODATE": "ODAT", "AND_OR": "A"}
    ]
    assert load["OUTCOND"] == [
        {"link": "P77_INGEST_INIT-P77_INGEST_LOAD_OK", "ODATE": "ODAT", "SIGN": "-"}
    ]
    assert folder["INCOND"] == [
        {"link": "P77_PRICING-P77_INGEST_DAILY_OK", "ODATE": "ODAT", "AND_OR": "A"}
    ]
    assert "NAME" not in json.dumps(load["INCOND"])


def test_docond_entries_reference_links_too(tmp_path: Path) -> None:
    _import(tmp_path, ANOMALY_EXPORT)

    b = _read(tmp_path / "folders/P77_CHAIN/jobs/P77_B.json")

    assert b["ON"][0]["children"] == [
        {"tag": "DOCOND", "link": "P77_B-P77_C_OK", "ODATE": "ODAT", "SIGN": "+"}
    ]


def test_links_json_holds_the_names_in_the_consumer_folder(tmp_path: Path) -> None:
    _import(tmp_path)

    links = _read(tmp_path / F / "links.json")

    assert links == {
        "links": {
            "P77_INGEST_INIT-P77_INGEST_LOAD_OK": {"name": "P77_INGEST_INIT-P77_INGEST_LOAD_OK"},
            "P77_PRICING-P77_INGEST_DAILY_OK": {"name": "P77_PRICING-P77_INGEST_DAILY_OK"},
        }
    }
    index = _read(tmp_path / F / "index.json")
    assert index["derived"] is True
    assert [e["id"] for e in index["links"]] == list(links["links"])


def test_export_with_original_names_is_byte_identical(tmp_path: Path) -> None:
    repo = _import(tmp_path)

    assert export_xml(repo, env="uat") == filter_applications(SAMPLE_EXPORT, {APP})


def test_renaming_a_link_in_links_json_changes_every_occurrence_on_export(tmp_path: Path) -> None:
    repo = _import(tmp_path)
    path = tmp_path / F / "links.json"
    data = _read(path)
    data["links"]["P77_INGEST_INIT-P77_INGEST_LOAD_OK"]["name"] = "P77_INIT-P77_LOAD_DONE"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    out = export_xml(repo, env="uat")

    assert out.count(b'NAME="UP77_INIT-UP77_LOAD_DONE"') == 3  # OUTCOND +, INCOND, OUTCOND -
    assert b"UP77_INGEST_INIT-UP77_INGEST_LOAD_OK" not in out


def test_export_fails_on_a_reference_to_an_unknown_link(tmp_path: Path) -> None:
    repo = _import(tmp_path)
    path = tmp_path / F / "jobs/P77_INGEST_LOAD.json"
    data = _read(path)
    data["INCOND"][0]["link"] = "NOPE"
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")

    with pytest.raises(ModelError, match="NOPE"):
        export_xml(repo, env="uat")


def test_standard_names_follow_the_endpoints_and_leave_externals_alone(tmp_path: Path) -> None:
    repo = _import(tmp_path, ANOMALY_EXPORT)

    out = export_xml(repo, env="uat", names="standard")

    assert b'NAME="UP77_C-UP77_D_OK"' in out  # was the stale UP77_OLDNAME-UP77_D_OK
    assert b"UP77_OLDNAME" not in out
    assert b'NAME="UP77_GHOST-UP77_E_OK"' in out  # dangling/external: untouched
    assert b'NAME="WEIRD_NAME"' in out  # no endpoints known: untouched
    assert b'NAME="UP77_A-UP77_B_OK"' in out  # already standard
    assert export_xml(repo, env="uat") == filter_applications(
        ANOMALY_EXPORT, {APP}
    )  # original still intact


def test_standard_names_disambiguate_two_links_that_would_collide(tmp_path: Path) -> None:
    # a second folder with the same job names, whose conditions use the A-TO-B pattern: distinct
    # link ids that both standardize to P77_A-P77_B_OK
    second = ANOMALY_EXPORT.replace(b"UP77_CHAIN", b"UP77_CHAIN2").replace(b"_OK", b"")
    second = second.replace(b'NAME="UP77_A-UP77_B"', b'NAME="UP77_A-TO-UP77_B"')
    repo = init_repo(tmp_path, APP, ("uat",), prefixes=PREFIXES)
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    import_xml(repo, second, env="uat")

    out = export_xml(repo, env="uat", names="standard")

    assert out.count(b'NAME="UP77_A-UP77_B_OK"') == 0
    assert b'NAME="UP77_CHAIN_UP77_A-UP77_B_OK"' in out
    assert b'NAME="UP77_CHAIN2_UP77_A-UP77_B_OK"' in out


def test_a_condition_shared_by_two_folders_is_one_link_and_keeps_its_name(tmp_path: Path) -> None:
    second = ANOMALY_EXPORT.replace(b"UP77_CHAIN", b"UP77_CHAIN2")  # same condition names
    repo = init_repo(tmp_path, APP, ("uat",), prefixes=PREFIXES)
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    import_xml(repo, second, env="uat")

    links = load_links(repo)
    out = export_xml(repo, env="uat", names="standard")

    assert links["P77_A-P77_B_OK"].kind == "fan_in"  # two producers, two consumers: shared
    assert out.count(b'NAME="UP77_A-UP77_B_OK"') == 6  # a name policy never splits a link


def test_reimport_keeps_everything_identical(tmp_path: Path) -> None:
    repo = _import(tmp_path, ANOMALY_EXPORT)
    before = snapshot(tmp_path)

    import_xml(repo, export_xml(repo, env="uat"), env="uat")

    assert snapshot(tmp_path) == before


def test_cli_export_names_flag_and_links_listing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _import(tmp_path, ANOMALY_EXPORT)
    out = tmp_path / "std.xml"

    assert (
        main(
            [
                "export",
                "--repo",
                str(tmp_path),
                "--env",
                "uat",
                "--names",
                "standard",
                "-o",
                str(out),
            ]
        )
        == 0
    )
    assert b'NAME="UP77_C-UP77_D_OK"' in out.read_bytes()
    capsys.readouterr()
    assert main(["links", "--name", "P77_OLDNAME-P77_D_OK", "--repo", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert "P77_OLDNAME-P77_D_OK" in text and "standard: P77_C-P77_D_OK" in text


def test_ids_stay_stable_when_a_renamed_export_is_imported_again(tmp_path: Path) -> None:
    repo = _import(tmp_path)
    path = tmp_path / F / "links.json"
    data = _read(path)
    data["links"]["P77_INGEST_INIT-P77_INGEST_LOAD_OK"]["name"] = "P77_INIT-P77_LOAD_DONE"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    rebuild_links(repo)
    before = snapshot(tmp_path)

    import_xml(repo, export_xml(repo, env="uat"), env="uat")

    assert snapshot(tmp_path) == before  # same link id, same name, same node references


def test_a_legacy_links_json_is_ignored_on_reimport(tmp_path: Path) -> None:
    repo = _import(tmp_path)
    (tmp_path / F / "links.json").write_text(
        json.dumps({"derived": True, "links": [{"name": "X"}]}) + "\n", encoding="utf-8"
    )

    import_xml(repo, SAMPLE_EXPORT, env="uat")

    assert export_xml(repo, env="uat") == filter_applications(SAMPLE_EXPORT, {APP})
