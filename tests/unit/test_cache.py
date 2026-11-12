"""A comparison of two commits is always the same: it is worked out once and kept by commit."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core import cache
from controlm_chain_admin.core import compare as compare_mod
from controlm_chain_admin.core import package as package_mod
from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.envmap import remove_from_map
from controlm_chain_admin.core.package import build_package
from controlm_chain_admin.core.refresh import refresh
from controlm_chain_admin.core.repo import load_repo
from tests.support.fourenvs import export_of, four_branches, uat_ahead, with_map
from tests.support.gitrepo import git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"
TODAY = "2026-11-12"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = four_branches(tmp_path, change=uat_ahead)
    with_map(repo)
    return repo.root


def _no_more_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """From here on, opening the two sides of a comparison is a failure."""

    def opened(*args: object, **kwargs: object) -> None:
        raise AssertionError("the sides were opened again")

    monkeypatch.setattr(compare_mod, "open_sides", opened)
    monkeypatch.setattr(package_mod, "open_sides", opened)


def _kept(root: Path) -> list[Path]:
    return sorted(cache.directory(root).glob("*")) if cache.directory(root).is_dir() else []


def test_the_same_comparison_again_opens_nothing(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = compare(root, BENCH, UAT)
    _no_more_work(monkeypatch)

    again = compare(root, BENCH, UAT)

    assert again.to_json() == first.to_json() and again == first
    assert len(_kept(root)) == 1
    assert git(root, "status", "--porcelain") == ""  # kept under the git directory


def test_other_options_are_another_comparison(root: Path) -> None:
    plain, raw = compare(root, BENCH, UAT), compare(root, BENCH, UAT, translate=False)
    turned = compare(root, UAT, BENCH)

    assert raw.translation is None and plain.translation is not None
    assert turned.environments == ("uat", "bench")
    assert len(_kept(root)) == 3


def test_a_new_commit_on_a_side_is_compared_anew(root: Path) -> None:
    before = compare(root, BENCH, UAT)

    refresh(load_repo(root), export_of("uat"), source="uat.xml", apply=True)  # uat as bench
    after = compare(root, BENCH, UAT)

    assert before.summary()["jobs"]["added"] == 3 and after.summary()["jobs"]["added"] == 0


def test_another_map_is_compared_anew(root: Path) -> None:
    before = compare(root, BENCH, UAT)

    remove_from_map(load_repo(root), "run_as.1")
    after = compare(root, BENCH, UAT)

    assert after.to_json() != before.to_json()


def test_the_working_tree_is_never_kept(root: Path) -> None:
    compare(root, "main", "WORKTREE")
    compare(root, "WORKTREE", "main")

    assert _kept(root) == []


def test_a_file_that_cannot_be_read_is_worked_out_again(root: Path) -> None:
    first = compare(root, BENCH, UAT)
    (kept,) = _kept(root)
    kept.write_bytes(b"not a result")

    assert compare(root, BENCH, UAT) == first
    assert compare(root, BENCH, UAT) == first  # and kept again, readable


def test_asked_to_work_it_out_anew_it_does_and_keeps_it(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compare(root, BENCH, UAT)
    opened: list[str] = []
    real = compare_mod.open_sides

    def counting(*args: object, **kwargs: object) -> object:
        opened.append("sides")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(compare_mod, "open_sides", counting)
    with cache.fresh():
        compare(root, BENCH, UAT)
    compare(root, BENCH, UAT)

    assert opened == ["sides"]


def test_it_can_be_turned_off(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CTMCHAIN_NO_CACHE", "1")

    compare(root, BENCH, UAT)

    assert _kept(root) == []


def test_only_the_latest_results_are_kept(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "KEEP", 2)

    for base in ("main", BENCH, "env/egma"):
        compare(root, base, UAT)

    assert len(_kept(root)) == 2


def test_a_package_is_kept_like_a_comparison(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = build_package(root, BENCH, UAT, today=TODAY)
    chosen = build_package(root, BENCH, UAT, take=["folder:P77_WEEKLY_DAILY"], today=TODAY)
    later = build_package(root, BENCH, UAT, today="2026-11-13")  # its name has the day
    _no_more_work(monkeypatch)

    again = build_package(root, BENCH, UAT, today=TODAY)

    assert again == first and again.require_xml() == first.require_xml()
    assert chosen.taken == ("folder:P77_WEEKLY_DAILY",) and chosen.xml != first.xml
    assert later.filename != first.filename
