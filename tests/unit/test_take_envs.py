"""Taking from the branch of one environment into the branch of another: what arrives is in
the terms of the environment it arrives in."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.errors import ChainError, InvalidChange
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.refactor import apply, run_operation
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.core.take import items_of, take, takeable
from tests.support.envexports import job
from tests.support.fourenvs import (
    CHAIN,
    HOSTS,
    INGEST,
    USERS,
    WEEKLY,
    administrator,
    four_branches,
    two_users_in,
    uat_ahead,
    with_map,
    without_folder,
)
from tests.support.gitrepo import commit_all, git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"
SUBAPP = "P77_BATCH"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def _on_bench(tmp_path: Path, change: object = uat_ahead) -> ChainRepo:
    """The four environments with their map, the branch of bench checked out."""
    repo = four_branches(tmp_path, change=change)  # type: ignore[arg-type]
    with_map(repo)
    git(repo.root, "switch", "-q", BENCH)
    return load_repo(repo.root)


def _take(repo: ChainRepo, *items: str) -> None:
    apply(repo, take(repo, BENCH, UAT, items))


def test_one_attribute_and_nothing_else(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path)

    _take(repo, f"attr:{CHAIN}/P77_A@CMDLINE")

    taken = read_json(repo.job_file(CHAIN, "P77_A"))
    assert taken["CMDLINE"] == "/opt/p77/bin/a2.ksh -x"
    assert (taken["RUN_AS"], taken["NODEID"]) == (USERS["bench"], HOSTS["bench"])
    assert not repo.job_file(CHAIN, "P77_NEW").exists()


def test_a_job_arrives_with_the_user_and_the_machine_of_the_target(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path)

    _take(repo, f"job:{CHAIN}/P77_NEW")

    new = read_json(repo.job_file(CHAIN, "P77_NEW"))
    assert (new["RUN_AS"], new["NODEID"]) == (USERS["bench"], HOSTS["bench"])
    assert "P77_NEW" in read_json(repo.folder_file(CHAIN))["jobs"]


def test_a_variable_of_a_folder(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path)

    _take(repo, f"var:{INGEST}/@%%RETRY")

    variables = read_json(repo.folder_file(INGEST))["VARIABLE"]
    assert variables == [{"NAME": "%%GEIENV", "VALUE": "b"}, {"NAME": "%%RETRY", "VALUE": "3"}]


def test_a_whole_folder_exports_as_the_target_would_have_it(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path)

    _take(repo, f"folder:{WEEKLY}")

    xml = export_xml(load_repo(repo.root), "bench")
    assert b'FOLDER_NAME="BP77_WEEKLY_DAILY"' in xml and b'DATACENTER="CTMBENCH"' in xml
    assert b'NAME="BP77_WEEKLY_INIT-BP77_WEEKLY_LOAD_OK"' in xml
    assert b"[P77][BENCH] Load failed" in xml
    for uat in (b"UP77", b"URQ_", USERS["uat"].encode(), b"CTMUAT", b"[UAT]"):
        assert uat not in xml


def test_a_sub_application_is_every_folder_of_it_that_differs(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path)

    change = take(repo, BENCH, UAT, [f"subapp:{SUBAPP}"])
    apply(repo, change)
    commit_all(repo.root, "take the sub-application from uat")

    assert {e.path.split("/")[1] for e in change.edits if e.path.startswith("folders/")} == {
        CHAIN, INGEST, WEEKLY,
    }  # fmt: skip
    left = compare(repo.root, BENCH, UAT)
    assert (left.folders, left.jobs, left.links) == ((), (), ())


def _one_folder_changed(env: str, data: bytes) -> bytes:
    if env != "uat":
        return data
    return job(data, b"UP77_A", b"/opt/p77/bin/a.ksh", b"/opt/p77/bin/a2.ksh -x")


def test_the_folders_of_the_sub_application_that_do_not_differ_are_left_alone(
    tmp_path: Path,
) -> None:
    repo = _on_bench(tmp_path, _one_folder_changed)

    change = take(repo, BENCH, UAT, [f"subapp:{SUBAPP}"])

    assert change.edits and all(f"/{CHAIN}" in e.path for e in change.edits)


def _one_folder_less(env: str, data: bytes) -> bytes:
    changed = _one_folder_changed(env, data)
    return without_folder(changed, "UP77_INGEST_DAILY") if env == "uat" else changed


def test_a_folder_the_other_environment_lacks_stays_and_a_warning_says_so(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path, _one_folder_less)

    change = take(repo, BENCH, UAT, [f"subapp:{SUBAPP}"])
    apply(repo, change)

    assert repo.folder_file(INGEST).is_file()
    assert any(INGEST in w and f"folder:{INGEST}" in w for w in change.warnings)


def test_a_sub_application_nobody_has_is_refused(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path)

    with pytest.raises(InvalidChange, match="no sub-application P77_NOWHERE"):
        take(repo, BENCH, UAT, ["subapp:P77_NOWHERE"])


def test_the_sub_applications_that_differ_are_listed_with_the_other_items(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path)

    items = dict(items_of(compare(repo.root, BENCH, UAT)))

    assert items[f"subapp:{SUBAPP}"] == "3 folders that differ"
    assert f"folder:{WEEKLY}" in items and f"var:{INGEST}/@%%RETRY" in items


# ---------------------------------------------------------------- a value the map cannot settle


def test_a_value_the_map_gives_two_answers_for_is_kept_and_a_warning_says_so(
    tmp_path: Path,
) -> None:
    repo = _on_bench(tmp_path, two_users_in("bench"))

    change = take(repo, BENCH, UAT, [f"job:{CHAIN}/P77_NEW"])

    (kept,) = [w for w in change.warnings if "kept as it is" in w]
    assert f"RUN_AS {USERS['uat']} of uat is" in kept and "(run_as.2)" in kept
    assert f"({CHAIN}/P77_NEW)" in kept
    # nothing is said about what was not taken
    other = take(repo, BENCH, UAT, [f"attr:{CHAIN}/P77_A@CMDLINE"])
    assert not [w for w in other.warnings if "kept as it is" in w]


def test_taking_with_a_preferred_entry_settles_it(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path, two_users_in("bench"))

    change = take(repo, BENCH, UAT, [f"job:{CHAIN}/P77_NEW"], prefer=("run_as.2",))
    apply(repo, change)

    assert not [w for w in change.warnings if "kept as it is" in w]
    new = read_json(repo.root / "folders" / CHAIN / "jobs" / "P77_NEW.json")
    assert new["RUN_AS"] == administrator("bench")


# ---------------------------------------------------------------- the list an adapter shows


def test_the_items_that_can_be_taken_say_into_what_and_between_which_environments(
    tmp_path: Path,
) -> None:
    repo = _on_bench(tmp_path)

    found = takeable(repo.root, "HEAD", UAT)

    assert (found.into, found.source, found.environments) == (BENCH, UAT, ("bench", "uat"))
    assert found.items == items_of(compare(repo.root, BENCH, UAT))
    assert found.to_json()["items"][0] == {
        "id": f"subapp:{SUBAPP}", "label": "3 folders that differ"
    }  # fmt: skip
    assert found.to_json()["environments"] == ["bench", "uat"]


def test_the_list_is_of_the_comparison_with_the_entry_preferred(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path, two_users_in("bench"))

    found = takeable(repo.root, BENCH, UAT, prefer=("run_as.2",))

    assert f"job:{CHAIN}/P77_NEW" in dict(found.items)
    with pytest.raises(ChainError, match=r"run_as\.9"):
        takeable(repo.root, BENCH, UAT, prefer=("run_as.9",))


def test_the_operation_takes_into_the_branch_checked_out_with_the_entry_preferred(
    tmp_path: Path,
) -> None:
    repo = _on_bench(tmp_path, two_users_in("bench"))
    params = {"head": UAT, "items": [f"job:{CHAIN}/P77_NEW"]}

    plain = run_operation(repo, "take", params)
    settled = run_operation(repo, "take", {**params, "base": BENCH, "prefer": ["run_as.2"]})

    assert [w for w in plain.warnings if "kept as it is" in w]
    assert not [w for w in settled.warnings if "kept as it is" in w]


def test_an_item_without_its_kind_is_refused_with_how_an_id_looks(tmp_path: Path) -> None:
    repo = _on_bench(tmp_path)

    with pytest.raises(ChainError, match=r"an id is KIND:WHAT, as in job:FOLDER/JOB"):
        take(repo, BENCH, UAT, [f"{CHAIN}/P77_NEW"])


def test_the_name_of_an_environment_given_for_its_branch_says_which_branch_it_is(
    tmp_path: Path,
) -> None:
    repo = _on_bench(tmp_path)

    with pytest.raises(ChainError, match="unknown git ref 'uat': the environment uat is the "
                                         "branch env/uat"):  # fmt: skip
        takeable(repo.root, "HEAD", "uat")
    with pytest.raises(ChainError, match="unknown git ref 'prod': the environment prod is the "
                                         "branch main"):  # fmt: skip
        compare(repo.root, "prod", UAT)
    with pytest.raises(ChainError, match=r"unknown git ref 'nowhere'$"):
        compare(repo.root, "nowhere", UAT)
