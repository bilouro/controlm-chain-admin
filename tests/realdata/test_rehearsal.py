"""The rehearsal before a release: what the author does at work, played on the real chains.

On a temporary clone of the private data repository (one branch per environment, the map on
its branch), never on the repository itself: a user renamed everywhere by a refresh goes back
into the map; a file of some folders goes onto an environment's branch without removing the
others; a follow in every environment moves the counts. Only counts are printed.

Run before every release: ``CTMCHAIN_DATA_REPO=... pytest -m realdata tests/realdata``.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.environments import env_branches
from controlm_chain_admin.core.envmap import read_map
from controlm_chain_admin.core.mapcheck import (
    adopt_value,
    apply_follow_everywhere,
    follow_everywhere,
    new_values,
    survey,
)
from controlm_chain_admin.core.refresh import refresh
from controlm_chain_admin.core.repo import load_repo
from tests.support.fourenvs import split_folders
from tests.support.gitrepo import git, plain_git_identity

pytestmark = pytest.mark.realdata


@pytest.fixture
def clone(data_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    root = tmp_path / "data"
    git(tmp_path, "clone", "-q", "--no-hardlinks", str(data_repo), str(root))
    for branch in git(data_repo, "branch", "--format=%(refname:short)").split():
        if branch != git(root, "branch", "--show-current"):
            git(root, "branch", "-q", "--track", branch, f"origin/{branch}")
    if len(env_branches(root, load_repo(root).config)) < 2:
        pytest.skip("the data repository has not one branch per environment")
    return root


def _envs(root: Path) -> tuple[str, str, str, str]:
    """(production, its branch, another environment, its branch)."""
    config = load_repo(root).config
    branches = env_branches(root, config)
    trunk = config.git_rules.trunk
    prod = next(env for env, branch in branches.items() if branch == trunk)
    other = next(env for env, branch in branches.items() if branch != trunk)
    return prod, trunk, other, branches[other]


def _export(root: Path, env: str, path: Path) -> bytes:
    assert main(["export", "--env", env, "-o", str(path), "--repo", str(root)]) == 0
    return path.read_bytes()


def _jobs_differing(root: Path, base: str, head: str) -> int:
    return int(compare(root, base, head).summary()["jobs"]["modified"])


def test_a_user_renamed_everywhere_goes_back_into_the_map(clone: Path, tmp_path: Path) -> None:
    _, trunk, env, branch = _envs(clone)
    git(clone, "switch", "-q", branch)
    data = _export(clone, env, tmp_path / "export.xml")
    used, times = Counter(re.findall(rb'RUN_AS="([^"]+)"', data)).most_common(1)[0]
    renamed = used.decode() + "X"
    changed = data.replace(b'RUN_AS="' + used + b'"', f'RUN_AS="{renamed}"'.encode())
    before = _jobs_differing(clone, trunk, branch)

    done = refresh(load_repo(clone), changed, source="renamed.xml", apply=True)
    broken = _jobs_differing(clone, trunk, branch)
    _, found = new_values(load_repo(clone))
    new = next(v for v in found if (v.key, v.value) == ("RUN_AS", renamed) and v.suggested)
    adopted = adopt_value(load_repo(clone), "RUN_AS", renamed, entry=new.suggested)
    # where another environment had the same user, a combination of its own: a new entry
    combinations = [v for v in new_values(load_repo(clone))[1]
                    if (v.key, v.value) == ("RUN_AS", renamed)]  # fmt: skip
    for combination in combinations:
        adopt_value(load_repo(clone), "RUN_AS", renamed, entry=combination.suggested)
    after = _jobs_differing(clone, trunk, branch)

    print(f"renamed one user in {times} places: {before} jobs differ before, {broken} after "
          f"the refresh, {after} once it went into {', '.join(adopted['entries'])} and "
          f"{len(combinations)} new entr(ies) ({adopted['left']} left)")  # fmt: skip
    assert any(v["value"] == renamed for v in done.new_values)  # said by the refresh itself
    assert broken > before
    assert after == before and adopted["left"] == 0


def test_some_folders_go_onto_an_environments_branch_without_removing(
    clone: Path, tmp_path: Path
) -> None:
    _, _, env, branch = _envs(clone)
    data = _export(clone, env, tmp_path / "export.xml")
    raw = split_folders(data)
    one = raw.header + data[raw.folders[0].start : raw.folders[0].end] + raw.footer

    told = refresh(load_repo(clone), one, source="one.xml", partial=None)
    whole = refresh(load_repo(clone), one, source="one.xml", partial=False)

    print(f"a file of 1 of {told.branch_folders} folders: read as some folders "
          f"({told.summary['folders']['removed']} removed); read whole it would remove "
          f"{whole.summary['folders']['removed']}")  # fmt: skip
    assert told.branch == branch and told.partial and told.looks_partial
    assert told.summary["folders"]["removed"] == 0
    assert whole.removes_most


def test_a_follow_in_every_environment_moves_the_counts(clone: Path) -> None:
    repo = load_repo(clone)
    envmap = read_map(clone, repo.config)
    counts = survey(clone).counts()
    trunk = repo.config.git_rules.trunk
    pair = None
    for first in envmap.entries:
        if not counts.get(first.name):
            continue
        for second in envmap.entries:
            if second is first or (second.key, second.inline) != (first.key, first.inline):
                continue
            plan = follow_everywhere(repo, first.name, second.name)
            if plan and all(f.branch != trunk for f in plan):
                pair = (first.name, second.name)
                break
        if pair:
            break
    if pair is None:
        pytest.skip("no two entries of one key that differ outside production")

    moved = {(p.node, p.path, p.attribute) for p in survey(clone).followers[pair[0]]}
    done = apply_follow_everywhere(load_repo(clone), *pair)
    seen = survey(clone)
    after = seen.counts()
    unexplained = moved & {(u.place.node, u.place.path, u.place.attribute) for u in seen.unmapped}

    print(f"a follow committed on {sum(1 for d in done if d['commit'])} branch(es): "
          f"{counts[pair[0]]} place(s) moved; the source now {after.get(pair[0], 0)}, the "
          f"target {counts.get(pair[1], 0)} -> {after.get(pair[1], 0)} (the rest the same in "
          f"every environment now); {len(unexplained)} follow no entry")  # fmt: skip
    assert after.get(pair[0], 0) == 0
    assert after.get(pair[1], 0) > counts.get(pair[1], 0)
    assert not unexplained  # each one follows the target, or varies no more
