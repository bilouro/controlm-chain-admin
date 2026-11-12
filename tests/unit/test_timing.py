"""Where the time of an operation goes: phases and counters, collected only when asked."""

from __future__ import annotations

from pathlib import Path

from controlm_chain_admin.core.repo import read_json, write_json
from controlm_chain_admin.core.timing import collect, count, phase


def test_nothing_is_collected_unless_asked() -> None:
    with phase("idle"):
        count("things")  # no collector: nothing to record, nothing fails


def test_phases_and_counters_of_what_ran_inside() -> None:
    with collect() as seen:
        with phase("first"):
            count("things", 2)
        with phase("first"):
            count("things")
        with phase("second"):
            pass

    assert list(seen.phases) == ["first", "second"]
    assert seen.phases["first"] >= 0 and seen.calls["first"] == 2
    assert seen.counts == {"things": 3}
    assert seen.total >= seen.phases["first"]
    assert seen.to_json()["counts"] == {"things": 3}


def test_a_collection_ends_with_its_block() -> None:
    with collect() as seen:
        count("inside")
    count("outside")

    assert seen.counts == {"inside": 1}


def test_the_json_files_read_and_written_are_counted(tmp_path: Path) -> None:
    with collect() as seen:
        write_json(tmp_path / "a.json", {"a": 1})
        read_json(tmp_path / "a.json")
        read_json(tmp_path / "a.json")

    assert seen.counts == {"files_written": 1, "files_read": 2}
