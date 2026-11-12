"""What the map knows about the branches: who follows each entry, and what follows none.

The map says which value of one environment stands for which value of another. Looking at the
environments' branches with it tells, for every entry, the places (an attribute of a job or of
an element inside it) whose values are exactly the entry's, and the places of a mapped key
whose values no entry says. From that come four findings of ``validate`` and one change:

- a place of this environment with the value another environment has in an entry;
- a difference of a mapped key that no entry says;
- a value the map gives two answers for;
- an entry that is another entry with one environment set up like a third;
- :func:`follow_entry`: the places that follow one entry get the value of another, on the
  branch of the environment that is checked out. Renaming an entry changes no job; this does.

The survey reads the commits of the environments' branches, not the working tree, and is kept
by commit (:mod:`controlm_chain_admin.core.cache`).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from controlm_chain_admin.core import cache
from controlm_chain_admin.core.environments import env_branches, held_env
from controlm_chain_admin.core.envmap import (
    _WORDS,
    EnvMap,
    MapEntry,
    _varying,
    children,
    one_word,
    read_map,
)
from controlm_chain_admin.core.errors import ChainError, InvalidChange
from controlm_chain_admin.core.memfs import is_memory
from controlm_chain_admin.core.refactor import ChangeSet, _finish, _sandbox, _tracked
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json, write_json


@dataclass(frozen=True)
class Place:
    """Where a value is: an attribute of a node, or of an element inside it."""

    node: str  # "F/J" or "F/"
    path: str  # "" for the node itself, "/ON[..]/DOMAIL[..]" for an element inside it
    attribute: str


@dataclass(frozen=True)
class Unmapped:
    """A place of a mapped key whose values no entry of the map says."""

    place: Place
    key: str
    inline: bool
    values: Mapping[str, str]  # environment -> the value, or the one word that differs


@dataclass(frozen=True)
class Survey:
    environments: tuple[str, ...] = ()
    followers: Mapping[str, tuple[Place, ...]] = field(default_factory=dict)  # by entry
    unmapped: tuple[Unmapped, ...] = ()

    def counts(self) -> dict[str, int]:
        """Entry -> how many places follow it."""
        return {name: len(places) for name, places in self.followers.items()}

    def to_json(self) -> dict[str, Any]:
        return {"environments": list(self.environments), "followers": self.counts()}


def _says(entry: MapEntry, values: Mapping[str, str]) -> bool:
    return all(entry.values.get(env) == value for env, value in values.items())


def _survey(root: Path) -> Survey:
    repo = load_repo(root)
    config = repo.config
    branches = env_branches(root, config)
    envmap = read_map(root, config)
    if len(branches) < 2 or not envmap.entries:
        return Survey(tuple(branches))
    followers: dict[str, list[Place]] = {}
    unmapped: list[Unmapped] = []
    for seen in _varying(root, config, branches):
        fitting = [entry for entry in envmap.entries if seen.fact.fits(entry.selector)]
        if not fitting:
            continue  # not a key of the map: `envmap suggest` lists those
        place = Place(seen.node, seen.fact.path, seen.fact.attribute)
        words = one_word(seen.values)
        said = [
            entry
            for entry in fitting
            if _says(entry, (words or {"": ""}) if entry.inline else seen.values)
        ]
        for entry in said:
            followers.setdefault(entry.name, []).append(place)
        if not said:
            first = fitting[0]
            values = words if first.inline and words is not None else seen.values
            unmapped.append(Unmapped(place, first.key, first.inline, dict(values)))
    return Survey(
        tuple(branches), {name: tuple(places) for name, places in followers.items()},
        tuple(unmapped),
    )  # fmt: skip


def survey(root: Path) -> Survey:
    """Who follows each entry of the map, and what follows none, on the environments' branches
    as committed. Empty where fewer than two environments have a branch, or without a map."""
    try:
        branches = list(env_branches(root, load_repo(root).config).values())
    except ChainError:
        return Survey()
    parts = cache.state(root, branches) if branches else None
    return cache.remember(root, "survey", parts, lambda: _survey(root))


# ---------------------------------------------------------------- what the map alone says


def _groups(envmap: EnvMap) -> list[list[MapEntry]]:
    """The entries of each key, a word inside a text apart from the whole value."""
    groups: dict[tuple[str, bool], list[MapEntry]] = {}
    for entry in envmap.entries:
        groups.setdefault((entry.key, entry.inline), []).append(entry)
    return list(groups.values())


@dataclass(frozen=True)
class Suspect:
    """``entry`` is ``other`` but for ``env``, which has there the value ``like`` has in
    ``other``: one environment set up like another, more likely than a rule of its own."""

    entry: MapEntry
    other: MapEntry
    env: str
    like: str


def suspects(envmap: EnvMap) -> list[Suspect]:
    found = []
    for group in _groups(envmap):
        for entry in group:
            for other in group:
                if other is entry:
                    continue
                envs = list(dict.fromkeys([*entry.values, *other.values]))
                differ = [e for e in envs if entry.values.get(e) != other.values.get(e)]
                if len(differ) != 1 or entry.values.get(differ[0]) is None:
                    continue
                value = entry.values[differ[0]]
                like = next(
                    (e for e, v in other.values.items() if e != differ[0] and v == value), None
                )
                if like is not None:
                    found.append(Suspect(entry, other, differ[0], like))
    return found


def ambiguous(envmap: EnvMap, env: str) -> list[tuple[str, str, str, dict[str, str]]]:
    """(key, the value of ``env``, another environment, entry -> its value there) wherever one
    value of ``env`` stands for several values of that other environment."""
    found = []
    for group in _groups(envmap):
        by_value: dict[str, list[MapEntry]] = {}
        for entry in group:
            if env in entry.values:
                by_value.setdefault(entry.values[env], []).append(entry)
        for value, entries in by_value.items():
            others = dict.fromkeys(e for entry in entries for e in entry.values if e != env)
            for other in others:
                answers = {e.name: e.values[other] for e in entries if other in e.values}
                if len(set(answers.values())) > 1:
                    found.append((group[0].key, value, other, answers))
    return found


def foreign(envmap: EnvMap, item: Unmapped, env: str) -> tuple[MapEntry, str] | None:
    """The entry ``item`` would follow if ``env`` had its own value there, and the environment
    whose value ``env`` has instead."""
    mine = item.values.get(env)
    for entry in envmap.entries:
        if (entry.key, entry.inline) != (item.key, item.inline):
            continue
        if mine is None or entry.values.get(env) in (None, mine):
            continue
        if not _says(entry, {e: v for e, v in item.values.items() if e != env}):
            continue
        like = next((e for e, v in entry.values.items() if e != env and v == mine), None)
        if like is not None:
            return entry, like
    return None


def checked_out(repo: ChainRepo) -> tuple[str, EnvMap] | None:
    """The environment the branch checked out holds, and the map; None where there is no git,
    no such environment or no map (a snapshot in memory, a repository of one tree)."""
    if is_memory(repo.root):
        return None
    try:
        env = held_env(repo.root, repo.config, "HEAD")
        envmap = read_map(repo.root, repo.config)
    except ChainError:
        return None
    return (env, envmap) if env is not None and envmap.entries else None


def map_findings(repo: ChainRepo) -> list[Any]:
    """The findings of ``validate`` that come from the map, for the environment checked out."""
    from controlm_chain_admin.core.validate import Finding  # validate calls this module

    here = checked_out(repo)
    if here is None:
        return []
    env, envmap = here
    try:
        seen = survey(repo.root)
    except ChainError:
        return []
    findings: list[Finding] = []
    plain: dict[tuple[str, tuple[tuple[str, str], ...]], list[Unmapped]] = {}
    for item in seen.unmapped:
        if env not in item.values:
            continue
        found = foreign(envmap, item, env)
        if found is None:
            plain.setdefault((item.key, tuple(item.values.items())), []).append(item)
            continue
        entry, like = found
        findings.append(
            Finding(
                "warning", "foreign-value", item.place.node, entry.name,
                f"{item.key} is {item.values[env]}, what {like} has in the map ({entry.name}): "
                f"{env} has {entry.values[env]} there",
            )
        )  # fmt: skip
    for (key, values), items in plain.items():
        others = ", ".join(f"{e} has {v}" for e, v in values if e != env)
        findings.append(
            Finding(
                "info", "unmapped-difference", items[0].place.node, key,
                f"{key}: {env} has {dict(values)[env]}; {others}: no entry of the map says "
                f"these stand for each other ({len(items)} place(s)), so a comparison shows it "
                "as a difference",
            )
        )  # fmt: skip
    for key, value, other, answers in ambiguous(envmap, env):
        said = ", ".join(f"{name}: {answer}" for name, answer in answers.items())
        number = "two" if len(set(answers.values())) == 2 else str(len(set(answers.values())))
        findings.append(
            Finding(
                "info", "ambiguous-map", "", key,
                f"{value} of {env} stands for {number} values of {other} in the map ({said}): "
                f"what is taken or packaged from {env} for {other} keeps it as it is unless one "
                "entry is preferred",
            )
        )  # fmt: skip
    counts = seen.counts()
    for suspect in suspects(envmap):
        wrong, right = suspect.entry, suspect.other
        findings.append(
            Finding(
                "info", "suspect-map-entry", "", wrong.name,
                f"{wrong.name} is {right.name} with {suspect.env} having "
                f"{wrong.values[suspect.env]}, the value of {suspect.like}: if {suspect.env} "
                f"was set up wrongly, its {counts.get(wrong.name, 0)} place(s) can follow "
                f"{right.name}",
            )
        )  # fmt: skip
    return findings


# ---------------------------------------------------------------- following another entry


def _elements(data: dict[str, Any], path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """The node and every element inside it with its path, as :func:`envmap.facts` names them."""
    yield path, data
    for step, _tag, child in children(data):
        yield from _elements(child, f"{path}/{step}")


def _replace_word(text: str, old: str, new: str) -> str:
    parts = _WORDS.split(text)
    return "".join(new if i % 2 == 0 and part == old else part for i, part in enumerate(parts))


def _technical(meta: dict[str, Any], job: str) -> dict[str, Any]:
    """The technical attributes of the folder (``job`` empty) or of one of its jobs."""
    if not job:
        return dict(meta.get("attrs", {}))
    return dict(meta.get("jobs", {}).get(job, {}))


def _follow_node(
    box: ChainRepo, node: str, places: Sequence[Place], old: str, new: str, inline: bool
) -> int:
    """Give the places of one node the new value; how many really had the old one."""
    folder, _, job = node.partition("/")
    path = box.job_file(folder, job) if job else box.folder_file(folder)
    if not path.is_file():
        return 0
    data = dict(read_json(path))
    elements = dict(_elements(data))
    meta_file = box.folder_meta_file(folder)
    meta = dict(read_json(meta_file)) if meta_file.is_file() else {}
    technical = _technical(meta, job)
    changed = 0
    for place in places:
        element = elements.get(place.path)
        if element is None or place.attribute not in element:
            element = technical if not place.path and place.attribute in technical else None
        if element is None:
            continue
        value = str(element[place.attribute])
        after = _replace_word(value, old, new) if inline else (new if value == old else value)
        if after != value:
            element[place.attribute] = after
            changed += 1
    if changed:
        write_json(path, data)
        if technical != _technical(meta, job):
            if job:
                meta["jobs"] = {**meta.get("jobs", {}), job: technical}
            else:
                meta["attrs"] = technical
            write_json(meta_file, meta)
    return changed


def follow_entry(repo: ChainRepo, entry: str, other: str) -> ChangeSet:
    """The places that follow the map entry ``entry`` get the value ``other`` has, for the
    environment the branch checked out holds: one environment set up like another is put
    right. The map is not changed: once the branch of the environment has the change, nothing
    follows ``entry`` there any more and it can be removed."""
    repo = load_repo(repo.root)
    envmap = read_map(repo.root, repo.config)
    wrong, right = envmap.named(entry), envmap.named(other)
    if (wrong.key, wrong.inline) != (right.key, right.inline):
        raise InvalidChange(f"{entry} and {other} are not entries of the same key")
    env = held_env(repo.root, repo.config, "HEAD")
    if env is None:
        raise InvalidChange(
            "the branch checked out holds no environment: check out the branch of the "
            "environment to correct, or a branch started from it"
        )
    old, new = wrong.values.get(env), right.values.get(env)
    if old is None or new is None or old == new:
        raise InvalidChange(
            f"{entry} and {other} have the same value for {env}: nothing to change on this "
            "branch (check out the branch of the environment where they differ)"
        )
    by_node: dict[str, list[Place]] = {}
    for place in survey(repo.root).followers.get(entry, ()):
        by_node.setdefault(place.node, []).append(place)
    tracked = _tracked(repo.root)
    with _sandbox(tracked) as box:
        changed = sum(
            _follow_node(box, node, places, old, new, wrong.inline)
            for node, places in by_node.items()
        )
        summary = (
            f"{changed} place(s) of {env} follow {other} instead of {entry}: {wrong.key} "
            f"{old} -> {new}"
        )
        warnings = []
        expected = sum(len(places) for places in by_node.values())
        if changed < expected:
            warnings.append(
                f"{expected - changed} place(s) that follow {entry} on the branch of {env} do "
                "not have that value here any more: left as they are"
            )
        return _finish(tracked, box, summary, warnings)
