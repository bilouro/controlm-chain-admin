"""A condition two environments call by different names (story 17): the same jobs linked the
same way, another name. Each may keep its own, or one takes the other's."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare, render_text
from controlm_chain_admin.core.crossenv import OtherName
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.package import build_package
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from controlm_chain_admin.core.take import items_of, take, takeable
from tests.support.fourenvs import CHAIN, four_branches, with_map
from tests.support.gitrepo import git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"
OURS, THEIRS = "P77_A-P77_B_OK", "P77_ALPHA-P77_B_OK"
TODAY = "2026-11-12"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    """Four environments; uat calls the condition between ``P77_A`` and ``P77_B`` otherwise."""
    built = four_branches(
        tmp_path,
        change=lambda env, data: (
            data.replace(b"UP77_A-UP77_B_OK", b"UP77_ALPHA-UP77_B_OK") if env == "uat" else data
        ),
    )
    with_map(built)
    return load_repo(built.root)


def test_the_comparison_names_the_conditions_called_otherwise(repo: ChainRepo) -> None:
    result = compare(repo.root, BENCH, UAT)
    turned = compare(repo.root, UAT, BENCH)

    assert result.translation is not None and turned.translation is not None
    (name,) = result.translation.names
    assert (name.base, name.head) == (OURS, THEIRS) and isinstance(name, OtherName)
    assert [(n.base, n.head) for n in turned.translation.names] == [(THEIRS, OURS)]
    assert result.links == () and not result.jobs  # still no difference: read through
    assert result.to_json()["translation"]["names"] == [
        {"link": name.link, "base": OURS, "head": THEIRS}
    ]
    text = render_text(result)
    assert "1 condition called another name" in text
    assert f"  {OURS} is {THEIRS} in uat (link:{name.link} takes that name)" in text


def test_the_name_is_an_item_that_can_be_taken(repo: ChainRepo) -> None:
    (name,) = compare(repo.root, BENCH, UAT).translation.names  # type: ignore[union-attr]
    item = f"link:{name.link}"
    git(repo.root, "switch", "-q", BENCH)
    bench = load_repo(repo.root)

    listed = dict(takeable(repo.root, "HEAD", UAT).items)
    apply(bench, take(bench, BENCH, UAT, [item]))

    assert listed[item] == f"condition {OURS} -> {THEIRS}: the name uat uses"
    assert item in dict(items_of(compare(repo.root, BENCH, UAT)))
    xml = export_xml(load_repo(repo.root), "bench")
    assert b"BP77_ALPHA-BP77_B_OK" in xml and b"BP77_A-BP77_B_OK" not in xml


def test_the_name_goes_in_the_file_of_the_environment_that_takes_it(repo: ChainRepo) -> None:
    (name,) = compare(repo.root, "main", UAT).translation.names  # type: ignore[union-attr]

    package = build_package(repo.root, "main", UAT, take=[f"link:{name.link}"], today=TODAY)

    xml = package.require_xml()
    assert package.env == "prod" and [f.name for f in package.folders] == [CHAIN]
    assert b"PP77_ALPHA-PP77_B_OK" in xml and b"PP77_A-PP77_B_OK" not in xml


def test_environments_that_call_everything_alike_have_no_such_name(tmp_path: Path) -> None:
    plain = four_branches(tmp_path)
    with_map(plain)

    result = compare(plain.root, BENCH, UAT)

    assert result.translation is not None and result.translation.names == ()
    assert "takes that name" not in render_text(result)
