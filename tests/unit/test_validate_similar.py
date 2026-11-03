"""Similar condition names: copies told apart only by a suffix (``…_OK-U26``) or by case."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.fixes import Fix, by_kind, fixes_for
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.refactor import apply, run_operation
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo
from controlm_chain_admin.core.validate import Finding, parse_condition_name, validate

APP = "P77_RISK_ENGINE"
F = "P77_SIM"

_JOB = (
    '        <JOB JOBISN="{n}" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" '
    'MEMNAME="U{name}" JOBNAME="U{name}" RUN_AS="aup77proc" TASKTYPE="Dummy" '
    'NODEID="UP77_BATCH" PARENT_FOLDER="UP77_SIM">\n{body}        </JOB>\n'
)


def _export(*links: tuple[str, str, str | None]) -> bytes:
    """A folder whose jobs are linked by ``(condition, producer, consumer)``; no consumer means
    nobody in the repository waits for it."""
    bodies: dict[str, list[str]] = {}
    for neutral, producer, consumer in links:
        condition = neutral.replace("P77", "UP77")  # as exported from uat
        bodies.setdefault(producer, []).append(
            f'            <OUTCOND NAME="{condition}" ODATE="ODAT" SIGN="+" />\n'
        )
        if consumer is not None:
            bodies.setdefault(consumer, []).extend(
                [
                    f'            <INCOND NAME="{condition}" ODATE="ODAT" AND_OR="A" />\n',
                    f'            <OUTCOND NAME="{condition}" ODATE="ODAT" SIGN="-" />\n',
                ]
            )
    jobs = "".join(
        _JOB.format(n=n, name=name, body="".join(body))
        for n, (name, body) in enumerate(bodies.items(), start=2)
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<DEFTABLE>\n"
        '    <SMART_FOLDER JOBISN="1" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" '
        'JOBNAME="UP77_SIM" RUN_AS="aup77proc" TASKTYPE="SMART Table" FOLDER_NAME="UP77_SIM" '
        'TYPE="2">\n'
        f"{jobs}"
        "    </SMART_FOLDER>\n"
        "</DEFTABLE>\n"
    ).encode()


COPIES = (
    ("P77_A-P77_B_OK", "P77_A", "P77_B"),
    ("P77_A-P77_B_OK-U26", "P77_A2", "P77_B2"),  # a copy of the chain, renamed by a suffix
    ("P77_A-P77_B_OK-U26-U31", "P77_A3", "P77_B3"),  # a copy of the copy
)


def _repo(tmp_path: Path, *links: tuple[str, str, str | None]) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("test", "uat", "prod"), prefixes=("P77",))
    import_xml(repo, _export(*links), env="uat")
    return load_repo(tmp_path)


def _similar(repo: ChainRepo) -> list[Finding]:
    return [f for f in validate(repo, write_index=False).findings if f.code == "similar-names"]


def _fix(repo: ChainRepo, finding: Finding) -> Fix:
    report = validate(repo, write_index=False)
    offered = dict(zip(report.findings, fixes_for(repo, report.findings), strict=True))
    [fix] = offered[finding]
    return fix


def _renames(fix: Fix) -> list[str]:
    """The renames of the fix, once each (the effects list them for every job that uses one)."""
    return list(
        dict.fromkeys(
            f"{e.before} -> {e.after}" for e in fix.effects if e.element == "condition name"
        )
    )


def test_copies_told_apart_by_a_suffix_are_similar_names(tmp_path: Path) -> None:
    repo = _repo(tmp_path, *COPIES)

    [finding] = _similar(repo)

    assert (finding.severity, finding.name) == ("warning", "P77_A-P77_B_OK")
    assert finding.node == f"{F}/P77_A"
    assert (
        "3 conditions differ only by a suffix or by case: P77_A-P77_B_OK, "
        "P77_A-P77_B_OK-U26, P77_A-P77_B_OK-U26-U31" in finding.message
    )


def test_the_fix_numbers_them(tmp_path: Path) -> None:
    repo = _repo(tmp_path, *COPIES)
    [finding] = _similar(repo)

    fix = _fix(repo, finding)

    assert (fix.kind, fix.title) == ("number-similar", "Number the similar names")
    assert fix.label == (
        "rename P77_A-P77_B_OK -> P77_A-P77_B_OK1; rename P77_A-P77_B_OK-U26 -> "
        "P77_A-P77_B_OK2; rename P77_A-P77_B_OK-U26-U31 -> P77_A-P77_B_OK3"
    )
    assert fix.op == "batch" and [c["op"] for c in fix.params["changes"]] == ["rename-link"] * 3
    assert "in every job that uses it" in fix.explanation
    assert set(_renames(fix)) == {
        "P77_A-P77_B_OK -> P77_A-P77_B_OK1",
        "P77_A-P77_B_OK-U26 -> P77_A-P77_B_OK2",
        "P77_A-P77_B_OK-U26-U31 -> P77_A-P77_B_OK3",
    }


def test_numbered_names_are_no_longer_similar_and_stay_standard(tmp_path: Path) -> None:
    repo = _repo(tmp_path, *COPIES)
    [finding] = _similar(repo)
    fix = _fix(repo, finding)

    apply(repo, run_operation(repo, fix.op, fix.params))

    report = validate(repo, write_index=False)
    by_name = {(f.code, f.name) for f in report.findings}
    assert _similar(repo) == []
    assert ("non-standard-name", "P77_A-P77_B_OK1") not in by_name
    assert ("stale-name", "P77_A-P77_B_OK1") not in by_name
    assert ("stale-name", "P77_A-P77_B_OK2") in by_name  # still names P77_A -> P77_B


def test_names_that_differ_only_in_case_are_similar(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        ("P77_C-P77_D_Ok", "P77_C", "P77_D"),
        ("P77_C-P77_D_OK", "P77_E", "P77_F"),
    )

    [finding] = _similar(repo)

    assert finding.name == "P77_C-P77_D_OK"
    assert _renames(_fix(repo, finding)) == [
        "P77_C-P77_D_OK -> P77_C-P77_D_OK1",
        "P77_C-P77_D_Ok -> P77_C-P77_D_OK2",
    ]


def test_names_that_describe_their_own_jobs_are_not_similar(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        ("P77_G-TO-P77_LOAD-S1", "P77_G", "P77_LOAD-S1"),
        ("P77_G-TO-P77_LOAD-S2", "P77_G", "P77_LOAD-S2"),
        ("P77_H-P77_K_OK_1", "P77_H", "P77_K"),
        ("P77_H-P77_K_OK_2", "P77_H2", "P77_K2"),  # already numbered
    )

    assert _similar(repo) == []


def test_a_condition_with_an_end_outside_the_repository_keeps_its_name(tmp_path: Path) -> None:
    repo = _repo(tmp_path, *COPIES, ("P77_A-P77_B_OK-U40", "P77_A3", None))
    [finding] = _similar(repo)

    fix = _fix(repo, finding)

    assert "4 conditions" in finding.message
    assert "P77_A-P77_B_OK-U40" not in fix.label
    assert "P77_A-P77_B_OK-U40 keeps its name" in fix.explanation


def test_a_number_another_condition_has_is_skipped(tmp_path: Path) -> None:
    repo = _repo(tmp_path, *COPIES, ("P77_A-P77_B_OK2", "P77_X", "P77_Y"))
    [finding] = _similar(repo)

    assert _renames(_fix(repo, finding)) == [
        "P77_A-P77_B_OK -> P77_A-P77_B_OK1",
        "P77_A-P77_B_OK-U26 -> P77_A-P77_B_OK3",
        "P77_A-P77_B_OK-U26-U31 -> P77_A-P77_B_OK4",
    ]


@pytest.mark.parametrize(
    ("name", "parsed"),
    [
        ("P77_A-P77_B_OK2", ("P77_A", "P77_B")),
        ("P77_A-P77_B_ok12", ("P77_A", "P77_B")),
        ("P77_A-TO-P77_B2", ("P77_A", "P77_B2")),
    ],
)
def test_a_numbered_standard_name_is_parsed(name: str, parsed: tuple[str, str]) -> None:
    assert parse_condition_name(name) == parsed


def test_a_numbered_to_name_still_names_its_consumer(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ("P77_A-TO-P77_B2", "P77_A", "P77_B"))

    codes = {f.code for f in validate(repo, write_index=False).findings}

    assert "stale-name" not in codes and "non-standard-name" not in codes


def test_many_families_are_numbered_in_one_change(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        *COPIES,
        ("P77_C-P77_D_Ok", "P77_C", "P77_D"),
        ("P77_C-P77_D_OK", "P77_E", "P77_F"),
    )
    report = validate(repo, write_index=False)
    changes, skipped = by_kind(
        report.findings, fixes_for(repo, report.findings), {"similar-names": "number-similar"}
    )

    apply(repo, run_operation(repo, "batch", {"changes": changes}))  # a batch of batches

    assert skipped == [] and len(changes) == 2 and _similar(repo) == []
