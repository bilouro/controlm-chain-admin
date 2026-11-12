"""A directory in memory behaves like one on disk, for what the core does with a directory."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest

from controlm_chain_admin.core.memfs import (
    MemPath,
    copy_file,
    copy_tree,
    memory_dir,
    move,
    remove_tree,
)
from controlm_chain_admin.core.repo import read_json, write_json


def _both(tmp_path: Path):  # type: ignore[no-untyped-def]
    """The same assertions run on a real directory and on a memory one."""
    with memory_dir("test") as mem:
        yield from (tmp_path / "disk", mem / "disk")


@pytest.fixture(params=["disk", "memory"])
def root(request: pytest.FixtureRequest, tmp_path: Path):  # type: ignore[no-untyped-def]
    if request.param == "disk":
        yield tmp_path / "root"
    else:
        with memory_dir("test") as mem:
            yield mem / "root"


def test_files_and_directories_are_made_listed_and_removed(root: Path) -> None:
    assert not root.exists()
    (root / "folders" / "F1" / "jobs").mkdir(parents=True)
    (root / "folders" / "F1" / "folder.json").write_text("{}", encoding="utf-8")
    (root / "folders" / "F1" / "jobs" / "A.json").write_bytes(b'{"a": 1}')
    (root / "folders" / "F2").mkdir()
    (root / "chain.json").write_text("{}\n", encoding="utf-8", newline="\n")

    assert root.is_dir() and (root / "chain.json").is_file()
    assert not (root / "folders").is_file() and not (root / "nothing").exists()
    assert sorted(p.name for p in (root / "folders").iterdir()) == ["F1", "F2"]
    assert [p.name for p in sorted(root.glob("folders/*/folder.json"))] == ["folder.json"]
    assert sorted(p.name for p in root.rglob("*.json")) == ["A.json", "chain.json", "folder.json"]
    job = root / "folders" / "F1" / "jobs" / "A.json"
    assert (job.name, job.stem, job.suffix, job.parent.name) == ("A.json", "A", ".json", "jobs")
    assert job.relative_to(root).as_posix() == "folders/F1/jobs/A.json"
    assert PurePosixPath(job.relative_to(root).as_posix()).parts[0] == "folders"
    assert job.with_name("B.json").name == "B.json" and job.stat().st_size == 8
    assert root.joinpath("folders", "F1") == root / "folders" / "F1"
    assert len({root / "x", root / "x"}) == 1

    job.unlink()
    job.unlink(missing_ok=True)
    with pytest.raises(FileNotFoundError):
        job.unlink()
    with pytest.raises(FileNotFoundError):
        job.read_bytes()
    with pytest.raises(OSError):
        (root / "folders").rmdir()  # not empty
    (root / "folders" / "F2").rmdir()
    assert sorted(p.name for p in (root / "folders").iterdir()) == ["F1"]


def test_writing_needs_the_directory_and_mkdir_says_what_is_there(root: Path) -> None:
    with pytest.raises(FileNotFoundError):
        (root / "a" / "b.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        (root / "a" / "b").mkdir()
    root.mkdir()
    root.mkdir(exist_ok=True)
    with pytest.raises(FileExistsError):
        root.mkdir()


def test_text_is_read_and_written_as_on_disk(root: Path) -> None:
    root.mkdir()
    with (root / "a.txt").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("one\ntwo\n")
    (root / "crlf.txt").write_bytes(b"one\r\ntwo\r\n")
    with (root / "a.txt").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("three\n")

    assert (root / "a.txt").read_bytes() == b"one\ntwo\nthree\n"
    assert (root / "crlf.txt").read_text(encoding="utf-8") == "one\ntwo\n"
    with (root / "a.txt").open(encoding="utf-8") as handle:
        assert handle.readline() == "one\n"
    with (root / "a.txt").open("rb") as raw:
        assert raw.read(3) == b"one"


def test_the_json_helpers_of_the_core_work_on_both(root: Path) -> None:
    write_json(root / "deep" / "x.json", {"é": [1, 2]})

    assert read_json(root / "deep" / "x.json") == {"é": [1, 2]}
    assert (root / "deep" / "x.json").read_bytes() == (
        json.dumps({"é": [1, 2]}, indent=2, ensure_ascii=False) + "\n"
    ).encode()


def test_trees_are_copied_moved_and_removed_between_disk_and_memory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "sub" / "empty").mkdir(parents=True)
    (source / "sub" / "a.txt").write_bytes(b"a")
    (source / "top.txt").write_bytes(b"top")

    with memory_dir("copies") as mem:
        copy_tree(source, mem / "in")
        copy_tree(mem / "in", mem / "again")
        copy_tree(mem / "again", tmp_path / "out")
        copy_file(mem / "in" / "top.txt", tmp_path / "one.txt")
        move(mem / "again" / "sub", mem / "moved")
        remove_tree(mem / "in")

        assert isinstance(mem, MemPath) and not (mem / "in").exists()
        assert (mem / "moved" / "a.txt").read_bytes() == b"a"
        assert (mem / "moved" / "empty").is_dir()
        assert not (mem / "again" / "sub").exists() and (mem / "again" / "top.txt").is_file()
        with pytest.raises(FileExistsError):
            copy_tree(source, mem / "again")
        remove_tree(mem / "nowhere", ignore_errors=True)
    assert (tmp_path / "out" / "sub" / "a.txt").read_bytes() == b"a"
    assert (tmp_path / "out" / "sub" / "empty").is_dir()
    assert (tmp_path / "one.txt").read_bytes() == b"top"


def test_a_memory_directory_is_gone_with_its_block_and_stays_inside() -> None:
    with memory_dir("gone") as mem:
        (mem / "a.txt").write_bytes(b"a")
        with pytest.raises(ValueError, match="leaves the directory"):
            mem / ".." / "x"
        assert str(mem / "a.txt") == "<memory gone>/a.txt"
    assert not (mem / "a.txt").exists()
