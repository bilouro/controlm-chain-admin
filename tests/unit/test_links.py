"""Links derived from the conditions on nodes: collection, grouping, index on disk."""

from __future__ import annotations

import json
from pathlib import Path

from controlm_chain_admin.core.links import (
    Condition,
    Link,
    NodeRef,
    build_links,
    collect_conditions,
    rebuild_links,
)
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"
PREFIXES = ("P77", "RQ_", "RC_")


def _import(tmp_path: Path, data: bytes = SAMPLE_EXPORT) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=PREFIXES)
    import_xml(repo, data, env="uat")
    return repo


def test_noderef_text_form_round_trips_for_jobs_and_folders() -> None:
    job = NodeRef("P77_F", "P77_J")
    folder = NodeRef("P77_F")

    assert str(job) == "P77_F/P77_J" and NodeRef.parse("P77_F/P77_J") == job
    assert str(folder) == "P77_F/" and NodeRef.parse("P77_F/") == folder


def test_collect_reads_static_conditions_and_docond_from_the_repository(tmp_path: Path) -> None:
    repo = _import(tmp_path, ANOMALY_EXPORT)

    conditions = collect_conditions(repo)

    b = NodeRef("P77_CHAIN", "P77_B")
    kinds = {(c.kind, c.id) for c in conditions if c.node == b}
    assert kinds == {
        ("in", "P77_A-P77_B_OK"),
        ("out-", "P77_A-P77_B_OK"),
        ("out+", "P77_B-P77_C_OK"),
        ("do+", "P77_B-P77_C_OK"),
    }
    docond = next(c for c in conditions if c.node == b and c.kind == "do+")
    assert docond.on_code == "NOTOK" and docond.odate == "ODAT"
    folder_level = {c.kind for c in conditions if c.node == NodeRef("P77_CHAIN")}
    assert folder_level == {"in", "out-", "out+"}


def test_build_groups_conditions_by_name_into_links() -> None:
    a, b = NodeRef("F", "A"), NodeRef("F", "B")
    conditions = [
        Condition(a, "A-B_OK", "out+", "ODAT"),
        Condition(b, "A-B_OK", "in", "ODAT", and_or="A"),
        Condition(b, "A-B_OK", "out-", "ODAT"),
        Condition(a, "A-B_OK", "do+", "ODAT", on_code="NOTOK"),
    ]

    links = build_links(conditions, {})

    assert list(links) == ["A-B_OK"]
    link = links["A-B_OK"]
    assert link.producers == (a,) and link.consumers == (b,) and link.deleters == (b,)
    assert link.docond_add == ((a, "NOTOK"),) and link.docond_delete == ()
    assert link.odates == ("ODAT",) and link.and_or == ("A",)
    assert link.kind == "edge" and not link.external


def test_link_kinds() -> None:
    a, b, c = NodeRef("F", "A"), NodeRef("F", "B"), NodeRef("F", "C")

    def link(producers: tuple[NodeRef, ...], consumers: tuple[NodeRef, ...]) -> Link:
        return Link("N", "N", producers, consumers, (), (), (), ("ODAT",), ())

    assert link((a,), (b,)).kind == "edge"
    assert link((a, c), (b,)).kind == "fan_in"
    assert link((), (b,)).kind == "dangling" and link((), (b,)).external
    assert link((a,), ()).kind == "unconsumed" and link((a,), ()).external
    assert Link("N", "N", (), (), (b,), (), (), ("ODAT",), ()).kind == "delete_only"


def test_link_with_only_a_docond_producer_is_still_connected() -> None:
    a, b = NodeRef("F", "A"), NodeRef("F", "B")
    link = Link("N", "N", (), (b,), (), ((a, "COMPSTAT EQ 0"),), (), ("ODAT",), ())

    assert link.kind == "edge" and not link.external


def test_import_writes_the_links_index_on_the_consumer_side(tmp_path: Path) -> None:
    _import(tmp_path)

    index = json.loads((tmp_path / "folders/P77_INGEST_DAILY/index.json").read_text("utf-8"))

    assert index["derived"] is True
    names = [entry["name"] for entry in index["links"]]
    assert names == ["P77_INGEST_INIT-P77_INGEST_LOAD_OK", "P77_PRICING-P77_INGEST_DAILY_OK"]
    edge, folder_link = index["links"]
    assert edge["from"] == ["P77_INGEST_DAILY/P77_INGEST_INIT"]
    assert edge["to"] == ["P77_INGEST_DAILY/P77_INGEST_LOAD"]
    assert edge["cleanup"] == ["P77_INGEST_DAILY/P77_INGEST_LOAD"]
    assert edge["kind"] == "edge" and edge["external"] is False
    assert folder_link["to"] == ["P77_INGEST_DAILY/"] and folder_link["from"] == []
    assert folder_link["kind"] == "dangling" and folder_link["external"] is True


def test_rebuild_is_deterministic_and_returns_every_link(tmp_path: Path) -> None:
    repo = _import(tmp_path, ANOMALY_EXPORT)
    first = (tmp_path / "folders/P77_CHAIN/index.json").read_bytes()

    links = rebuild_links(repo)

    assert (tmp_path / "folders/P77_CHAIN/index.json").read_bytes() == first
    assert len(links) == 10
    assert links["P77_B-P77_C_OK"].docond_add == ((NodeRef("P77_CHAIN", "P77_B"), "NOTOK"),)
    assert links["P77_D-P77_NOBODY_OK"].kind == "unconsumed"


def test_a_link_only_deleted_from_an_on_block_still_has_a_home_in_the_index(
    tmp_path: Path,
) -> None:
    data = ANOMALY_EXPORT.replace(
        b'<DOCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" />',
        b'<DOCOND NAME="UP77_ORPHAN_OK" ODATE="ODAT" SIGN="-" />',
    )
    repo = _import(tmp_path, data)

    links = rebuild_links(repo)
    index = json.loads((tmp_path / "folders/P77_CHAIN/index.json").read_text("utf-8"))

    assert links["P77_ORPHAN_OK"].kind == "delete_only"
    assert "P77_ORPHAN_OK" in [entry["name"] for entry in index["links"]]
    assert len(index["links"]) == len(links)
