"""Two environments compared in the terms of one of them: what the map and the letters say
varies is translated first, so that only the real differences are left."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare, render_markdown, render_text
from controlm_chain_admin.core.envmap import add_entry, read_map, write_map
from controlm_chain_admin.core.errors import ChainError, GitError
from controlm_chain_admin.core.selection import open_sides
from tests.support.envexports import job
from tests.support.fourenvs import (
    ENVS,
    HOSTS,
    LETTERS,
    USERS,
    administrator,
    four_branches,
    two_users_in,
    with_map,
    without_job,
)
from tests.support.gitrepo import plain_git_identity


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def _names(nodes: object) -> set[str]:
    return {a.name for node in nodes for a in node.attributes}  # type: ignore[attr-defined]


# ---------------------------------------------------------------- what is expected to vary


@pytest.mark.parametrize(
    ("base", "head"),
    [("main", "env/uat"), ("env/uat", "main"), ("env/egma", "env/bench"), ("env/bench", "main")],
)
def test_with_the_map_two_environments_that_differ_as_expected_show_no_difference(
    tmp_path: Path, base: str, head: str
) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)

    result = compare(repo.root, base, head)

    assert (result.folders, result.jobs, result.links) == ((), (), ())
    assert result.merge_base is None and result.commits == ()


def test_the_translation_says_what_it_explained(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)

    translation = compare(repo.root, "main", "env/uat").translation

    assert translation is not None
    assert (translation.source, translation.target) == ("uat", "prod")
    # RUN_AS of 2 folders and 9 jobs, NODEID of the 7 jobs on a host, the variable, 2 sidecars
    assert translation.values == 11 + 7 + 1 + 2
    assert translation.letters == 2  # the two jobs on the host group named with the letter
    assert translation.texts == 1  # the mail subject
    assert translation.links == 0 and translation.warnings == ()
    assert translation.to_json()["source"] == "uat"


def test_without_the_map_only_the_letter_is_explained(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)

    result = compare(repo.root, "main", "env/uat")

    assert _names(result.jobs) == {"RUN_AS", "NODEID"}
    assert len([j for j in result.jobs if "NODEID" in _names([j])]) == 7  # not the group's two
    assert result.translation is not None and result.translation.letters == 2


def test_untranslated_the_two_branches_are_compared_as_they_are(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)

    with open_sides(repo.root, "main", "env/uat", translate=False) as sides:
        uat = json.loads(
            (sides.head_root / "folders/P77_CHAIN/jobs/P77_A.json").read_text("utf-8")
        )
        assert sides.translation is None and sides.merge_base is None

    assert (uat["RUN_AS"], uat["NODEID"]) == (USERS["uat"], HOSTS["uat"])


def test_the_same_environment_is_compared_as_before(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)

    assert compare(repo.root, "env/uat", "env/uat").translation is None


def test_commits_cannot_be_selected_across_environments(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)

    with pytest.raises(GitError, match="environments"):
        compare(repo.root, "main", "env/uat", commits=["HEAD"])


# ---------------------------------------------------------------- the real differences


def _uat_changed(env: str, data: bytes) -> bytes:
    if env != "uat":
        return data
    data = job(data, b"UP77_A", b"/opt/p77/bin/a.ksh", b"/opt/p77/bin/a2.ksh -x")
    return without_job(data, "UP77_INGEST_LOAD")


def test_a_real_difference_is_all_that_is_left(tmp_path: Path) -> None:
    repo = four_branches(tmp_path, change=_uat_changed)
    with_map(repo)

    result = compare(repo.root, "main", "env/uat")

    changed = {j.node: j for j in result.jobs}
    assert set(changed) == {
        "P77_CHAIN/P77_A",
        "P77_INGEST_DAILY/P77_INGEST_LOAD",
        "P77_INGEST_DAILY/P77_INGEST_INIT",  # what it emits has nobody waiting for it there
    }
    assert _names([changed["P77_CHAIN/P77_A"]]) == {"CMDLINE"}
    assert changed["P77_INGEST_DAILY/P77_INGEST_LOAD"].change == "removed"
    left = changed["P77_INGEST_DAILY/P77_INGEST_INIT"]
    assert left.attributes == () and [r.change for r in left.relations] == ["modified"]
    assert [f.node for f in result.folders] == ["P77_INGEST_DAILY/"]


def _new_job(env: str, data: bytes) -> bytes:
    if env != "uat":
        return data
    line = next(row for row in data.split(b"\n") if b'JOBNAME="UP77_A"' in row)
    new = line.replace(b"UP77_A", b"UP77_NEW") + b"\n        </JOB>\n"
    return data.replace(line, new + line, 1)


def test_a_node_the_target_lacks_arrives_in_the_targets_terms(tmp_path: Path) -> None:
    repo = four_branches(tmp_path, change=_new_job)
    with_map(repo)

    result = compare(repo.root, "main", "env/uat")

    (added,) = result.jobs
    assert (added.node, added.change) == ("P77_CHAIN/P77_NEW", "added")
    assert added.after is not None
    assert (added.after["RUN_AS"], added.after["NODEID"]) == (USERS["prod"], HOSTS["prod"])


def test_the_technical_attributes_are_translated_too(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)

    with open_sides(repo.root, "env/bench", "env/uat") as sides:
        meta = json.loads((sides.head_root / "meta/folders/P77_CHAIN.json").read_text("utf-8"))

    assert meta["attrs"]["DATACENTER"] == "CTMBENCH"


# ---------------------------------------------------------------- when the map cannot say


def _shared_host(env: str, data: bytes) -> bytes:
    # the job runs on the uat host in every environment
    return job(data, b"%sP77_B" % LETTERS[env].encode(), HOSTS[env].encode(), b"srvu-bat1")


def test_a_value_the_target_has_already_is_kept(tmp_path: Path) -> None:
    repo = four_branches(tmp_path, change=_shared_host)
    with_map(repo)

    result = compare(repo.root, "main", "env/uat")

    assert result.jobs == ()


def _two_users(env: str, data: bytes) -> bytes:
    # prod runs one job as an administrator; uat has one user for everything
    if env == "prod":
        data = job(data, b"PP77_B", b'RUN_AS="app77proc"', b'RUN_AS="app77adm"')
    return _new_job(env, data)


def test_of_two_possible_values_the_one_the_target_has_wins_and_else_none_does(
    tmp_path: Path,
) -> None:
    repo = four_branches(tmp_path, change=_two_users)
    envmap = with_map(repo)
    more = add_entry(envmap, "RUN_AS", {"prod": "app77adm", "uat": USERS["uat"]},
                     environments=ENVS)  # fmt: skip
    write_map(repo.root, repo.config, more, "map: the administrator")
    assert read_map(repo.root, repo.config) == more

    result = compare(repo.root, "main", "env/uat")

    (added,) = result.jobs  # P77_B is not a difference: prod's value is one of the two
    assert added.after is not None and added.after["RUN_AS"] == USERS["uat"]
    assert result.translation is not None
    (warning,) = result.translation.warnings
    assert "RUN_AS" in warning and "app77proc (run_as.1) or app77adm (run_as.2)" in warning
    assert "P77_CHAIN/P77_NEW" in warning and "prefer" in warning


def test_a_preferred_entry_of_the_map_settles_it(tmp_path: Path) -> None:
    repo = four_branches(tmp_path, change=two_users_in("prod"))
    with_map(repo)

    result = compare(repo.root, "main", "env/uat", prefer=("run_as.2",))

    users = {j.node: j.after["RUN_AS"] for j in result.jobs if j.change == "added" and j.after}
    assert users["P77_CHAIN/P77_NEW"] == administrator("prod")
    assert result.translation is not None and result.translation.warnings == ()
    with pytest.raises(ChainError, match=r"no entry called 'run_as\.9'"):
        compare(repo.root, "main", "env/uat", prefer=("run_as.9",))


# ---------------------------------------------------------------- the names of the conditions


def _other_names(env: str, data: bytes) -> bytes:
    letter = LETTERS[env].encode()
    # a condition from another application, whose name carries its letter there too
    data = data.replace(b"%sP77_GHOST-" % letter, b"%sOTH_GHOST-" % letter)
    # a condition between two jobs of the chain, called as each environment likes
    return data.replace(b"%sP77_A-%sP77_B_OK" % (letter, letter), b"%s_A_TO_B" % env.encode())


def test_a_condition_called_another_name_is_not_a_difference(tmp_path: Path) -> None:
    repo = four_branches(tmp_path, change=_other_names)
    with_map(repo)

    result = compare(repo.root, "main", "env/uat")

    assert (result.folders, result.jobs, result.links) == ((), (), ())
    assert result.translation is not None and result.translation.links == 2


def test_what_comes_from_the_other_environment_uses_the_targets_condition_names(
    tmp_path: Path,
) -> None:
    repo = four_branches(tmp_path, change=_other_names)
    with_map(repo)

    with open_sides(repo.root, "main", "env/uat") as sides:
        folder = sides.head_root / "folders/P77_CHAIN"
        a = json.loads((folder / "jobs/P77_A.json").read_text("utf-8"))
        e = json.loads((folder / "jobs/P77_E.json").read_text("utf-8"))
        names = json.loads((folder / "links.json").read_text("utf-8"))["links"]

    assert a["OUTCOND"][0]["link"] == "prod_A_TO_B"
    assert {c["link"] for c in e["INCOND"]} == {"P77_A-P77_E_OK", "POTH_GHOST-P77_E_OK"}
    assert names["prod_A_TO_B"] == {"name": "prod_A_TO_B"}
    assert "uat_A_TO_B" not in names and "UOTH_GHOST-P77_E_OK" not in names


def _used_differently(env: str, data: bytes) -> bytes:
    data = _other_names(env, data)
    if env == "uat":  # there, the condition of the other application is not deleted
        cleanup = b'        <OUTCOND NAME="UOTH_GHOST-UP77_E_OK" ODATE="ODAT" SIGN="-" />\n'
        data = data.replace(cleanup, b"")
    return data


def test_a_condition_named_with_the_letters_is_the_same_one_however_it_is_used(
    tmp_path: Path,
) -> None:
    repo = four_branches(tmp_path, change=_used_differently)
    with_map(repo)

    result = compare(repo.root, "main", "env/uat")

    (changed,) = result.jobs
    assert changed.node == "P77_CHAIN/P77_E" and result.links == ()
    (relation,) = changed.relations
    assert (relation.link, relation.change) == ("POTH_GHOST-P77_E_OK", "modified")


def _promoted_as_it_was(env: str, data: bytes) -> bytes:
    # production got this condition from uat as it was called there: uat's letter is in it
    return (
        data.replace(b"PP77_GHOST-PP77_E_OK", b"UP77_GHOST-PP77_E_OK") if env == "prod" else data
    )


@pytest.mark.parametrize(("base", "head"), [("main", "env/uat"), ("env/bench", "main")])
def test_a_condition_that_kept_the_letter_of_another_environment_is_the_same_one(
    tmp_path: Path, base: str, head: str
) -> None:
    repo = four_branches(tmp_path, change=_promoted_as_it_was)
    with_map(repo)

    result = compare(repo.root, base, head)

    assert (result.folders, result.jobs, result.links) == ((), (), ())
    assert result.translation is not None and result.translation.links == 1


# ---------------------------------------------------------------- how it is shown


def test_the_report_names_the_two_environments_and_what_was_explained(tmp_path: Path) -> None:
    repo = four_branches(tmp_path)
    with_map(repo)

    text = render_text(compare(repo.root, "main", "env/uat")).split("\n")

    assert text[0] == "Compare main (prod) with env/uat (uat): real differences only"
    assert text[1] == (
        "  expected between prod and uat, not shown: 21 values and 1 text of the map, "
        "2 names with the letter, 0 conditions called another name"
    )
    assert text[2] == "No real difference between main and env/uat."


def test_the_report_lists_the_differences_and_the_warnings(tmp_path: Path) -> None:
    repo = four_branches(tmp_path, change=_two_users)
    envmap = with_map(repo)
    more = add_entry(envmap, "RUN_AS", {"prod": "app77adm", "uat": USERS["uat"]},
                     environments=ENVS)  # fmt: skip
    write_map(repo.root, repo.config, more, "map: the administrator")
    result = compare(repo.root, "main", "env/uat")

    text = render_text(result)
    markdown = render_markdown(result)

    assert (
        "  warning: RUN_AS aup77proc of uat is app77proc (run_as.1) or app77adm (run_as.2) in"
        in text
    )
    assert " in prod: kept as it is (P77_CHAIN/P77_NEW); prefer one of the entries" in text
    assert "added    job P77_CHAIN/P77_NEW" in text
    assert markdown.startswith("## Chain differences: main (prod) and env/uat (uat)\n")
    assert "Expected between prod and uat, not shown: " in markdown
    assert "- warning: RUN_AS aup77proc of uat is" in markdown
    assert "0 commits" not in text + markdown
