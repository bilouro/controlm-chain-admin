"""The map of what varies from one environment to another: kept on a branch of its own,
derived from the environments' branches, completed by hand."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from controlm_chain_admin.core.envmap import (
    EnvMap,
    MapEntry,
    add_entry,
    derive,
    read_map,
    remove_entry,
    rename_entry,
    suggest,
    write_map,
)
from controlm_chain_admin.core.errors import ChainError, GitError
from controlm_chain_admin.core.refresh import refresh
from tests.support.envexports import job
from tests.support.fourenvs import CENTERS, ENVS, HOSTS, USERS, export_of, four_branches
from tests.support.gitrepo import git, plain_git_identity


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


USER = MapEntry("run_as.1", "RUN_AS", USERS)


# ---------------------------------------------------------------- the branch of the map


def test_without_the_branch_the_map_is_empty(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)

    assert read_map(repo.root, repo.config) == EnvMap()


def test_the_map_lives_on_a_branch_of_its_own_and_no_checkout_is_needed(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    head = git(repo.root, "rev-parse", "HEAD")

    first = write_map(repo.root, repo.config, EnvMap((USER,)), "map: the users")

    assert read_map(repo.root, repo.config) == EnvMap((USER,))
    assert git(repo.root, "branch", "--show-current") == "main"
    assert git(repo.root, "rev-parse", "HEAD") == head and git(repo.root, "status", "-s") == ""
    assert git(repo.root, "ls-tree", "--name-only", "map") == "map.json"
    with pytest.raises(subprocess.CalledProcessError):  # an orphan: no common history
        git(repo.root, "merge-base", "main", "map")

    more = add_entry(EnvMap((USER,)), "DATACENTER", CENTERS, environments=ENVS)
    second = write_map(repo.root, repo.config, more, "map: the datacenters")

    assert git(repo.root, "rev-parse", "map^") == first and second != first
    assert git(repo.root, "log", "-1", "--format=%s", "map") == "map: the datacenters"
    assert write_map(repo.root, repo.config, more, "map: again") is None  # nothing new


def test_a_map_that_cannot_be_read_says_so(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    git(repo.root, "branch", "map", "main")  # a branch called map, without the file

    with pytest.raises(GitError, match=r"map\.json"):
        read_map(repo.root, repo.config)


# ---------------------------------------------------------------- entries by hand


def test_entries_are_added_named_renamed_and_removed() -> None:
    one = add_entry(EnvMap(), "RUN_AS", USERS, environments=ENVS)
    two = add_entry(one, "RUN_AS", {"prod": "root", "uat": "admin"}, environments=ENVS)
    text = add_entry(two, "DOMAIL/@SUBJECT", {"prod": "PROD", "uat": "UAT"}, inline=True,
                     name="env.code", environments=ENVS)  # fmt: skip

    assert [e.name for e in text.entries] == ["run_as.1", "run_as.2", "env.code"]
    assert text.entries[2].inline and text.entries[2].to_json() == {
        "name": "env.code", "key": "DOMAIL/@SUBJECT", "values": {"prod": "PROD", "uat": "UAT"},
        "inline": True,
    }  # fmt: skip
    assert EnvMap.from_json(text.to_json()) == text

    renamed = rename_entry(text, "run_as.2", "user.admin")
    assert [e.name for e in renamed.entries] == ["run_as.1", "user.admin", "env.code"]
    left = remove_entry(renamed, "run_as.1")
    assert [e.name for e in left.entries] == ["user.admin", "env.code"]


@pytest.mark.parametrize(
    ("key", "values", "message"),
    [
        ("RUN_AS", {"prod": "a", "nowhere": "b"}, "nowhere"),
        ("RUN_AS", {"prod": "a"}, "two environments"),
        ("RUN_AS", {"prod": "a", "uat": "a"}, "the same value"),
        ("RUN AS", {"prod": "a", "uat": "b"}, "invalid attribute spec"),
        ("RUN_AS", USERS, "already"),
    ],
)
def test_entries_that_make_no_sense_are_refused(
    key: str, values: dict[str, str], message: str
) -> None:
    with pytest.raises(ChainError, match=message):
        add_entry(EnvMap((USER,)), key, values, environments=ENVS)


def test_unknown_names_are_refused() -> None:
    with pytest.raises(ChainError, match="no entry"):
        remove_entry(EnvMap((USER,)), "nodeid.9")
    with pytest.raises(ChainError, match="already"):
        rename_entry(EnvMap((USER, MapEntry("x", "NODEID", HOSTS))), "x", "run_as.1")


# ---------------------------------------------------------------- derived from the branches


def test_the_map_is_derived_from_what_the_branches_show(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)

    found = derive(repo.root, repo.config, EnvMap())

    assert found.environments == ENVS
    assert [(e.name, e.key, dict(e.values)) for e in found.entries] == [
        ("nodeid.1", "NODEID", HOSTS),
        ("run_as.1", "RUN_AS", USERS),
        ("datacenter.1", "DATACENTER", CENTERS),
    ]
    # the user of the 2 folders and their 9 jobs; the machine of the 7 jobs of one folder (the
    # machine group of the others is named with the letter, UP77_BATCH: not for the map)
    assert found.nodes == {"nodeid.1": 7, "run_as.1": 11, "datacenter.1": 2}
    assert found.left_out == () and found.envmap.entries == found.entries


def test_what_one_node_alone_shows_is_left_out_of_the_map(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    odd = job(export_of("bench"), b"BP77_C", b'RUN_AS="abp77proc"', b'RUN_AS="special"')
    refresh(repo, odd, source="bench.xml", apply=True)

    found = derive(repo.root, repo.config, EnvMap())

    assert found.nodes["run_as.1"] == 10
    assert [(o.key, dict(o.values), o.nodes) for o in found.left_out] == [
        ("RUN_AS", {**USERS, "bench": "special"}, 1)
    ]
    assert len(derive(repo.root, repo.config, EnvMap(), min_nodes=1).entries) == 4


def test_deriving_again_adds_only_what_is_new(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    known = derive(repo.root, repo.config, EnvMap(), keys=("RUN_AS",)).envmap
    assert [e.name for e in known.entries] == ["run_as.1"]

    found = derive(repo.root, repo.config, known)

    assert [e.name for e in found.entries] == ["nodeid.1", "datacenter.1"]
    assert [e.name for e in found.envmap.entries] == ["run_as.1", "nodeid.1", "datacenter.1"]
    assert derive(repo.root, repo.config, found.envmap).entries == ()


def test_a_text_is_derived_by_the_one_word_that_varies(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)

    found = derive(repo.root, repo.config, EnvMap(), keys=(), text_keys=("DOMAIL/@SUBJECT",),
                   min_nodes=1)  # fmt: skip

    assert [(e.name, e.key, e.inline, dict(e.values)) for e in found.entries] == [
        ("subject.1", "DOMAIL/@SUBJECT", True,
         {"prod": "PROD", "uat": "UAT", "egma": "EGMA", "bench": "BENCH"})
    ]  # fmt: skip


def test_two_environments_are_needed_to_derive(tmp_path: Path) -> None:
    repo = four_branches(tmp_path, envs=("prod",))

    with pytest.raises(ChainError, match="two environments"):
        derive(repo.root, repo.config, EnvMap())


# ---------------------------------------------------------------- what else varies


def test_what_else_varies_is_suggested_with_counts(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    known = derive(repo.root, repo.config, EnvMap()).envmap

    found = {s.key: s for s in suggest(repo.root, repo.config, known)}

    assert set(found) == {"VARIABLE[NAME=%%GEIENV]/@VALUE", "DOMAIL/@SUBJECT"}
    env = found["VARIABLE[NAME=%%GEIENV]/@VALUE"]
    assert (env.nodes, env.tuples, env.text) == (1, 1, False)
    subject = found["DOMAIL/@SUBJECT"]
    assert (subject.nodes, subject.tuples, subject.text) == (1, 1, True)
    assert dict(subject.example) == {"prod": "PROD", "uat": "UAT", "egma": "EGMA",
                                     "bench": "BENCH"}  # fmt: skip
