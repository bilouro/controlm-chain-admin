"""``refresh``: the full export of an environment overwrites its branch, after showing what
differs."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.errors import (
    ChainError,
    GitError,
    ProtectedBranch,
    UncommittedChanges,
)
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.refresh import refresh
from controlm_chain_admin.core.repo import load_repo, read_json
from tests.support.envexports import job
from tests.support.fourenvs import (
    CHAIN,
    INGEST,
    empty_repo,
    export_of,
    four_branches,
    own,
    uat_ahead,
    without_folder,
    without_job,
)
from tests.support.gitrepo import commit_all, git, plain_git_identity


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


# ---------------------------------------------------------------- import, replacing


def test_an_import_that_replaces_drops_what_the_export_no_longer_has(tmp_path: Path) -> None:
    repo = empty_repo(tmp_path)
    import_xml(repo, export_of("uat"), env="uat")
    smaller = without_folder(export_of("uat"), "UP77_CHAIN")

    report = import_xml(repo, smaller, env="uat", replace_all=True)

    assert report.folders == (INGEST,)
    assert not repo.folder_dir(CHAIN).exists() and not repo.folder_meta_file(CHAIN).exists()
    assert read_json(repo.export_meta_file)["folder_order"] == [INGEST]
    assert export_xml(load_repo(repo.root), env="uat").count(b"<SMART_FOLDER") == 1


def test_an_import_that_does_not_replace_keeps_the_other_folders(tmp_path: Path) -> None:
    repo = empty_repo(tmp_path)
    import_xml(repo, export_of("uat"), env="uat")

    import_xml(repo, without_folder(export_of("uat"), "UP77_CHAIN"), env="uat")

    assert repo.folder_dir(CHAIN).exists()


def test_replacing_forgets_the_names_the_repository_gave_to_conditions(tmp_path: Path) -> None:
    repo = empty_repo(tmp_path)
    import_xml(repo, export_of("prod"), env="prod")
    renamed = export_of("uat").replace(b"UP77_A-UP77_B_OK", b"UP77_A-UP77_B_DONE")

    import_xml(repo, renamed, env="uat", replace_all=True)

    links = read_json(repo.folder_dir(CHAIN) / "links.json")["links"]
    assert "P77_A-P77_B_DONE" in links and "P77_A-P77_B_OK" not in links


# ---------------------------------------------------------------- refresh


def test_the_first_refresh_of_production_fills_the_trunk(tmp_path: Path) -> None:
    repo = empty_repo(tmp_path)

    preview = refresh(repo, export_of("prod"), source="prod.xml")

    assert (preview.env, preview.branch, preview.new_branch) == ("prod", "main", False)
    assert preview.applied is False and preview.commit is None
    assert preview.summary["folders"]["added"] == 2
    assert not repo.folders_dir.exists()  # a preview writes nothing

    done = refresh(repo, export_of("prod"), source="prod.xml", apply=True)

    assert done.applied and done.commit
    assert git(repo.root, "log", "-1", "--format=%s") == "refresh(prod): prod.xml"
    assert git(repo.root, "status", "--porcelain") == ""
    assert export_xml(load_repo(repo.root), env="prod") == own(export_of("prod"))


def test_the_environment_is_read_from_the_letters_of_the_export(tmp_path: Path) -> None:
    repo = empty_repo(tmp_path)
    refresh(repo, export_of("prod"), source="prod.xml", apply=True)

    done = refresh(repo, export_of("egma"), source="egma.xml", apply=True)

    assert (done.env, done.branch, done.new_branch) == ("egma", "env/egma", True)
    assert git(repo.root, "branch", "--show-current") == "env/egma"
    assert export_xml(load_repo(repo.root), env="egma") == own(export_of("egma"))
    assert git(repo.root, "merge-base", "main", "env/egma") == git(repo.root, "rev-parse", "main")


def test_each_branch_exports_what_its_environment_gave_byte_for_byte(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)

    for env, branch in (("prod", "main"), ("uat", "env/uat"), ("egma", "env/egma"),
                        ("bench", "env/bench")):  # fmt: skip
        git(repo.root, "switch", "-q", branch)
        assert export_xml(load_repo(repo.root), env=env) == own(export_of(env)), env


def test_refreshing_again_shows_the_differences_and_applies_them_when_asked(
    tmp_path: Path,
) -> None:
    repo = four_branches(tmp_path)
    changed = job(export_of("bench"), b"BP77_B", b'CMDLINE="/opt/p77/bin/b.ksh"',
                  b'CMDLINE="/opt/p77/bin/b2.ksh"')  # fmt: skip
    changed = without_job(changed, "BP77_INGEST_LOAD")
    before = git(repo.root, "rev-parse", "env/bench")

    preview = refresh(repo, changed, source="bench-2.xml")

    assert preview.branch == "env/bench" and not preview.applied
    assert preview.summary["jobs"]["removed"] == 1
    # the job that fed the removed one changes too: nobody waits for its condition any more
    assert {j.node for j in preview.comparison.jobs if j.change == "modified"} == {
        f"{CHAIN}/P77_B",
        f"{INGEST}/P77_INGEST_INIT",
    }
    assert git(repo.root, "rev-parse", "env/bench") == before
    assert git(repo.root, "branch", "--show-current") == "main"  # a preview stays where it is

    done = refresh(repo, changed, source="bench-2.xml", apply=True)

    assert done.applied and git(repo.root, "branch", "--show-current") == "env/bench"
    assert export_xml(load_repo(repo.root), env="bench") == own(changed)
    assert not (repo.root / "folders" / INGEST / "jobs" / "P77_INGEST_LOAD.json").exists()


def test_the_same_export_again_changes_nothing(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    before = git(repo.root, "rev-parse", "env/uat")

    done = refresh(repo, export_of("uat"), source="uat.xml", apply=True)

    assert done.applied is False and done.commit is None and done.unchanged
    assert git(repo.root, "rev-parse", "env/uat") == before


def test_the_same_export_changes_nothing_where_git_converts_line_ends(tmp_path: Path) -> None:
    """Git for Windows hands files out with CRLF (core.autocrlf): that is not a difference."""
    repo = empty_repo(tmp_path)
    git(repo.root, "config", "core.autocrlf", "true")
    refresh(repo, export_of("prod"), source="prod.xml", apply=True)
    refresh(repo, export_of("uat"), source="uat.xml", apply=True)
    before = git(repo.root, "rev-parse", "env/uat")

    done = refresh(load_repo(repo.root), export_of("uat"), source="uat.xml", apply=True)

    assert (done.files_changed, done.unchanged, done.applied) == (0, True, False)
    assert git(repo.root, "rev-parse", "env/uat") == before


def test_a_refresh_is_refused_over_uncommitted_chain_changes(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    (repo.root / "chain.json").write_text(
        (repo.root / "chain.json").read_text("utf-8") + "\n", "utf-8"
    )

    with pytest.raises(UncommittedChanges):
        refresh(repo, export_of("uat"), source="uat.xml", apply=True)


def test_without_commit_the_changes_stay_in_the_working_tree(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    changed = export_of("uat").replace(b"/opt/p77/bin/c.ksh", b"/opt/p77/bin/c2.ksh")
    before = git(repo.root, "rev-parse", "env/uat")

    done = refresh(repo, changed, source="uat.xml", apply=True, commit=False)

    assert done.applied and done.commit is None
    assert git(repo.root, "rev-parse", "env/uat") == before
    assert "P77_C.json" in git(repo.root, "status", "--porcelain")


def test_an_export_of_no_known_environment_asks_for_it(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    unknown = export_of("uat").replace(b"UP77", b"ZP77")

    with pytest.raises(ChainError, match="--env"):
        refresh(repo, unknown, source="z.xml")


def test_the_environment_given_must_be_the_one_the_export_shows(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)

    with pytest.raises(ChainError, match="uat"):
        refresh(repo, export_of("uat"), source="uat.xml", env="bench")


def test_other_files_of_the_trunk_follow_into_a_new_environment_branch(tmp_path: Path) -> None:
    repo = empty_repo(tmp_path)
    (repo.root / "README.md").write_text("the data\n", "utf-8")
    commit_all(repo.root, "docs: readme")
    refresh(repo, export_of("prod"), source="prod.xml", apply=True)

    refresh(repo, export_of("uat"), source="uat.xml", apply=True)

    assert (repo.root / "README.md").read_text("utf-8") == "the data\n"


# ---------------------------------------------------------------- onto the checked-out branch


def on_a_branch_of_uat(tmp_path: Path, name: str = "work/uat-next") -> Path:
    """The four environments, and a branch started from uat's that is checked out."""
    root = four_branches(tmp_path).root
    git(root, "switch", "-q", "-c", name, "env/uat")
    return root


def test_an_export_goes_onto_the_checked_out_branch_and_the_environments_stays(
    tmp_path: Path,
) -> None:
    root = on_a_branch_of_uat(tmp_path)
    newer = uat_ahead("uat", export_of("uat"))
    before = git(root, "rev-parse", "env/uat")

    preview = refresh(load_repo(root), newer, source="uat-2.xml", here=True)

    assert (preview.env, preview.branch) == ("uat", "work/uat-next")
    assert (preview.new_branch, preview.applied, preview.work) == (False, False, True)
    assert preview.summary["jobs"]["added"] == 3 and preview.summary["folders"]["added"] == 1
    assert git(root, "status", "--porcelain") == ""  # a preview writes nothing

    done = refresh(load_repo(root), newer, source="uat-2.xml", here=True, apply=True)

    assert done.applied and done.commit == git(root, "rev-parse", "work/uat-next")
    assert git(root, "branch", "--show-current") == "work/uat-next"
    assert git(root, "log", "-1", "--format=%s") == "import(uat): uat-2.xml"
    assert git(root, "rev-parse", "env/uat") == before  # uat's own branch is not touched
    assert export_xml(load_repo(root), env="uat") == own(newer)
    # so uat as it was against uat as the export has it is a comparison of two branches
    between = compare(root, "env/uat", "work/uat-next")
    assert between.summary()["jobs"]["added"] == 3
    assert [j.node for j in between.jobs if j.change == "modified"] == [f"{CHAIN}/P77_A"]


def test_a_partial_export_keeps_the_folders_it_does_not_have(tmp_path: Path) -> None:
    root = on_a_branch_of_uat(tmp_path, "work/delivery")
    delivery = without_folder(export_of("uat"), "UP77_INGEST_DAILY").replace(
        b"/opt/p77/bin/c.ksh", b"/opt/p77/bin/c2.ksh"
    )

    whole = refresh(load_repo(root), delivery, source="delivery.xml", here=True)

    assert whole.summary["folders"]["removed"] == 1  # read as a full export, the other one goes

    preview = refresh(load_repo(root), delivery, source="delivery.xml", here=True, partial=True)

    assert preview.partial and preview.summary["folders"]["removed"] == 0
    assert [(j.node, j.change) for j in preview.comparison.jobs] == [
        (f"{CHAIN}/P77_C", "modified")
    ]

    done = refresh(
        load_repo(root), delivery, source="delivery.xml", here=True, partial=True, apply=True
    )

    assert done.applied and (root / "folders" / INGEST / "folder.json").is_file()
    assert git(root, "log", "-1", "--format=%s") == "import(uat): delivery.xml"
    assert git(root, "status", "--porcelain") == ""
    again = refresh(
        load_repo(root), delivery, source="delivery.xml", here=True, partial=True, apply=True
    )
    assert again.unchanged and not again.applied


def test_the_branch_of_an_environment_takes_only_its_own_full_export(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)  # on main
    uat = export_of("uat")

    with pytest.raises(ChainError, match="main holds prod: an export of uat goes onto env/uat"):
        refresh(repo, uat, here=True)
    git(repo.root, "switch", "-q", "env/egma")
    with pytest.raises(ChainError, match="env/egma holds egma: an export of uat goes onto"):
        refresh(repo, uat, here=True, apply=True)
    assert git(repo.root, "status", "--porcelain") == ""

    git(repo.root, "switch", "-q", "env/uat")
    same = refresh(repo, uat, here=True)  # its own branch: the refresh itself
    assert (same.branch, same.work, same.unchanged) == ("env/uat", False, True)
    for here in (False, True):
        with pytest.raises(ChainError, match="env/uat holds the full export of uat"):
            refresh(repo, uat, here=here, partial=True)


def test_a_protected_branch_or_a_detached_head_takes_no_export(tmp_path: Path) -> None:
    root = on_a_branch_of_uat(tmp_path, "master")

    with pytest.raises(ProtectedBranch, match="master is protected"):
        refresh(load_repo(root), export_of("uat"), here=True)
    git(root, "switch", "-q", "--detach", "env/uat")
    with pytest.raises(GitError, match="HEAD is detached: check a branch out"):
        refresh(load_repo(root), export_of("uat"), here=True)


def test_an_export_onto_the_checked_out_branch_is_refused_over_uncommitted_changes(
    tmp_path: Path,
) -> None:
    root = on_a_branch_of_uat(tmp_path)
    (root / "chain.json").write_text((root / "chain.json").read_text("utf-8") + "\n", "utf-8")

    with pytest.raises(UncommittedChanges):
        refresh(load_repo(root), uat_ahead("uat", export_of("uat")), here=True, apply=True)
