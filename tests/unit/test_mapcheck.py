"""What the map knows, said by ``validate``; and the jobs of one entry made to follow another."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.envmap import read_map
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.fixes import fixes_for
from controlm_chain_admin.core.mapcheck import follow_entry, survey
from controlm_chain_admin.core.refactor import apply
from controlm_chain_admin.core.refresh import refresh
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.core.validate import Finding, validate
from tests.support.envexports import job
from tests.support.fourenvs import (
    CHAIN,
    HOSTS,
    INGEST,
    LETTERS,
    USERS,
    export_of,
    four_branches,
    two_users_in,
    with_map,
)
from tests.support.gitrepo import commit_all, git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"
B = f"{CHAIN}/P77_B"
MAP_CODES = ("foreign-value", "unmapped-difference", "ambiguous-map", "suspect-map-entry")


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def _on(repo: ChainRepo, branch: str) -> ChainRepo:
    git(repo.root, "switch", "-q", branch)
    return load_repo(repo.root)


def _found(repo: ChainRepo, code: str) -> list[Finding]:
    return [f for f in validate(repo, write_index=False).findings if f.code == code]


def _with(env_in: str, before: Callable[[str], bytes], after: Callable[[str], bytes]):  # type: ignore[no-untyped-def]
    """An export change: in ``env_in``, on the line of ``P77_B``, ``before`` becomes ``after``."""

    def change(env: str, data: bytes) -> bytes:
        if env != env_in:
            return data
        return job(data, f"{LETTERS[env]}P77_B".encode(), before(env), after(env))

    return change


def _prod_user_in_bench(tmp_path: Path) -> ChainRepo:
    """bench runs ``P77_B`` as the user of production: the map derived from the branches has
    that as an entry of its own, ``run_as.2``."""
    repo = four_branches(
        tmp_path,
        change=_with(
            "bench",
            lambda env: b'RUN_AS="%s"' % USERS[env].encode(),
            lambda env: b'RUN_AS="%s"' % USERS["prod"].encode(),
        ),
    )
    with_map(repo)
    return repo


def test_a_value_of_another_environment_on_this_branch(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)  # the map of four environments that agree
    wrong = job(export_of("uat"), b"UP77_B", HOSTS["uat"].encode(), HOSTS["prod"].encode())
    refresh(load_repo(repo.root), wrong, source="uat.xml", apply=True)
    repo = _on(repo, UAT)

    (finding,) = _found(repo, "foreign-value")
    ((fix,),) = fixes_for(repo, [finding])

    assert (finding.severity, finding.node, finding.name) == ("warning", B, "nodeid.1")
    assert finding.message == (
        f"NODEID is {HOSTS['prod']}, what prod has in the map (nodeid.1): uat has "
        f"{HOSTS['uat']} there"
    )
    assert (fix.kind, fix.op) == ("map-value", "set-attributes")
    assert fix.params == {"node": B, "changes": {"NODEID": HOSTS["uat"]}}
    assert _found(_on(repo, BENCH), "foreign-value") == []  # bench has its own value


def test_a_difference_no_entry_of_the_map_says(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)
    odd = job(export_of("uat"), b"UP77_B", HOSTS["uat"].encode(), b"srvu-odd9")
    refresh(load_repo(repo.root), odd, source="uat.xml", apply=True)
    repo = _on(repo, UAT)

    (finding,) = _found(repo, "unmapped-difference")

    assert (finding.severity, finding.node, finding.name) == ("info", B, "NODEID")
    assert "uat has srvu-odd9" in finding.message and "1 place" in finding.message
    assert "no entry of the map says" in finding.message
    assert _found(repo, "foreign-value") == []


def test_a_value_the_map_gives_two_answers_for(tmp_path: Path) -> None:
    repo = four_branches(tmp_path, change=two_users_in("bench"))
    with_map(repo)
    repo = _on(repo, UAT)

    (finding,) = _found(repo, "ambiguous-map")

    assert (finding.severity, finding.node, finding.name) == ("info", "", "RUN_AS")
    assert finding.message.startswith(
        f"{USERS['uat']} of uat stands for two values of bench in the map "
        f"(run_as.1: {USERS['bench']}, run_as.2: abp77adm)"
    )
    assert _found(_on(repo, BENCH), "ambiguous-map") == []  # from bench each has one answer


def test_an_entry_that_is_another_with_one_environment_set_up_like_a_third(
    tmp_path: Path,
) -> None:
    repo = _on(_prod_user_in_bench(tmp_path), BENCH)

    (finding,) = _found(repo, "suspect-map-entry")
    ((fix,),) = fixes_for(repo, [finding])

    assert (finding.severity, finding.node, finding.name) == ("info", "", "run_as.2")
    assert finding.message == (
        f"run_as.2 is run_as.1 with bench having {USERS['prod']}, the value of prod: if bench "
        "was set up wrongly, its 1 place(s) can follow run_as.1"
    )
    assert (fix.kind, fix.op) == ("follow-entry", "follow-entry")
    assert fix.params == {"entry": "run_as.2", "other": "run_as.1"}
    (elsewhere,) = _found(_on(repo, UAT), "suspect-map-entry")
    assert fixes_for(load_repo(repo.root), [elsewhere]) == [()]  # bench is where it is fixed


def test_who_follows_each_entry(tmp_path: Path) -> None:
    repo = _prod_user_in_bench(tmp_path)

    seen = survey(repo.root)

    assert [(p.node, p.attribute) for p in seen.followers["run_as.2"]] == [(B, "RUN_AS")]
    assert B not in {p.node for p in seen.followers["run_as.1"]}
    assert len(seen.followers["run_as.1"]) > 3 and seen.unmapped == ()
    assert seen.counts()["run_as.2"] == 1


def test_the_jobs_of_an_entry_follow_another_on_the_branch_of_the_environment(
    tmp_path: Path,
) -> None:
    repo = _on(_prod_user_in_bench(tmp_path), BENCH)
    git(repo.root, "switch", "-q", "-c", "work/bench-users")
    repo = load_repo(repo.root)

    change = follow_entry(repo, "run_as.2", "run_as.1")
    apply(repo, change)
    commit_all(repo.root, "fix: P77_B runs as bench's user")

    assert change.summary == (
        f"1 place(s) of bench follow run_as.1 instead of run_as.2: RUN_AS {USERS['prod']} -> "
        f"{USERS['bench']}"
    )
    assert read_json(repo.job_file(CHAIN, "P77_B"))["RUN_AS"] == USERS["bench"]
    (changed,) = compare(repo.root, BENCH, "work/bench-users").jobs
    assert changed.node == B and [a.name for a in changed.attributes] == ["RUN_AS"]
    assert survey(repo.root).followers.get("run_as.2", ()) != ()  # until bench's branch has it


def test_following_is_refused_where_it_would_change_nothing_or_cannot_be(tmp_path: Path) -> None:
    repo = _prod_user_in_bench(tmp_path)

    with pytest.raises(ChainError, match="have the same value for uat"):
        follow_entry(_on(repo, UAT), "run_as.2", "run_as.1")
    bench = _on(repo, BENCH)
    with pytest.raises(ChainError, match=r"no entry called 'run_as\.9'"):
        follow_entry(bench, "run_as.2", "run_as.9")
    with pytest.raises(ChainError, match="not entries of the same key"):
        follow_entry(bench, "run_as.2", "nodeid.1")


def test_a_word_inside_a_text_follows_too(tmp_path: Path) -> None:
    repo = four_branches(
        tmp_path,
        change=lambda env, data: data.replace(b"[BENCH]", b"[PROD]") if env == "bench" else data,
    )
    with_map(repo)
    repo = _on(repo, BENCH)
    names = [e.name for e in read_map(repo.root, repo.config).entries if e.inline]
    assert names == ["subject.1"]  # one job has a subject: the entry is that job's

    wrong = {"prod": "PROD", "uat": "UAT", "egma": "EGMA", "bench": "BENCH"}
    assert main(["envmap", "add", "DOMAIL/@SUBJECT", "--text", "--as", "subject.2",
                 *(f"{env}={word}" for env, word in wrong.items()),
                 "--repo", str(repo.root)]) == 0  # fmt: skip
    change = follow_entry(load_repo(repo.root), "subject.1", "subject.2")

    assert change.summary.endswith("DOMAIL/@SUBJECT PROD -> BENCH")
    (edit,) = change.edits
    assert "[P77][BENCH] Load failed" in (edit.after or "") and INGEST in edit.path


def test_the_command_previews_and_applies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _on(_prod_user_in_bench(tmp_path), BENCH)
    git(repo.root, "switch", "-q", "-c", "work/bench-users")
    root = str(repo.root)

    assert main(["envmap", "followers", "--repo", root]) == 0
    listed = capsys.readouterr().out
    assert main(["envmap", "follow", "run_as.2", "run_as.1", "--repo", root, "--stat"]) == 0
    preview = capsys.readouterr().out
    assert main(["envmap", "follow", "run_as.2", "run_as.1", "--repo", root, "--apply"]) == 0

    assert "run_as.2  1 place(s)" in listed
    assert "1 place(s) of bench follow run_as.1 instead of run_as.2" in preview
    assert read_json(load_repo(repo.root).job_file(CHAIN, "P77_B"))["RUN_AS"] == USERS["bench"]


def test_without_branches_or_a_map_validate_says_nothing_of_it(tmp_path: Path) -> None:
    from tests.support.gitrepo import chain_git_repo

    plain = chain_git_repo(tmp_path)

    assert not [f for f in validate(plain, write_index=False).findings if f.code in MAP_CODES]
