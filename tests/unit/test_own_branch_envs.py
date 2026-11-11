"""A branch of one's own against another environment: it is read as the environment it holds,
through the letter and the map, like that environment's branch."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.errors import ChainError, GitError
from controlm_chain_admin.core.package import build_package
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.refresh import refresh
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.core.take import items_of, take, takeable
from tests.support.fourenvs import (
    CHAIN,
    HOSTS,
    USERS,
    WEEKLY,
    export_of,
    four_branches,
    uat_ahead,
    with_map,
    without_folder,
)
from tests.support.gitrepo import git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"
MINE = "work/uat-next"
TODAY = "2026-11-11"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def _repo(tmp_path: Path) -> ChainRepo:
    """The four environments with their map, uat ahead, and a branch started from uat's."""
    repo = four_branches(tmp_path, change=uat_ahead)
    with_map(repo)
    git(repo.root, "branch", MINE, UAT)
    return repo


def test_it_is_compared_with_another_environment_as_its_own_would_be(tmp_path: Path) -> None:
    root = _repo(tmp_path).root

    mine, theirs = compare(root, BENCH, MINE), compare(root, BENCH, UAT)

    assert mine.environments == ("bench", "uat") and mine.translation is not None
    assert items_of(mine) == items_of(theirs)
    assert mine.summary() == theirs.summary()
    assert compare(root, "main", MINE).environments == ("prod", "uat")
    assert compare(root, MINE, BENCH).environments == ("uat", "bench")
    with pytest.raises(GitError, match="hold different environments"):
        compare(root, BENCH, MINE, commits=[git(root, "rev-parse", MINE)])


def test_with_the_branch_of_its_own_environment_it_is_two_branches_as_before(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path).root

    same = compare(root, UAT, MINE)

    assert same.environments is None and same.translation is None
    assert not any(same.summary()["jobs"].values())


def test_what_it_has_is_taken_into_another_environment_through_the_map(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    git(repo.root, "switch", "-q", BENCH)
    repo = load_repo(repo.root)

    found = takeable(repo.root, "HEAD", MINE)
    apply(repo, take(repo, BENCH, MINE, [f"job:{CHAIN}/P77_NEW"]))

    assert (found.into, found.source, found.environments) == (BENCH, MINE, ("bench", "uat"))
    taken = read_json(repo.job_file(CHAIN, "P77_NEW"))
    assert (taken["RUN_AS"], taken["NODEID"]) == (USERS["bench"], HOSTS["bench"])


def test_a_branch_of_one_s_own_takes_from_another_environment_too(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    git(repo.root, "switch", "-q", "-c", "work/bench-next", BENCH)
    repo = load_repo(repo.root)

    apply(repo, take(repo, "work/bench-next", UAT, [f"job:{CHAIN}/P77_NEW"]))

    taken = read_json(repo.job_file(CHAIN, "P77_NEW"))
    assert (taken["RUN_AS"], taken["NODEID"]) == (USERS["bench"], HOSTS["bench"])


def test_its_package_for_another_environment_needs_no_env(tmp_path: Path) -> None:
    root = _repo(tmp_path).root

    package = build_package(root, BENCH, MINE, today=TODAY)

    assert package.env == "bench" and WEEKLY in [f.name for f in package.folders]
    xml = package.require_xml()
    assert b'JOBNAME="BP77_NEW"' in xml and USERS["bench"].encode() in xml
    assert not any(word in xml for word in (b"UP77", USERS["uat"].encode(), b"CTMUAT"))
    assert package.filename == f"deploy_bench_work-uat-next_{TODAY}.xml"
    with pytest.raises(ChainError, match="env/bench holds bench"):
        build_package(root, BENCH, MINE, env="prod", today=TODAY)
    with pytest.raises(ChainError, match="which environment"):  # one environment on both sides
        build_package(root, UAT, MINE, today=TODAY)


def test_the_full_export_of_another_environment_makes_the_branch_that_environment(
    tmp_path: Path,
) -> None:
    repo = four_branches(tmp_path, change=uat_ahead)  # on main
    with_map(repo)
    root = repo.root
    git(root, "switch", "-q", "-c", "work/from-prod")
    assert compare(root, UAT, "work/from-prod").environments == ("uat", "prod")

    done = refresh(
        load_repo(root), uat_ahead("uat", export_of("uat")), source="uat.xml", here=True,
        apply=True,
    )  # fmt: skip

    assert done.applied and git(root, "log", "-1", "--format=%s") == "import(uat): uat.xml"
    assert compare(root, "main", "work/from-prod").environments == ("prod", "uat")
    assert items_of(compare(root, BENCH, "work/from-prod")) == items_of(compare(root, BENCH, UAT))


def test_some_folders_of_another_environment_would_leave_the_branch_with_two(
    tmp_path: Path,
) -> None:
    root = four_branches(tmp_path).root  # on main
    git(root, "switch", "-q", "-c", "work/from-prod")
    delivery = without_folder(export_of("uat"), "UP77_INGEST_DAILY")

    with pytest.raises(
        ChainError,
        match="work/from-prod holds prod: some folders of uat would leave it with two "
        "environments; start a branch from env/uat",
    ):
        refresh(load_repo(root), delivery, source="delivery.xml", here=True, partial=True)

    # the whole export first, and then the branch holds uat: a delivery of uat goes onto it
    refresh(load_repo(root), export_of("uat"), source="uat.xml", here=True, apply=True)
    later = refresh(
        load_repo(root), delivery, source="delivery.xml", here=True, partial=True, apply=True
    )
    assert later.partial and later.summary["folders"]["removed"] == 0
