"""ctmchain receive and ctmchain env learn: an export of one environment taken in."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.repo import load_repo
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.envexports import both, constants_repo, fresh_repo, job, to_prod
from tests.support.gitrepo import git, plain_git_identity

C = "P77_CHAIN"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    return constants_repo(tmp_path).root


@pytest.fixture
def export(tmp_path: Path) -> Path:
    path = tmp_path / "prod.xml"
    path.write_bytes(job(to_prod(both()), b"PP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"'))
    return path


def test_receive_shows_the_decisions_and_previews(
    root: Path, export: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["receive", str(export), "--repo", str(root), "--stat"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("prod export: ") and "carry the letter P of prod" in out.splitlines()[0]
    assert "  learn:user.proc  learn [learn|ignore]  user.proc = app77proc (11 uses)" in out
    assert f"  {C}/P77_E@TASKTYPE  change [change|exception|ignore]  Command -> Dummy" in out
    assert "Preview only" in out


def test_receive_shows_a_group_with_the_values_of_its_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plain_git_identity(monkeypatch, tmp_path)
    root = fresh_repo(tmp_path).root
    uat = tmp_path / "uat.xml"
    uat.write_bytes(both())

    assert main(["receive", str(uat), "--repo", str(root), "--stat"]) == 0

    out = capsys.readouterr().out
    assert (
        "  group:NODEID=PP77_BATCH>UP77_BATCH  new [new|exceptions|change|ignore]  "
        "NODEID PP77_BATCH -> UP77_BATCH (9 uses); new: node.p77_batch "
        "(test TP77_BATCH, uat UP77_BATCH, bench BP77_BATCH, prod PP77_BATCH)"
    ) in out
    assert (
        "  group:DOMAIL/@SUBJECT~env  new [new|change|ignore]  DOMAIL/@SUBJECT: the name of the "
        "environment inside the text (1 use); new: env.subject (inline: test TEST, uat UAT, "
        "bench BENCH, prod PROD)"
    ) in out


def test_receive_is_told_a_delivery_is_the_whole_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plain_git_identity(monkeypatch, tmp_path)
    root = fresh_repo(tmp_path).root
    chain = tmp_path / "chain.xml"
    chain.write_bytes(ANOMALY_EXPORT)  # one folder of two

    assert main(["receive", str(chain), "--repo", str(root)]) == 0
    assert "some folders only" in capsys.readouterr().out
    assert main(["receive", str(chain), "--repo", str(root), "--full"]) == 0

    out = capsys.readouterr().out
    assert "full export" in out
    assert "  P77_INGEST_DAILY/#absent  not-here [not-here|keep]" in out


def test_receive_applies_on_a_release_only(
    root: Path, export: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["receive", str(export), "--repo", str(root), "--apply", "--stat",
            "--choose", f"{C}/P77_E@TASKTYPE=exception"]  # fmt: skip
    assert main(args) == 3
    assert "main is protected" in capsys.readouterr().err
    git(root, "switch", "-q", "-c", "release/march")

    assert main(args) == 0

    assert "Applied" in capsys.readouterr().out
    overrides = json.loads((root / "envs/prod/overrides.json").read_text(encoding="utf-8"))
    assert overrides == {f"{C}/P77_E": {"set": {"TASKTYPE": "Dummy"}}}
    assert main(["receive", str(export), "--repo", str(root), "--format", "json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["intake"]["env"] == "prod" and body["applied"] is False


def test_env_learn_writes_only_the_values(
    root: Path, export: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(root, "switch", "-q", "-c", "release/march")

    assert main(["env", "learn", str(export), "--repo", str(root), "--apply", "--stat"]) == 0

    out = capsys.readouterr().out
    assert "user.proc: ? -> app77proc (11 uses)" in out and "var.geienv: ? -> x (1 use)" in out
    assert "envs/prod/env.json" in out
    prod = load_repo(root).load_env("prod").constants
    assert prod["user.proc"] == "app77proc" and prod["var.geienv"] == "x"
    assert not (root / "envs/prod/overrides.json").exists()


def test_env_learn_can_take_some_constants_only(
    root: Path, export: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(root, "switch", "-q", "-c", "release/march")

    args = [
        "env",
        "learn",
        str(export),
        "--repo",
        str(root),
        "--apply",
        "--stat",
        "--only",
        "var.",
    ]
    assert main(args) == 0

    out = capsys.readouterr().out
    assert "var.geienv: ? -> x" in out and "user.proc" not in out
    prod = load_repo(root).load_env("prod").constants
    assert prod["var.geienv"] == "x" and prod.get("user.proc") is None
