"""The steps of a preview, kept by its id: a command applies a change by the id alone."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core import previews
from controlm_chain_admin.core.errors import ChainError
from tests.support.gitrepo import chain_git_repo

STEPS = [{"do": "change-fields", "params": {"nodes": ["P77_CHAIN/P77_B"], "changes": {"A": "1"}}}]


def test_the_steps_of_a_preview_come_back_by_its_id(tmp_path: Path) -> None:
    root = chain_git_repo(tmp_path).root

    previews.remember(root, "abc123", STEPS)

    assert previews.recall(root, "abc123") == STEPS
    # kept inside the git directory: nothing shows in the working tree
    assert not any(p.name.startswith("abc123") for p in root.rglob("*") if ".git" not in p.parts)


def test_an_id_never_previewed_says_to_preview_again(tmp_path: Path) -> None:
    root = chain_git_repo(tmp_path).root

    with pytest.raises(ChainError, match=r"no preview abc123.*preview again"):
        previews.recall(root, "abc123")


@pytest.mark.parametrize("wrong", ["../x", "a/b", "", "a b"])
def test_an_id_that_is_not_one_is_refused(tmp_path: Path, wrong: str) -> None:
    root = chain_git_repo(tmp_path).root

    with pytest.raises(ChainError, match="not a preview id"):
        previews.remember(root, wrong, STEPS)
    with pytest.raises(ChainError, match="not a preview id"):
        previews.recall(root, wrong)


def test_only_the_last_ones_are_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = chain_git_repo(tmp_path).root
    monkeypatch.setattr(previews, "KEEP", 2)

    for number in range(3):
        previews.remember(root, f"id{number}", STEPS)

    with pytest.raises(ChainError, match="no preview id0"):
        previews.recall(root, "id0")
    assert previews.recall(root, "id2") == STEPS


def test_without_git_they_are_kept_beside_the_repository(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()

    previews.remember(root, "abc", STEPS)

    assert previews.recall(root, "abc") == STEPS
