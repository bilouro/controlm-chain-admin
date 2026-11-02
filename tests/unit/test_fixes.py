"""Fixes offered for each validation finding, and that applying one makes the finding go away."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import InvalidChange
from controlm_chain_admin.core.fixes import fixes_for
from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.refactor import apply, run_operation
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.core.validate import validate
from tests.support.gitrepo import chain_git_repo

C = "P77_CHAIN"


def _offered(repo: ChainRepo) -> dict[tuple[str, str], list[str]]:
    report = validate(repo)
    return {
        (f.code, f.name): [fix.label for fix in fixes]
        for f, fixes in zip(report.findings, fixes_for(repo, report.findings), strict=True)
    }


def test_each_finding_of_the_anomalies_gets_its_fixes(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)

    offered = _offered(repo)

    assert offered[("dangling", "P77_A-P77_E_OK")] == [
        f"{C}/P77_A emits P77_A-P77_E_OK",
        f"{C}/P77_E stops waiting for P77_A-P77_E_OK",
    ]
    assert offered[("dangling-external", "P77_GHOST-P77_E_OK")] == [
        f"{C}/P77_E stops waiting for P77_GHOST-P77_E_OK"
    ]
    assert offered[("dangling-unknown", "WEIRD_NAME")] == [
        f"{C}/P77_F stops waiting for WEIRD_NAME"
    ]
    assert offered[("unconsumed", "P77_A-P77_C_OK")] == [
        f"{C}/P77_C waits for P77_A-P77_C_OK",
        f"{C}/P77_A stops emitting P77_A-P77_C_OK",
    ]
    assert offered[("unconsumed-external", "P77_D-P77_NOBODY_OK")] == [
        f"{C}/P77_D stops emitting P77_D-P77_NOBODY_OK"
    ]
    assert offered[("never-cleaned", "P77_B-P77_C_OK")] == [
        f"{C}/P77_C deletes P77_B-P77_C_OK once it ran"
    ]
    assert offered[("stale-name", "P77_OLDNAME-P77_D_OK")] == [
        "rename P77_OLDNAME-P77_D_OK -> P77_C-P77_D_OK"
    ]
    assert offered[("duplicate-jobname", "P77_F")] == [f"rename {C}/P77_F~2 -> P77_F2"]
    assert offered[("non-standard-name", "WEIRD_NAME")] == []  # no producer: no standard name


def test_every_fix_has_a_kind_a_title_and_an_explanation(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    report = validate(repo)

    fixes = [fix for group in fixes_for(repo, report.findings) for fix in group]

    assert {fix.kind for fix in fixes} == {
        "emit", "stop-waiting", "wait", "stop-emitting", "add-cleanup", "standard-name",
        "number-copies",
    }  # fmt: skip
    assert all(fix.title and fix.explanation and fix.op for fix in fixes)
    external = next(f for f in fixes if f.label.endswith("stops waiting for P77_GHOST-P77_E_OK"))
    assert "outside this repository" in external.explanation
    assert fixes[0].to_json().keys() == {"kind", "title", "label", "explanation", "op", "params"}


CASES = [
    ("dangling", "P77_A-P77_E_OK", "emit"),
    ("dangling", "P77_A-P77_E_OK", "stop-waiting"),
    ("dangling-external", "P77_GHOST-P77_E_OK", "stop-waiting"),
    ("dangling-unknown", "WEIRD_NAME", "stop-waiting"),
    ("unconsumed", "P77_A-P77_C_OK", "wait"),
    ("unconsumed", "P77_A-P77_C_OK", "stop-emitting"),
    ("unconsumed-external", "P77_D-P77_NOBODY_OK", "stop-emitting"),
    ("never-cleaned", "P77_B-P77_C_OK", "add-cleanup"),
    ("stale-name", "P77_OLDNAME-P77_D_OK", "standard-name"),
    ("duplicate-jobname", "P77_F", "number-copies"),
]


@pytest.mark.parametrize(("code", "name", "kind"), CASES)
def test_applying_a_fix_makes_the_finding_go_away(
    tmp_path: Path, code: str, name: str, kind: str
) -> None:
    repo = chain_git_repo(tmp_path)
    report = validate(repo)
    index = next(i for i, f in enumerate(report.findings) if (f.code, f.name) == (code, name))
    (fix,) = [f for f in fixes_for(repo, report.findings)[index] if f.kind == kind]

    change = run_operation(repo, fix.op, fix.params)
    apply(repo, change)

    after = {(f.code, f.name) for f in validate(repo).findings}
    assert (code, name) not in after, change.summary
    errors_before = report.count("error")
    assert validate(repo).count("error") <= errors_before


def test_a_batch_is_one_change_set_of_several_changes(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    report = validate(repo)
    fixes = fixes_for(repo, report.findings)
    chosen = [
        fix.to_json()
        for group in fixes
        for fix in group
        if fix.kind in ("add-cleanup", "standard-name", "number-copies")
    ]
    changes = [{"op": f["op"], "params": f["params"]} for f in chosen]

    change = run_operation(
        repo, "batch", {"changes": [*changes, changes[0]]}
    )  # a repeat is ignored

    assert change.summary.startswith(f"{len(changes)} changes:")
    apply(repo, change)
    codes = {f.code for f in validate(repo).findings}
    assert not codes & {"never-cleaned", "stale-name", "duplicate-jobname"}


def test_a_batch_names_the_change_that_failed(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)

    with pytest.raises(InvalidChange, match=r"change 2 of 2 \(unlink\)"):
        run_operation(
            repo,
            "batch",
            {
                "changes": [
                    {"op": "update-relation", "params": {
                        "link": "P77_B-P77_C_OK", "consumer": f"{C}/P77_C", "cleanup": True,
                    }},
                    {"op": "unlink", "params": {
                        "link": "P77_B-P77_C_OK", "consumer": f"{C}/P77_A",
                    }},
                ]
            },
        )  # fmt: skip


def test_a_batch_sees_the_changes_made_before_it(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    changes = [
        {"op": "link", "params": {"consumer": f"{C}/P77_E", "producer": f"{C}/P77_C"}},
        {"op": "rename-link", "params": {"link": "P77_C-P77_E_OK", "name": "P77_C_DONE"}},
        {"op": "update-relation", "params": {
            "link": "P77_C-P77_E_OK", "consumer": f"{C}/P77_E", "and_or": "O",
        }},
    ]  # fmt: skip

    change = run_operation(repo, "batch", {"changes": changes})
    apply(repo, change)

    link = load_links(repo)["P77_C-P77_E_OK"]
    assert link.name == "P77_C_DONE" and link.and_or == ("O",)
    assert all(e.path != "folders/P77_CHAIN/index.json" for e in change.edits)
    assert (repo.root / "folders" / C / "index.json").is_file()  # apply rebuilt it
