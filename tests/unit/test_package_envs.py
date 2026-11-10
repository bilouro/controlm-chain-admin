"""The import file for one environment with what another environment has: everything that
differs, or the items chosen, written as the target has its names, users and machines."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import ChainError, NothingToPackage
from controlm_chain_admin.core.history import WORKTREE
from controlm_chain_admin.core.package import Package, build_package, save
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from controlm_chain_admin.core.take import take
from tests.support.fourenvs import (
    CHAIN,
    INGEST,
    USERS,
    WEEKLY,
    four_branches,
    two_users_in,
    uat_ahead,
    with_map,
)
from tests.support.gitrepo import git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"
TODAY = "2026-11-10"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def _repo(tmp_path: Path) -> ChainRepo:
    repo = four_branches(tmp_path, change=uat_ahead)
    with_map(repo)
    return repo


def _package(repo: ChainRepo, base: str = BENCH, *take: str, **options: object) -> Package:
    return build_package(repo.root, base, UAT, take=take or None, today=TODAY, **options)  # type: ignore[arg-type]


def _names(package: Package) -> list[str]:
    return [f.name for f in package.folders]


def _nothing_of_uat(xml: bytes) -> bool:
    return not any(
        word in xml for word in (b"UP77", b"URQ_", USERS["uat"].encode(), b"CTMUAT", b"[UAT]")
    )


def test_everything_another_environment_has_goes_as_the_target_writes_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    package = _package(repo)

    assert package.env == "bench" and package.taken is None
    assert set(_names(package)) == {CHAIN, INGEST, WEEKLY}
    xml = package.require_xml()
    assert b'JOBNAME="BP77_NEW"' in xml and b'FOLDER_NAME="BP77_WEEKLY_DAILY"' in xml
    assert b"/opt/p77/bin/a2.ksh -x" in xml and USERS["bench"].encode() in xml
    assert _nothing_of_uat(xml)
    assert package.filename == f"deploy_bench_env-uat_{TODAY}.xml"


def test_the_package_is_for_the_environment_of_the_base(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert _package(repo, env="bench").env == "bench"
    with pytest.raises(ChainError, match="env/bench holds bench"):
        _package(repo, env="prod")


def test_two_branches_of_one_environment_still_need_to_be_told_which(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(ChainError, match="which environment"):
        build_package(repo.root, "main", "main", today=TODAY)


def test_only_what_was_chosen_goes_in_the_package(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = git(repo.root, "rev-parse", BENCH)

    package = _package(repo, BENCH, f"folder:{WEEKLY}")

    assert _names(package) == [WEEKLY] and package.taken == (f"folder:{WEEKLY}",)
    assert package.folders[0].reasons[0] == "folder added"
    xml = package.require_xml()
    assert b'FOLDER_NAME="BP77_WEEKLY_DAILY"' in xml and b"BP77_CHAIN" not in xml
    assert _nothing_of_uat(xml)
    assert package.filename == f"deploy_bench_env-uat_1-item_{TODAY}.xml"
    assert package.to_json()["taken"] == [f"folder:{WEEKLY}"]
    # nothing was touched: neither the branch of the target nor the checkout
    assert git(repo.root, "rev-parse", BENCH) == head
    assert git(repo.root, "status", "-s") == ""
    assert git(repo.root, "branch", "--show-current") == "main"


def test_one_job_brings_its_folder_with_the_rest_as_the_target_has_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    package = _package(repo, BENCH, f"job:{CHAIN}/P77_NEW")

    assert _names(package) == [CHAIN]
    assert package.folders[0].reasons == ("job P77_NEW added",)
    xml = package.require_xml()
    assert b'JOBNAME="BP77_NEW"' in xml
    # the other change of that folder was not taken: the job it was made on is as bench has it
    assert xml.count(b"/opt/p77/bin/a2.ksh -x") == 1 and xml.count(b"/opt/p77/bin/a.ksh") == 1


def test_several_items_and_a_sub_application(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    two = _package(repo, BENCH, f"attr:{CHAIN}/P77_A@CMDLINE", f"var:{INGEST}/@%%RETRY")
    assert set(_names(two)) == {CHAIN, INGEST}
    assert two.filename == f"deploy_bench_env-uat_2-items_{TODAY}.xml"
    assert b"BP77_NEW" not in two.require_xml()

    whole = _package(repo, BENCH, "subapp:P77_BATCH")
    assert whole.require_xml() == _package(repo).require_xml()


def test_it_is_the_file_the_target_branch_would_give_after_taking_the_same(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    items = (f"job:{CHAIN}/P77_NEW", f"folder:{WEEKLY}", f"var:{INGEST}/@%%RETRY")
    direct = _package(repo, BENCH, *items).require_xml()

    git(repo.root, "switch", "-q", BENCH)
    repo = load_repo(repo.root)
    apply(repo, take(repo, BENCH, UAT, items))
    after = build_package(repo.root, BENCH, WORKTREE, env="bench", today=TODAY)

    assert after.require_xml() == direct


def test_production_gets_its_file_and_the_trunk_is_not_touched(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = git(repo.root, "rev-parse", "main")

    package = _package(repo, "main", f"folder:{WEEKLY}")

    assert package.env == "prod" and _names(package) == [WEEKLY]
    xml = package.require_xml()
    assert b'FOLDER_NAME="PP77_WEEKLY_DAILY"' in xml and USERS["prod"].encode() in xml
    assert b"CTMPROD" in xml and _nothing_of_uat(xml)
    assert git(repo.root, "rev-parse", "main") == head and git(repo.root, "status", "-s") == ""


def test_two_environments_have_no_branch_to_merge_first(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    package = _package(repo)

    assert not [w for w in package.warnings if "merge" in w]


def test_an_item_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(ChainError):
        _package(repo, BENCH, f"job:{CHAIN}/P77_NOWHERE")


def test_two_environments_that_agree_have_nothing_to_package(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)

    package = _package(repo)

    assert package.xml is None and package.folders == ()
    with pytest.raises(NothingToPackage):
        package.require_xml()


# ---------------------------------------------------------------- a value the map cannot settle


def _two_users(tmp_path: Path) -> ChainRepo:
    repo = four_branches(tmp_path, change=two_users_in("bench"))
    with_map(repo)
    return repo


def test_a_value_of_the_other_environment_left_in_the_file_is_warned_about(
    tmp_path: Path,
) -> None:
    repo = _two_users(tmp_path)

    one = _package(repo, BENCH, f"job:{CHAIN}/P77_NEW")
    (kept,) = [w for w in one.warnings if "kept as it is" in w]
    assert f"RUN_AS {USERS['uat']} of uat" in kept and f"({CHAIN}/P77_NEW)" in kept
    assert USERS["uat"].encode() in one.require_xml()

    everything = _package(repo)
    (kept,) = [w for w in everything.warnings if "kept as it is" in w]
    assert "and 3 more" in kept  # the new job and the three of the new folder

    untouched = _package(repo, BENCH, f"attr:{CHAIN}/P77_A@CMDLINE")
    assert not [w for w in untouched.warnings if "kept as it is" in w]


def test_a_preferred_entry_settles_the_value_in_the_file(tmp_path: Path) -> None:
    repo = _two_users(tmp_path)

    package = _package(repo, BENCH, f"folder:{WEEKLY}", prefer=("run_as.1",))

    assert not [w for w in package.warnings if "kept as it is" in w]
    assert _nothing_of_uat(package.require_xml())


def test_the_file_is_saved_once_and_never_over_another(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    package = build_package(repo.root, "main", UAT, take=[f"job:{CHAIN}/P77_NEW"], today=TODAY)
    nothing = build_package(repo.root, UAT, UAT, env="uat", today=TODAY)
    path = tmp_path / "out" / package.filename

    assert save(package, path) == path and path.read_bytes() == package.xml
    with pytest.raises(ChainError, match="is there already"):
        save(package, path)
    with pytest.raises(NothingToPackage):
        save(nothing, tmp_path / "nothing.xml")
    assert not (tmp_path / "nothing.xml").exists()
