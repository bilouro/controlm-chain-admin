"""``ctmchain envmap``: the map of what varies per environment, from the command line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.fourenvs import four_branches
from tests.support.gitrepo import git, plain_git_identity


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def test_the_map_is_derived_shown_and_completed_by_hand(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = str(four_branches(tmp_path).root)

    assert main(["envmap", "show", "--repo", root]) == 0
    out = capsys.readouterr().out
    assert "The map is empty" in out and "letters: prod=P uat=U egma=E bench=B" in out

    assert main(["envmap", "derive", "--repo", root]) == 0
    out = capsys.readouterr().out
    assert (
        "3 new entries from main (prod), env/uat (uat), env/egma (egma), env/bench (bench)" in out
    )
    assert "run_as.1" in out and "11 nodes" in out and "uat=aup77proc" in out
    assert "Nothing written: --apply adds them to the map." in out
    assert git(Path(root), "branch", "--list", "map") == ""

    assert main(["envmap", "derive", "--repo", root, "--apply"]) == 0
    assert "Written on map: 3 entries added" in capsys.readouterr().out
    assert git(Path(root), "log", "-1", "--format=%s", "map") == "map: 3 entries derived"
    assert git(Path(root), "branch", "--show-current") == "main"

    assert main(["envmap", "derive", "--repo", root, "--apply"]) == 0
    assert "Nothing new: the map explains what these keys show." in capsys.readouterr().out

    assert main(["envmap", "suggest", "--repo", root]) == 0
    out = capsys.readouterr().out
    assert "VARIABLE[NAME=%%GEIENV]/@VALUE" in out and "DOMAIL/@SUBJECT" in out
    assert "--text DOMAIL/@SUBJECT" in out

    assert main(["envmap", "derive", "--repo", root, "--text", "DOMAIL/@SUBJECT",
                 "--key", "VARIABLE[NAME=%%GEIENV]/@VALUE", "--min-nodes", "1",
                 "--apply"]) == 0  # fmt: skip
    assert "Written on map: 2 entries added" in capsys.readouterr().out

    assert main(["envmap", "add", "DOMAIL/@DEST", "prod=ops-prod@example.com",
                 "uat=ops@example.com", "--as", "mail.ops", "--repo", root]) == 0  # fmt: skip
    assert "Written on map: mail.ops" in capsys.readouterr().out
    assert main(["envmap", "rename", "geienv.1", "env.code", "--repo", root]) == 0
    assert main(["envmap", "remove", "mail.ops", "--repo", root]) == 0
    capsys.readouterr()

    assert main(["envmap", "show", "--repo", root, "--format", "json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["letters"] == {"prod": "P", "uat": "U", "egma": "E", "bench": "B"}
    assert [(e["name"], e["key"], e.get("inline", False)) for e in shown["entries"]] == [
        ("nodeid.1", "NODEID", False),
        ("run_as.1", "RUN_AS", False),
        ("datacenter.1", "DATACENTER", False),
        ("env.code", "VARIABLE[NAME=%%GEIENV]/@VALUE", False),
        ("subject.1", "DOMAIL/@SUBJECT", True),
    ]
    assert main(["envmap", "suggest", "--repo", root]) == 0
    assert "Nothing else varies" in capsys.readouterr().out


def test_what_is_left_out_is_counted_and_json_says_it_all(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = str(four_branches(tmp_path).root)

    assert (
        main(["envmap", "derive", "--repo", root, "--key", "VARIABLE[NAME=%%GEIENV]/@VALUE"]) == 0
    )
    out = capsys.readouterr().out
    assert "1 set of values left out: fewer than 2 nodes show it (--min-nodes 1 takes it)" in out

    assert main(["envmap", "derive", "--repo", root, "--format", "json"]) == 0
    derived = json.loads(capsys.readouterr().out)
    assert derived["applied"] is False and derived["environments"] == [
        "prod",
        "uat",
        "egma",
        "bench",
    ]
    assert [(e["name"], e["nodes"]) for e in derived["entries"]] == [
        ("nodeid.1", 7), ("run_as.1", 11), ("datacenter.1", 2)
    ]  # fmt: skip


def test_mistakes_are_errors_not_tracebacks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = str(four_branches(tmp_path).root)

    assert main(["envmap", "add", "RUN_AS", "prod", "--repo", root]) == 3
    assert "env=value" in capsys.readouterr().err
    assert main(["envmap", "add", "RUN_AS", "prod=a", "mars=b", "--repo", root]) == 3
    assert "mars" in capsys.readouterr().err
    assert main(["envmap", "remove", "nodeid.9", "--repo", root]) == 3
    assert "no entry" in capsys.readouterr().err
