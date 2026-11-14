"""New values for the map: what a branch has that no entry of the map says for its environment.

After a refresh that renamed the user of uat everywhere, the map still says the old one and a
comparison with production counts every job as different. The new value is found, the entry it
belongs to is suggested, and choosing it (or a new entry, the other environments to fill) puts
the comparison back where it was. Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.envmap import read_map
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.mapcheck import (
    adopt_value,
    apply_follow_everywhere,
    follow_entry,
    follow_everywhere,
    new_values,
    set_entry_value,
    survey,
)
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.refresh import refresh, render_text
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from tests.support.envexports import job
from tests.support.fourenvs import (
    CHAIN,
    USERS,
    export_of,
    four_branches,
    two_users_in,
    with_map,
)
from tests.support.gitrepo import commit_all, git, plain_git_identity

UAT, BENCH = "env/uat", "env/bench"
RENAMED = "aup77svc"  # the new user of uat's processes


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def _repo(tmp_path: Path) -> ChainRepo:
    repo = four_branches(tmp_path)
    with_map(repo)
    return load_repo(repo.root)


def _renamed(old: str = USERS["uat"], new: str = RENAMED) -> bytes:
    """uat's export with one user replaced everywhere, as a mass change in Control-M."""
    return export_of("uat").replace(f'RUN_AS="{old}"'.encode(), f'RUN_AS="{new}"'.encode())


def _jobs_differing(repo: ChainRepo) -> int:
    return int(compare(repo.root, "main", UAT).summary()["jobs"]["modified"])


def test_a_user_renamed_everywhere_is_found_and_put_back_into_its_entry(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = _jobs_differing(repo)

    refresh(repo, _renamed(), source="uat.xml", apply=True)
    repo = load_repo(repo.root)  # on env/uat, which the refresh checked out
    broken = _jobs_differing(repo)
    env, found = new_values(repo)

    assert broken > before  # the map does not know the new user: every job differs
    assert env == "uat"
    (new,) = found
    assert (new.key, new.value, new.inline) == ("RUN_AS", RENAMED, False)
    assert new.places == len(survey(repo.root).followers.get("run_as.1", ())) or new.places > 3
    assert new.suggested == "run_as.1"  # the other environments have run_as.1's values there
    assert "run_as.1" in new.candidates

    done = adopt_value(repo, "RUN_AS", RENAMED, entry="run_as.1")

    assert (done["entry"], done["old"], done["new"], done["left"]) == (
        "run_as.1", USERS["uat"], RENAMED, 0,
    )  # fmt: skip
    assert read_map(repo.root, repo.config).named("run_as.1").values["uat"] == RENAMED
    assert new_values(load_repo(repo.root))[1] == []
    assert _jobs_differing(load_repo(repo.root)) == before


def test_a_user_renamed_everywhere_changes_every_entry_that_had_it(tmp_path: Path) -> None:
    """run_as.1 and run_as.2 both have uat's process user (they differ in bench): renamed in
    all of uat, both take the new one, or run_as.2's jobs would differ."""
    repo = four_branches(tmp_path, change=two_users_in("bench"))
    with_map(repo)
    refresh(load_repo(repo.root), export_of("uat"), source="uat.xml", apply=True)  # as exported
    repo = load_repo(repo.root)
    before = _jobs_differing(repo)
    refresh(repo, _renamed(), source="uat.xml", apply=True)
    repo = load_repo(repo.root)
    (new,) = new_values(repo)[1]

    done = adopt_value(repo, "RUN_AS", RENAMED, entry=new.suggested)

    envmap = read_map(repo.root, repo.config)
    assert done["entries"] == ["run_as.1", "run_as.2"]
    assert envmap.named("run_as.2").values["uat"] == RENAMED
    assert _jobs_differing(load_repo(repo.root)) == before


def test_places_where_two_environments_had_the_same_user_get_a_new_entry_of_their_own(
    tmp_path: Path,
) -> None:
    """Where production and uat both ran a job as the same user, nothing varied there; renamed
    in uat, those places vary in a way no entry says, though the new name is in the map now.
    They are listed too, and their new entry takes the values they have."""
    shared = USERS["uat"]

    def same_user(env: str, data: bytes) -> bytes:
        if env == "uat":
            return data
        return job(data, f"{'PEB'[['prod', 'egma', 'bench'].index(env)]}P77_B".encode(),
                   f'RUN_AS="{USERS[env]}"'.encode(), f'RUN_AS="{shared}"'.encode())  # fmt: skip

    repo = four_branches(tmp_path, change=same_user)  # P77_B runs as uat's user everywhere
    with_map(repo)
    refresh(load_repo(repo.root), export_of("uat"), source="uat.xml", apply=True)
    before = _jobs_differing(load_repo(repo.root))
    refresh(load_repo(repo.root), _renamed(), source="uat.xml", apply=True)
    repo = load_repo(repo.root)

    found = new_values(repo)[1]
    renamed = next(v for v in found if v.suggested == "run_as.1")
    adopt_value(repo, "RUN_AS", RENAMED, entry="run_as.1")
    # P77_B: uat's new name here, the old one in the other environments
    (combination,) = new_values(load_repo(repo.root))[1]

    assert renamed.places > 1 and combination.places == 1
    assert combination.known and combination.suggested is None
    assert combination.others == {"prod": shared, "egma": shared, "bench": shared}
    done = adopt_value(load_repo(repo.root), "RUN_AS", RENAMED, entry=None)
    entry = read_map(repo.root, repo.config).named(done["entry"])
    assert dict(entry.values) == {"prod": shared, "uat": RENAMED, "egma": shared, "bench": shared}
    assert done["to_fill"] == []
    assert _jobs_differing(load_repo(repo.root)) == before
    assert new_values(load_repo(repo.root))[1] == []


def test_a_new_entry_takes_what_its_places_have_and_the_rest_is_left_to_fill(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    refresh(repo, _renamed(), source="uat.xml", apply=True)
    repo = load_repo(repo.root)

    done = adopt_value(repo, "RUN_AS", RENAMED, entry=None)
    entry = read_map(repo.root, repo.config).named(done["entry"])

    # every place of the new user has the same user in each other environment: taken
    assert dict(entry.values) == {"prod": USERS["prod"], "uat": RENAMED, "egma": USERS["egma"],
                                  "bench": USERS["bench"]}  # fmt: skip
    assert done["old"] is None and done["to_fill"] == []
    assert new_values(load_repo(repo.root))[1] == []

    set_entry_value(load_repo(repo.root), done["entry"], "prod", None)
    left = read_map(repo.root, repo.config).named(done["entry"])
    assert "prod" not in left.values  # to fill
    set_entry_value(load_repo(repo.root), done["entry"], "prod", USERS["prod"])
    assert read_map(repo.root, repo.config).named(done["entry"]).values["prod"] == USERS["prod"]


def test_the_old_value_still_used_elsewhere_is_said(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    one_job = job(export_of("uat"), b"UP77_B", f'RUN_AS="{USERS["uat"]}"'.encode(),
                  f'RUN_AS="{RENAMED}"'.encode())  # fmt: skip
    refresh(repo, one_job, source="uat.xml", apply=True)
    repo = load_repo(repo.root)

    done = adopt_value(repo, "RUN_AS", RENAMED, entry="run_as.1")

    assert done["left"] > 0  # the other jobs still run as the old user: unexplained now
    assert done["entries"] == ["run_as.1"]  # a rename in part: the entry chosen only


def test_choosing_is_checked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    git(repo.root, "switch", "-q", UAT)
    repo = load_repo(repo.root)

    with pytest.raises(ChainError, match="not an entry of RUN_AS"):
        adopt_value(repo, "RUN_AS", RENAMED, entry="nodeid.1")
    with pytest.raises(ChainError, match="no entry called"):
        adopt_value(repo, "RUN_AS", RENAMED, entry="run_as.9")
    with pytest.raises(ChainError, match="unknown environment"):
        set_entry_value(repo, "run_as.1", "nowhere", "x")


def test_the_refresh_runs_the_analysis_and_says_what_it_found(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    done = refresh(repo, _renamed(), source="uat.xml", apply=True)
    preview = refresh(load_repo(repo.root), export_of("uat"), source="uat.xml")

    assert [(v["key"], v["value"]) for v in done.new_values] == [("RUN_AS", RENAMED)]
    assert done.to_json()["new_values"][0]["suggested"] == "run_as.1"
    assert "1 new value for the map (RUN_AS " in render_text(done)
    assert "ctmchain envmap new-values" in render_text(done)
    assert preview.new_values == ()  # only once applied: the branches as committed


def test_the_commands_list_choose_and_fill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    refresh(repo, _renamed(), source="uat.xml", apply=True)
    root = str(repo.root)
    capsys.readouterr()

    assert main(["envmap", "new-values", "--repo", root]) == 0
    listed = capsys.readouterr().out
    assert main(["envmap", "adopt", "RUN_AS", RENAMED, "--entry", "run_as.1", "--repo", root]) == 0
    adopted = capsys.readouterr().out
    assert main(["envmap", "new-values", "--repo", root]) == 0
    after = capsys.readouterr().out

    assert f"RUN_AS {RENAMED}" in listed and "suggested: run_as.1" in listed
    assert f"run_as.1: uat {USERS['uat']} -> {RENAMED}" in adopted
    assert "No new value" in after
    assert main(["envmap", "set", "run_as.1", "uat", USERS["uat"], "--repo", root]) == 0
    assert main(["envmap", "set", "run_as.1", "egma", "--clear", "--repo", root]) == 0
    values = read_map(repo.root, repo.config).named("run_as.1").values
    assert values["uat"] == USERS["uat"] and "egma" not in values


# ---------------------------------------------------------------- following, honestly


def _two_wrong(tmp_path: Path, envs: tuple[str, ...] = ("uat", "bench")) -> ChainRepo:
    """P77_B runs as other users in uat and in bench: the derived map has an entry of its
    own for it, run_as.2, which differs from run_as.1 in two environments."""

    def change(env: str, data: bytes) -> bytes:
        if env not in envs:
            return data
        other = f"{env[0]}x77usr".encode()
        letter = {"uat": b"U", "bench": b"B", "prod": b"P", "egma": b"E"}[env]
        return job(data, letter + b"P77_B", f'RUN_AS="{USERS[env]}"'.encode(),
                   b'RUN_AS="' + other + b'"')  # fmt: skip

    repo = four_branches(tmp_path, change=change)
    with_map(repo)
    return load_repo(repo.root)


def test_a_follow_says_the_environments_left_and_the_places_are_counted_half_way(
    tmp_path: Path,
) -> None:
    repo = _two_wrong(tmp_path)
    git(repo.root, "switch", "-q", BENCH)
    repo = load_repo(repo.root)

    change = follow_entry(repo, "run_as.2", "run_as.1")
    apply(repo, change)
    commit_all(repo.root, "follow(bench): run_as.2 -> run_as.1")  # the subject it says to use
    seen = survey(repo.root)

    assert any("also differ in uat" in w and "env/uat" in w for w in change.warnings)
    assert any("once committed" in w for w in change.warnings)
    assert any('commit it as "follow(bench): run_as.2 -> run_as.1"' in w for w in change.warnings)
    assert seen.counts().get("run_as.2", 0) == 0
    (half,) = seen.halfway
    assert (half.entries, half.places) == (("run_as.1", "run_as.2"), 1)
    assert half.like == {"prod": "run_as.1", "uat": "run_as.2", "egma": "run_as.1",
                         "bench": "run_as.1"}  # fmt: skip
    assert seen.to_json()["halfway"] == [half.to_json()]


def test_a_follow_in_every_environment_where_the_two_entries_differ(tmp_path: Path) -> None:
    """The jobs of run_as.2 follow run_as.1 in uat and in bench at once: one commit on the
    branch of each, and the counts move."""
    repo = _two_wrong(tmp_path)
    git(repo.root, "switch", "-q", BENCH)
    before = survey(repo.root).counts()["run_as.1"]

    plan = follow_everywhere(load_repo(repo.root), "run_as.2", "run_as.1")
    done = apply_follow_everywhere(load_repo(repo.root), "run_as.2", "run_as.1")
    seen = survey(repo.root)

    assert [(f.env, f.branch, f.places, f.protected) for f in plan] == [
        ("uat", UAT, 1, False), ("bench", BENCH, 1, False),
    ]  # fmt: skip
    assert [(d["env"], bool(d["commit"])) for d in done] == [("uat", True), ("bench", True)]
    assert git(repo.root, "log", "-1", "--format=%s", UAT) == "follow(uat): run_as.2 -> run_as.1"
    assert git(repo.root, "status", "--porcelain") == ""  # bench, checked out, committed too
    assert git(repo.root, "branch", "--show-current") == BENCH
    assert seen.counts().get("run_as.2", 0) == 0 and seen.counts()["run_as.1"] == before + 1
    assert seen.halfway == ()


def test_production_is_not_edited_here_and_is_said(tmp_path: Path) -> None:
    repo = _two_wrong(tmp_path, envs=("prod", "uat", "bench"))
    git(repo.root, "switch", "-q", UAT)

    plan = follow_everywhere(load_repo(repo.root), "run_as.2", "run_as.1")
    done = apply_follow_everywhere(load_repo(repo.root), "run_as.2", "run_as.1")

    prod = next(f for f in plan if f.env == "prod")
    assert (prod.branch, prod.protected, prod.places) == ("main", True, 1)
    assert [d["env"] for d in done if d["commit"]] == ["uat", "bench"]
    assert next(d for d in done if d["env"] == "prod")["commit"] is None
    (half,) = survey(repo.root).halfway  # production still has the old user
    assert half.like["prod"] == "run_as.2"


def test_a_follow_everywhere_waits_for_uncommitted_files(tmp_path: Path) -> None:
    repo = _two_wrong(tmp_path)
    git(repo.root, "switch", "-q", BENCH)
    (repo.root / "folders" / CHAIN / "jobs" / "P77_A.json").write_text("{}\n", "utf-8")

    with pytest.raises(ChainError, match="uncommitted"):
        apply_follow_everywhere(load_repo(repo.root), "run_as.2", "run_as.1")
    assert git(repo.root, "log", "-1", "--format=%s", UAT).startswith("refresh(uat)")


def test_the_follow_command_works_everywhere_unless_told_here(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _two_wrong(tmp_path)
    git(repo.root, "switch", "-q", BENCH)
    root = str(repo.root)
    capsys.readouterr()

    assert main(["envmap", "follow", "run_as.2", "run_as.1", "--repo", root]) == 0
    preview = capsys.readouterr().out
    assert main(["envmap", "follow", "run_as.2", "run_as.1", "--repo", root, "--apply"]) == 0
    applied = capsys.readouterr().out

    assert "uat (env/uat): 1 place(s), RUN_AS ux77usr -> aup77proc" in preview
    assert "bench (env/bench): 1 place(s)" in preview and "--apply" in preview
    assert "Committed on env/uat: follow(uat): run_as.2 -> run_as.1" in applied
    assert "Committed on env/bench: follow(bench): run_as.2 -> run_as.1" in applied
