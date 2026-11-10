"""The whole story of one branch per environment, typed as a person would: the ``ctmchain``
program in a process of its own, a real git repository, four full exports.

    init -> refresh x4 -> a newer export (see, then apply) -> the map -> compare ->
    take (attribute, variable, job, folder, sub-application) -> the import file for a target
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.fourenvs import (
    CHAIN,
    ENVS,
    GEIENV,
    HOSTS,
    INGEST,
    SUBJECT,
    USERS,
    WEEKLY,
    export_of,
    own,
    uat_ahead,
)
from tests.support.gitrepo import APP, git, plain_git_identity

BENCH, EGMA, UAT = "env/bench", "env/egma", "env/uat"


class Shell:
    """``ctmchain`` run in ``root``, as from a terminal."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def run(self, *argv: str, code: int = 0) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "controlm_chain_admin", *argv],
            cwd=self.root, capture_output=True, text=True, check=False,
        )  # fmt: skip
        assert result.returncode == code, f"{argv}: {result.stdout}\n{result.stderr}"
        return result.stdout if code == 0 else result.stderr


@pytest.fixture
def exports(tmp_path: Path) -> dict[str, Path]:
    """One full export per environment; uat is ahead of the others."""
    files = {}
    for env in ENVS:
        files[env] = tmp_path / f"{env}.xml"
        files[env].write_bytes(uat_ahead(env, export_of(env)))
    return files


@pytest.fixture
def shell(tmp_path: Path, exports: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> Shell:
    """A new repository with the four branches, each from its export, and the map derived."""
    plain_git_identity(monkeypatch, tmp_path)
    root = tmp_path / "chains"
    root.mkdir()
    shell = Shell(root)
    shell.run("init", "--application", APP, "--envs", "prod=P,uat=U,egma=E,bench=B",
              "--prefixes", "P77,RQ_,RC_", "--leading-only", "RQ_,RC_")  # fmt: skip
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: the rules")
    for env in ENVS:
        shell.run("refresh", str(exports[env]), "--apply")
    git(root, "switch", "-q", "main")
    shell.run("envmap", "derive", "--key", GEIENV, "--text", SUBJECT, "--min-nodes", "1",
              "--apply")  # fmt: skip
    return shell


def test_each_branch_is_its_environment_and_gives_its_export_back(
    shell: Shell, exports: dict[str, Path], tmp_path: Path
) -> None:
    branches = git(shell.root, "branch", "--format=%(refname:short)").split()
    assert sorted(branches) == [BENCH, EGMA, UAT, "main", "map"]

    for env, branch in (("prod", "main"), ("uat", UAT), ("egma", EGMA), ("bench", BENCH)):
        git(shell.root, "switch", "-q", branch)
        out = tmp_path / f"back-{env}.xml"
        shell.run("export", "--env", env, "-o", str(out))
        assert out.read_bytes() == own(exports[env].read_bytes()), env


def test_a_newer_export_is_seen_before_it_overwrites_the_branch(
    shell: Shell, exports: dict[str, Path], tmp_path: Path
) -> None:
    newer = tmp_path / "bench-2.xml"
    newer.write_bytes(
        exports["bench"].read_bytes().replace(b"/opt/p77/bin/c.ksh", b"/opt/p77/bin/c9.ksh")
    )
    before = git(shell.root, "rev-parse", BENCH)

    seen = shell.run("refresh", str(newer))
    assert "Refresh env/bench (bench) from bench-2.xml" in seen
    assert f"modified job {CHAIN}/P77_C" in seen and "c.ksh -> /opt/p77/bin/c9.ksh" in seen
    assert "Nothing written" in seen and git(shell.root, "rev-parse", BENCH) == before

    shell.run("refresh", str(newer), "--apply")
    assert git(shell.root, "branch", "--show-current") == BENCH
    assert git(shell.root, "rev-parse", f"{BENCH}~1") == before
    assert "env/bench already holds this export: nothing to do." in shell.run(
        "refresh", str(newer)
    )

    # as many times as needed: the first export again puts the branch back as it was
    shell.run("refresh", str(exports["bench"]), "--apply")
    assert git(shell.root, "diff", "--stat", before, BENCH) == ""


def test_the_map_knows_what_varies_and_is_no_environment(shell: Shell) -> None:
    shown = json.loads(shell.run("envmap", "show", "--format", "json"))

    entries = {e["key"]: e["values"] for e in shown["entries"]}
    assert entries["RUN_AS"] == USERS and entries["NODEID"] == HOSTS
    assert git(shell.root, "ls-tree", "--name-only", "map") == "map.json"
    assert git(shell.root, "branch", "--show-current") == "main"


def test_two_environments_compare_by_what_really_differs(shell: Shell) -> None:
    same = shell.run("compare", "main", BENCH)
    assert "No real difference between main and env/bench." in same

    ahead = json.loads(shell.run("compare", "main", UAT, "--format", "json"))
    summary = ahead["summary"]
    assert (summary["folders"]["added"], summary["folders"]["modified"]) == (1, 2)
    assert (summary["jobs"]["added"], summary["jobs"]["modified"]) == (3, 1)
    assert ahead["translation"]["warnings"] == []

    raw = json.loads(shell.run("compare", "main", UAT, "--raw", "--format", "json"))
    assert raw["summary"]["jobs"]["modified"] > summary["jobs"]["modified"]


def test_items_of_every_size_are_taken_into_another_environment(
    shell: Shell, tmp_path: Path
) -> None:
    git(shell.root, "switch", "-q", BENCH)
    listed = shell.run("take", UAT, "--list")
    assert "subapp:P77_BATCH  3 folders that differ" in listed

    def job_of(folder: str, name: str) -> dict[str, object]:
        path = shell.root / "folders" / folder / "jobs" / f"{name}.json"
        return dict(json.loads(path.read_text("utf-8")))

    shell.run("take", UAT, "--item", f"attr:{CHAIN}/P77_A@CMDLINE", "--apply")
    assert job_of(CHAIN, "P77_A")["CMDLINE"] == "/opt/p77/bin/a2.ksh -x"
    shell.run("take", UAT, "--item", f"var:{INGEST}/@%%RETRY", "--apply")
    shell.run("take", UAT, "--item", f"job:{CHAIN}/P77_NEW", "--apply")
    assert job_of(CHAIN, "P77_NEW")["RUN_AS"] == USERS["bench"]
    shell.run("take", UAT, "--item", f"folder:{WEEKLY}", "--apply")
    assert job_of(WEEKLY, "P77_WEEKLY_INIT")["NODEID"] != HOSTS["uat"]
    shell.run("commit", "-m", "feat(bench): what uat has")

    assert "No real difference between env/bench and env/uat." in shell.run("compare", BENCH, UAT)

    # the export of bench now has it all, written as bench writes it
    out = tmp_path / "bench-after.xml"
    shell.run("export", "--env", "bench", "--jobnames", "original", "-o", str(out))
    xml = out.read_bytes()
    assert b'FOLDER_NAME="BP77_WEEKLY_DAILY"' in xml and b'JOBNAME="BP77_NEW"' in xml
    assert b"UP77" not in xml and USERS["uat"].encode() not in xml and b"CTMUAT" not in xml

    # and a whole sub-application in one item, into the next environment
    git(shell.root, "switch", "-q", EGMA)
    shell.run("take", UAT, "--item", "subapp:P77_BATCH", "--apply")
    shell.run("commit", "-m", "feat(egma): the batch of uat")
    assert "No real difference between env/egma and env/uat." in shell.run("compare", EGMA, UAT)


def test_the_import_file_of_chosen_items_for_a_target_changes_no_branch(
    shell: Shell, tmp_path: Path
) -> None:
    tips = git(shell.root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads")
    out = tmp_path / "to-prod.xml"

    said = shell.run("package", "main", UAT, "--take", f"folder:{WEEKLY}", "-o", str(out))

    assert said.startswith("Package env/uat (uat) for prod (main): 1 folder, 1 item taken")
    xml = out.read_bytes()
    assert xml.count(b"<SMART_FOLDER ") == 1 and b'FOLDER_NAME="PP77_WEEKLY_DAILY"' in xml
    assert USERS["prod"].encode() in xml and b"CTMPROD" in xml and b"[P77][PROD]" in xml
    assert b"UP77" not in xml and USERS["uat"].encode() not in xml
    assert git(shell.root, "status", "-s") == ""
    assert tips == git(
        shell.root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads"
    )

    # the trunk is production: nothing is taken into it by hand
    refused = shell.run("take", UAT, "--item", f"folder:{WEEKLY}", "--apply", code=3)
    assert "main" in refused

    # a whole environment's worth: everything uat has and bench has not, for bench
    everything = tmp_path / "to-bench.xml"
    shell.run("package", BENCH, UAT, "-o", str(everything))
    assert everything.read_bytes().count(b"<SMART_FOLDER ") == 3
