"""The numbered name of a job becomes its JOBNAME in Control-M too, and that change travels:
``compare`` shows it, ``package`` writes it, ``take`` carries it."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.capabilities import preview_steps
from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.fixes import fixes_for
from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.ops import ORIGINALS_KEY, export_xml
from controlm_chain_admin.core.package import build_package
from controlm_chain_admin.core.refactor import adopt_jobname, apply
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.core.take import items_of, take, takeable
from controlm_chain_admin.core.validate import validate
from tests.support.fourenvs import CHAIN, INGEST, four_branches, repeated_name, with_map
from tests.support.gitrepo import commit_all, git, plain_git_identity

BENCH, UAT, MINE = "env/bench", "env/uat", "work/names"
NUMBERED = f"{CHAIN}/P77_A2"
TODAY = "2026-11-12"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    """Four environments with ``P77_A`` in two folders, numbered at the import, and the map;
    a branch of one's own from uat's is checked out."""
    built = four_branches(tmp_path, change=repeated_name, numbered=True)
    with_map(built)
    git(built.root, "switch", "-q", "-c", MINE, UAT)
    return load_repo(built.root)


def _originals(repo: ChainRepo, folder: str = CHAIN) -> dict[str, str]:
    return dict(read_json(repo.folder_meta_file(folder)).get(ORIGINALS_KEY, {}))


def _adopted(repo: ChainRepo) -> ChainRepo:
    apply(repo, adopt_jobname(repo, NUMBERED))
    commit_all(repo.root, "feat: P77_A2 is its name")
    return load_repo(repo.root)


def test_the_numbered_name_becomes_the_jobname_and_its_conditions_follow(repo: ChainRepo) -> None:
    before = {link.name for link in load_links(repo).values()}

    change = adopt_jobname(repo, NUMBERED)
    apply(repo, change)
    repo = load_repo(repo.root)

    assert change.summary == (
        f"JOBNAME of {NUMBERED} in Control-M: P77_A -> P77_A2; 2 condition name(s) updated"
    )
    assert _originals(repo) == {"P77_F2": "P77_F"}  # the other numbered job is as it was
    names = {link.name for link in load_links(repo).values()}
    assert names - before == {"P77_A2-P77_B_OK", "P77_A2-P77_C_OK"}
    assert before - names == {"P77_A-P77_B_OK", "P77_A-P77_C_OK"}
    xml = export_xml(repo, "uat", jobnames="original")
    assert xml.count(b'JOBNAME="UP77_A2"') == 1 and xml.count(b'JOBNAME="UP77_A"') == 1
    assert b"UP77_A2-UP77_B_OK" in xml and b"UP77_A-UP77_B_OK" not in xml
    found = {f.node for f in validate(repo, write_index=False).findings
             if f.code == "repeated-jobname"}  # fmt: skip
    assert found == {f"{CHAIN}/P77_F2"}


def test_only_a_job_the_import_numbered_can_adopt_its_name(repo: ChainRepo) -> None:
    with pytest.raises(ChainError, match="its JOBNAME is its own already"):
        adopt_jobname(repo, f"{INGEST}/P77_A")
    with pytest.raises(ChainError, match="unknown job"):
        adopt_jobname(repo, f"{CHAIN}/P77_NOWHERE")


def test_the_conditions_can_be_left_as_they_are(repo: ChainRepo) -> None:
    change = adopt_jobname(repo, NUMBERED, update_names=False)

    assert change.summary == f"JOBNAME of {NUMBERED} in Control-M: P77_A -> P77_A2"
    assert [edit.path for edit in change.edits] == [f"meta/folders/{CHAIN}.json"]


def test_the_finding_offers_it_as_its_fix(repo: ChainRepo) -> None:
    findings = [f for f in validate(repo, write_index=False).findings
                if f.code == "repeated-jobname" and f.node == NUMBERED]  # fmt: skip

    ((fix,),) = fixes_for(repo, findings)

    assert (fix.kind, fix.op, fix.params) == ("keep-number", "adopt-jobname", {"node": NUMBERED})
    assert fix.title == "Make the numbered name the JOBNAME"
    assert fix.label == f"JOBNAME of {NUMBERED}: P77_A -> P77_A2"
    assert [(e.node, e.element, e.before, e.after) for e in fix.effects] == [
        (NUMBERED, "JOBNAME", "P77_A", "P77_A2"),
        (NUMBERED, "condition name", "P77_A-P77_B_OK", "P77_A2-P77_B_OK"),
        (f"{CHAIN}/P77_B", "condition name", "P77_A-P77_B_OK", "P77_A2-P77_B_OK"),
        (NUMBERED, "condition name", "P77_A-P77_C_OK", "P77_A2-P77_C_OK"),  # nobody waits
    ]


def test_it_is_a_capability_and_a_command(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    preview = preview_steps(repo, [{"do": "adopt-jobname", "params": {"node": NUMBERED}}])
    assert {"where": NUMBERED, "field": "JOBNAME", "before": "P77_A", "after": "P77_A2"} in (
        preview["changes"]
    )

    assert main(["adopt-jobname", NUMBERED, "--repo", str(repo.root), "--stat"]) == 0
    assert "JOBNAME of P77_CHAIN/P77_A2 in Control-M: P77_A -> P77_A2" in capsys.readouterr().out
    assert _originals(repo) == {"P77_A2": "P77_A", "P77_F2": "P77_F"}  # a preview
    assert main(["adopt-jobname", NUMBERED, "--repo", str(repo.root), "--apply"]) == 0
    assert _originals(load_repo(repo.root)) == {"P77_F2": "P77_F"}


def test_the_comparison_shows_the_jobname_as_control_m_has_it(repo: ChainRepo) -> None:
    root = _adopted(repo).root

    same_env, other_env = compare(root, UAT, MINE), compare(root, BENCH, MINE)

    for result in (same_env, other_env):
        (job,) = [j for j in result.jobs if j.node == NUMBERED]
        assert job.change == "modified"
        assert [(a.name, a.before, a.after) for a in job.attributes] == [
            ("JOBNAME", "P77_A", "P77_A2")
        ]
        assert f"attr:{NUMBERED}@JOBNAME" in [item for item, _ in items_of(result)]
    assert compare(root, UAT, UAT).jobs == ()  # numbered on both sides: nothing to show
    renamed = [(c.before, c.after) for c in same_env.links if c.change == "renamed"]
    assert sorted(renamed) == [
        ("P77_A-P77_B_OK", "P77_A2-P77_B_OK"),
        ("P77_A-P77_C_OK", "P77_A2-P77_C_OK"),
    ]


def test_the_package_writes_the_new_name_for_the_environment_that_receives(
    repo: ChainRepo,
) -> None:
    root = _adopted(repo).root

    whole = build_package(root, UAT, MINE, today=TODAY)
    chosen = build_package(root, "main", MINE, take=[f"attr:{NUMBERED}@JOBNAME"], today=TODAY)

    assert [f.name for f in whole.folders] == [CHAIN]
    assert b'JOBNAME="UP77_A2"' in whole.require_xml()
    xml = chosen.require_xml()
    assert chosen.env == "prod" and xml.count(b'JOBNAME="PP77_A2"') == 1
    assert b'JOBNAME="PP77_F"' in xml and xml.count(b'JOBNAME="PP77_F"') == 2  # still repeated
    assert b"PP77_A-PP77_B_OK" in xml  # the condition is another item, not taken here


def test_the_name_is_taken_into_another_environment_with_its_condition(repo: ChainRepo) -> None:
    root = _adopted(repo).root
    git(root, "switch", "-q", BENCH)
    bench = load_repo(root)
    listed = {item for item, _ in takeable(root, "HEAD", MINE).items}
    links = sorted(i for i in listed if i.startswith("link:"))

    apply(bench, take(bench, BENCH, MINE, [f"attr:{NUMBERED}@JOBNAME", *links]))
    bench = load_repo(root)

    assert f"attr:{NUMBERED}@JOBNAME" in listed
    assert _originals(bench) == {"P77_F2": "P77_F"}
    xml = export_xml(bench, "bench", jobnames="original")
    assert b'JOBNAME="BP77_A2"' in xml and b"BP77_A2-BP77_B_OK" in xml


def test_a_whole_job_taken_comes_with_the_name_it_has(repo: ChainRepo) -> None:
    root = _adopted(repo).root
    git(root, "switch", "-q", BENCH)
    bench = load_repo(root)

    apply(bench, take(bench, BENCH, MINE, [f"job:{NUMBERED}"]))

    assert _originals(load_repo(root)) == {"P77_F2": "P77_F"}
