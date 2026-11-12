"""``diagnose``: what this machine costs per small file and per git call, and where one real
comparison spends its time. Numbers only: no name of a job or of a folder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.diagnose import diagnose, machine, render_text
from controlm_chain_admin.core.errors import ChainError
from tests.support.fourenvs import CHAIN, four_branches, uat_ahead, with_map
from tests.support.gitrepo import chain_git_repo, git, plain_git_identity


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def _repo(tmp_path: Path) -> Path:
    repo = four_branches(tmp_path, change=uat_ahead)
    with_map(repo)
    return repo.root


def test_the_machine_is_measured_per_small_file_and_per_git_call(tmp_path: Path) -> None:
    probes = machine(tmp_path, files=50, spawns=2)

    assert set(probes) == {"temp_files", "repo_files", "git_spawn", "cpu"}
    for place in ("temp_files", "repo_files"):
        assert probes[place]["files"] == 50
        assert set(probes[place]) >= {"write_ms", "read_ms", "delete_ms"}
        assert all(probes[place][key] >= 0 for key in ("write_ms", "read_ms", "delete_ms"))
    assert probes["git_spawn"]["calls"] == 2 and probes["git_spawn"]["ms"] > 0
    assert probes["cpu"]["ms"] > 0
    assert not list(tmp_path.glob("ctmchain-probe-*"))  # nothing left behind


def test_one_comparison_between_two_environments_by_phase(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    found = diagnose(root, files=20, spawns=1)

    assert (found.base, found.head) == ("main", "env/uat")  # the trunk and the first other one
    run = found.run
    assert run is not None and run.environments == ("prod", "uat")
    assert {"snapshot", "translate", "diff"} <= set(run.timings.phases)
    counts = run.timings.counts
    assert counts["files_written"] > 0 and counts["files_read"] > 0 and counts["git_calls"] > 0
    assert run.seconds >= max(run.timings.phases.values())
    assert run.jobs["added"] == 3 and run.again_seconds is not None and run.again_kept
    assert 0 <= found.files_share <= 1
    assert git(root, "status", "--porcelain") == ""


def test_the_report_has_numbers_and_no_name_of_the_chain(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    found = diagnose(root, "env/bench", "env/uat", files=20, spawns=1)
    text, data = render_text(found), found.to_json()

    assert text.startswith("ctmchain diagnose")
    for line in ("Machine", "One comparison: env/bench with env/uat", "Where the time goes"):
        assert line in text
    assert "once more, right after" in text and "(kept by commit)" in text
    assert "small files" in text and "git call" in text and "the rest (deleting" in text
    assert CHAIN not in text and "P77" not in json.dumps(data)
    assert str(root) not in text and str(tmp_path) not in json.dumps(data)
    assert data["run"]["timings"]["counts"]["files_written"] > 0
    assert data["version"] and data["platform"]["python"]


def test_with_one_tree_for_every_environment_two_refs_are_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = chain_git_repo(tmp_path).root

    with pytest.raises(ChainError, match="name two refs to compare"):
        diagnose(root, files=5, spawns=1)
    found = diagnose(root, "main", "main", files=5, spawns=1)
    assert found.run is not None and found.run.environments is None

    monkeypatch.setenv("CTMCHAIN_NO_CACHE", "1")
    unkept = diagnose(root, "main", "main", files=5, spawns=1)
    assert unkept.run is not None and not unkept.run.again_kept
    assert "kept by commit" not in render_text(unkept)


def test_the_command_prints_the_report_and_writes_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    out_file = tmp_path / "report.json"

    code = main(["diagnose", "--repo", str(root), "--files", "20"])
    text = capsys.readouterr().out
    again = main(["diagnose", "main", "env/uat", "--repo", str(root), "--files", "20",
                  "--format", "json", "-o", str(out_file)])  # fmt: skip

    assert code == 0 and text.startswith("ctmchain diagnose")
    assert again == 0 and json.loads(out_file.read_text("utf-8"))["base"] == "main"
    assert f"Wrote {out_file}" in capsys.readouterr().err
