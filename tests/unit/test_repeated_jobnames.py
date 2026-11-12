"""A JOBNAME used by more than one job anywhere in the export: the import numbers the later
ones, and ``validate`` says so, with what each code looks for."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.repo import ChainRepo, load_repo
from controlm_chain_admin.core.validate import CODES, EXPLANATIONS, validate
from tests.support.fourenvs import CHAIN, INGEST, four_branches, repeated_name
from tests.support.gitrepo import chain_git_repo, git, plain_git_identity


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    """Four environments whose exports have ``P77_A`` in two folders (and ``P77_F`` twice in
    one), numbered at the import; uat is checked out."""
    built = four_branches(tmp_path, change=repeated_name, numbered=True)
    git(built.root, "switch", "-q", "env/uat")
    return load_repo(built.root)


def _of(repo: ChainRepo, code: str) -> dict[str, tuple[str, str]]:
    report = validate(repo, write_index=False)
    return {f.node: (f.name, f.message) for f in report.findings if f.code == code}


def test_a_name_repeated_in_two_folders_is_a_finding_of_its_own(repo: ChainRepo) -> None:
    found = _of(repo, "repeated-jobname")

    assert set(found) == {f"{CHAIN}/P77_A2", f"{CHAIN}/P77_F2"}
    name, message = found[f"{CHAIN}/P77_A2"]
    assert name == "P77_A"
    assert message == (
        f"JOBNAME P77_A is the name of 2 jobs ({INGEST}/P77_A, {CHAIN}/P77_A2): the repository "
        "calls this one P77_A2 to tell them apart, Control-M still calls it P77_A"
    )
    assert f"{CHAIN}/P77_F, {CHAIN}/P77_F2" in found[f"{CHAIN}/P77_F2"][1]
    assert _of(repo, "duplicate-jobname") == {}  # that one is about ids left unnumbered


def test_the_conditions_of_a_numbered_job_are_not_stale(repo: ChainRepo) -> None:
    stale = _of(repo, "stale-name")

    assert "P77_A-P77_B_OK" not in {name for name, _ in stale.values()}
    assert "P77_OLDNAME-P77_D_OK" in {name for name, _ in stale.values()}  # a real one stays


def test_every_code_says_what_it_looks_for_why_and_what_its_fix_does(repo: ChainRepo) -> None:
    report = validate(repo, write_index=False)
    shown = report.to_json()["explanations"]

    assert set(shown) == {f.code for f in report.findings}
    assert set(EXPLANATIONS) == set(CODES)
    for code, text in EXPLANATIONS.items():
        said = text.to_json()
        assert set(said) == {"looks_for", "why", "fix"}, code
        assert all(len(part) > 20 and part.endswith(".") for part in said.values()), code
    assert "anywhere in the repository" in shown["repeated-jobname"]["looks_for"]


def test_without_numbering_the_same_folder_check_is_the_one_that_speaks(tmp_path: Path) -> None:
    plain = chain_git_repo(tmp_path)

    codes = {f.code for f in validate(plain, write_index=False).findings}

    assert "duplicate-jobname" in codes and "repeated-jobname" not in codes
    assert codes <= set(CODES)
