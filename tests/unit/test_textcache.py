"""The files of the repository are read once: remembered until they change, and the first
time taken from git in one piece."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from controlm_chain_admin.core import textcache
from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.repo import load_repo, read_json, write_json
from controlm_chain_admin.core.timing import collect
from controlm_chain_admin.core.validate import validate
from tests.support.gitrepo import chain_git_repo, commit_all, git, plain_git_identity


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Nothing remembered, and a file trusted as soon as it is remembered (the tests that
    follow count readings; the grain of the clock has its own test)."""
    plain_git_identity(monkeypatch, tmp_path)
    textcache.clear()
    monkeypatch.setattr(textcache, "RACY_NS", 0)


def test_a_file_is_opened_once_and_again_only_when_it_changed(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text('{"a": 1}\n', encoding="utf-8")

    with collect() as seen:
        first, again = read_json(path), read_json(path)
        first["a"] = 99  # what is given out is the caller's own
        third = read_json(path)
        path.write_text('{"a": 2, "b": 3}\n', encoding="utf-8")
        changed = read_json(path)

    assert (again, third, changed) == ({"a": 1}, {"a": 1}, {"a": 2, "b": 3})
    assert seen.counts == {"files_read": 2, "files_remembered": 2}


def test_a_change_of_the_same_size_is_seen_by_its_time(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text('{"a": 1}\n', encoding="utf-8")
    read_json(path)
    path.write_text('{"a": 2}\n', encoding="utf-8")
    later = os.stat(path).st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))

    assert read_json(path) == {"a": 2}


def test_a_file_changed_just_before_it_was_read_is_read_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(textcache, "RACY_NS", 60_000_000_000)  # a clock with a minute's grain
    path = tmp_path / "a.json"
    path.write_text('{"a": 1}\n', encoding="utf-8")
    read_json(path)
    status = os.stat(path)
    path.write_text('{"a": 2}\n', encoding="utf-8")  # the same size
    os.utime(path, ns=(status.st_atime_ns, status.st_mtime_ns))  # and the time did not move

    with collect() as seen:
        assert read_json(path) == {"a": 2}
        write_json(path, {"a": 2})  # not known to hold it: written

    assert seen.counts["files_read"] == 1 and seen.counts["files_written"] == 1


def test_what_was_written_is_not_read_back_nor_written_twice(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "a.json"

    with collect() as seen:
        write_json(path, {"a": 1})
        back = read_json(path)
        write_json(path, {"a": 1})  # the same again: nothing to write
        write_json(path, {"a": 2})

    assert back == {"a": 1} and read_json(path) == {"a": 2}
    assert seen.counts["files_written"] == 2 and "files_read" not in seen.counts


def test_a_file_with_windows_line_ends_is_still_normalised_when_written(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_bytes(b'{\r\n  "a": 1\r\n}\r\n')

    assert read_json(path) == {"a": 1}
    write_json(path, {"a": 1})

    assert path.read_bytes() == b'{\n  "a": 1\n}\n'


def test_a_missing_or_broken_file_is_said_as_before(tmp_path: Path) -> None:
    from controlm_chain_admin.core.errors import ModelError

    (tmp_path / "bad.json").write_text("{", encoding="utf-8")

    with pytest.raises(ModelError, match="missing file"):
        read_json(tmp_path / "nothing.json")
    with pytest.raises(ModelError, match="invalid JSON"):
        read_json(tmp_path / "bad.json")


def test_the_first_reading_of_a_clean_working_tree_comes_from_git(tmp_path: Path) -> None:
    root = chain_git_repo(tmp_path).root
    textcache.clear()

    with collect() as first:
        links = load_links(load_repo(root))
    with collect() as again:
        load_links(load_repo(root))

    assert links and first.counts.get("trees_from_git") == 1
    assert first.counts.get("files_read", 0) == 0  # every committed file came in one piece
    assert again.counts.get("files_read", 0) == 0 and "trees_from_git" not in again.counts
    assert again.counts.get("git_calls", 0) == 0


def test_an_uncommitted_change_is_read_from_the_file(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    job = repo.job_file("P77_CHAIN", "P77_A")
    data = {**read_json(job), "CMDLINE": "/opt/p77/bin/changed.ksh"}
    job.write_text(__import__("json").dumps(data), encoding="utf-8")
    textcache.clear()

    with collect() as seen:
        got = read_json(job)

    assert got["CMDLINE"] == "/opt/p77/bin/changed.ksh" and seen.counts["files_read"] == 1


def test_another_commit_checked_out_is_read_from_git_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = chain_git_repo(tmp_path)
    root, job = repo.root, repo.job_file("P77_CHAIN", "P77_A")
    monkeypatch.setattr(textcache, "_RECHECK", 0.0)
    git(root, "switch", "-q", "-c", "work/next")
    write_json(job, {**read_json(job), "CMDLINE": "/opt/p77/bin/next.ksh"})
    commit_all(root, "feat: next")
    load_links(load_repo(root))
    git(root, "switch", "-q", "main")

    with collect() as seen:
        back = read_json(job)

    assert back["CMDLINE"] != "/opt/p77/bin/next.ksh"
    assert seen.counts.get("trees_from_git") == 1 and seen.counts.get("files_read", 0) == 0


def test_validation_writes_its_index_once(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    validate(repo)

    with collect() as seen:
        report = validate(load_repo(repo.root))

    assert report.findings and seen.counts.get("files_written", 0) == 0
    assert seen.counts.get("files_read", 0) == 0
