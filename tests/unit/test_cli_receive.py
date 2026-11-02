"""ctmchain receive and ctmchain env learn: an export of one environment taken in."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.repo import load_repo
from tests.support.envexports import both, constants_repo, job, to_prod
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
