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

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from controlm_chain_admin.core import cache
from controlm_chain_admin.core.constants import parse_spec
from controlm_chain_admin.core.environments import (
    branch_exists,
    branch_of_env,
    current_branch,
    env_branches,
    held_env,
)
from controlm_chain_admin.core.envmap import (
    _WORDS,
    EnvMap,
    MapEntry,
    _free_name,
    _varying,
    children,
    one_word,
    read_map,
    write_map,
)
from controlm_chain_admin.core.errors import ChainError, InvalidChange, UncommittedChanges
from controlm_chain_admin.core.history import _git, chain_changes, commit_files, snapshot
from controlm_chain_admin.core.memfs import is_memory
from controlm_chain_admin.core.refactor import ChangeSet, _finish, _sandbox, _tracked
from controlm_chain_admin.core.refactor import apply as apply_change
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
class HalfWay:
    """Places that have the values of one entry in some environments and of another in the
    rest: a follow done on some environments only. They follow neither entry until it is
    done on all of them."""

    entries: tuple[str, str]
    places: int
    like: Mapping[str, str]  # environment -> the entry whose value it has there

    def to_json(self) -> dict[str, Any]:
        return {"entries": list(self.entries), "places": self.places, "like": dict(self.like)}


@dataclass(frozen=True)
class Survey:
    environments: tuple[str, ...] = ()
    followers: Mapping[str, tuple[Place, ...]] = field(default_factory=dict)  # by entry
    unmapped: tuple[Unmapped, ...] = ()
    halfway: tuple[HalfWay, ...] = ()

    def counts(self) -> dict[str, int]:
        """Entry -> how many places follow it."""
        return {name: len(places) for name, places in self.followers.items()}

    def to_json(self) -> dict[str, Any]:
        return {
            "environments": list(self.environments),
            "followers": self.counts(),
            "halfway": [half.to_json() for half in self.halfway],
        }


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
    halfway: dict[tuple[tuple[str, str], tuple[tuple[str, str], ...]], int] = {}
    followed = _followed(root, branches)
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
            between = _between(fitting, dict(values), first.inline, followed)
            if between is not None:
                halfway[between] = halfway.get(between, 0) + 1
    return Survey(
        tuple(branches), {name: tuple(places) for name, places in followers.items()},
        tuple(unmapped),
        tuple(HalfWay(pair, count, dict(like)) for (pair, like), count in halfway.items()),
    )  # fmt: skip


_FOLLOW_SUBJECT = re.compile(r"^follow\([^)]+\): (\S+) -> (\S+)$")


def _followed(root: Path, branches: Mapping[str, str]) -> frozenset[frozenset[str]]:
    """The pairs of entries a follow was committed between, on any environment's branch."""
    pairs = set()
    for branch in branches.values():
        try:
            subjects = str(_git(root, "log", "-E", "--grep=^follow\\(", "--format=%s", branch))
        except ChainError:
            continue
        for subject in subjects.splitlines():
            found = _FOLLOW_SUBJECT.match(subject)
            if found:
                pairs.add(frozenset(found.groups()))
    return frozenset(pairs)


def _between(
    fitting: Sequence[MapEntry],
    values: Mapping[str, str],
    inline: bool,
    followed: frozenset[frozenset[str]] = frozenset(),
) -> tuple[tuple[str, str], tuple[tuple[str, str], ...]] | None:
    """The two entries a place is half-way between, and which one each environment is like:
    two entries a follow was committed between, whose values it has. None otherwise."""
    entries = sorted((e for e in fitting if e.inline == inline), key=lambda e: e.name)
    for i, first in enumerate(entries):
        for second in entries[i + 1 :]:
            if frozenset((first.name, second.name)) not in followed:
                continue
            like = {}
            for env, value in values.items():
                if first.values.get(env) == value:
                    like[env] = first.name
                elif second.values.get(env) == value:
                    like[env] = second.name
                else:
                    break
            else:
                only_second = any(name == second.name for name in like.values())
                only_first = any(
                    name == first.name and second.values.get(env) != values[env]
                    for env, name in like.items()
                )
                if only_first and only_second:
                    return (first.name, second.name), tuple(like.items())
    return None


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
        others = [
            e for e in repo.config.environments
            if e != env and wrong.values.get(e) != right.values.get(e)
        ]  # fmt: skip
        if others:
            branches = ", ".join(branch_of_env(repo.config, e) for e in others)
            warnings.append(
                f"{entry} and {other} also differ in {', '.join(others)}: these places follow "
                f"neither until the same follow is done on {branches} too"
            )
        warnings.append(
            "The Map page counts who follows each entry on the branches as committed: the "
            f'counts move once committed; commit it as "follow({env}): {entry} -> {other}" '
            "for the places still half-way to be told apart"
        )
        expected = sum(len(places) for places in by_node.values())
        if changed < expected:
            warnings.append(
                f"{expected - changed} place(s) that follow {entry} on the branch of {env} do "
                "not have that value here any more: left as they are"
            )
        return _finish(tracked, box, summary, warnings)


# ---------------------------------------------------------------- new values for the map


@dataclass(frozen=True)
class NewValue:
    """A value of a mapped key that the environment of the branch checked out has and no
    entry of the map has for it: a user renamed, a machine replaced, after a refresh."""

    key: str
    inline: bool
    env: str
    value: str  # the value, or for a word inside a text the word
    places: int
    nodes: tuple[str, ...]  # the first of them
    suggested: str | None  # the entry the other environments' values there are of
    candidates: tuple[str, ...]  # the entries of the same key
    #: the value is in an entry already, but not with what the other environments have here
    known: bool = False
    #: what every one of these places has in each other environment, where they agree
    others: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key, "inline": self.inline, "env": self.env, "value": self.value,
            "places": self.places, "nodes": list(self.nodes), "suggested": self.suggested,
            "candidates": list(self.candidates), "known": self.known,
            "others": dict(self.others),
        }  # fmt: skip


NODES_SHOWN = 5


def _env_of_head(repo: ChainRepo) -> str:
    env = held_env(repo.root, repo.config, "HEAD")
    if env is None:
        raise InvalidChange(
            "the branch checked out holds no environment: check out the branch of an "
            "environment, or a branch started from it"
        )
    return env


def _agreed(items: Sequence[Unmapped], env: str) -> dict[str, str]:
    """Environment -> the value every one of ``items`` has there, where they agree."""
    found: dict[str, str] = {}
    envs = dict.fromkeys(e for item in items for e in item.values if e != env)
    for other in envs:
        values = {item.values.get(other) for item in items}
        if len(values) == 1 and None not in values:
            found[other] = str(values.pop())
    return found


def new_values(repo: ChainRepo) -> tuple[str | None, list[NewValue]]:
    """The environment of the branch checked out, and the values of mapped keys it has (on
    its branch, as committed) where no entry of the map says what these places have: a value
    no entry has for it, or one some entry has but with other values elsewhere (where two
    environments had the same value before one was renamed). Places half-way between two
    entries are left out: a follow says those. Most places first."""
    env = held_env(repo.root, repo.config, "HEAD")
    if env is None:
        return None, []
    envmap = read_map(repo.root, repo.config)
    followed = _followed(repo.root, env_branches(repo.root, repo.config))
    groups: dict[tuple[str, bool, str], list[Unmapped]] = {}
    for item in survey(repo.root).unmapped:
        mine = item.values.get(env)
        same = [e for e in envmap.entries if (e.key, e.inline) == (item.key, item.inline)]
        if mine is None or _between(same, item.values, item.inline, followed) is not None:
            continue
        groups.setdefault((item.key, item.inline, mine), []).append(item)
    found = []
    for (key, inline, value), items in groups.items():
        same = [e for e in envmap.entries if (e.key, e.inline) == (key, inline)]
        score = {
            e.name: sum(
                1 for item in items
                if _says(e, {x: v for x, v in item.values.items() if x != env})
            )
            for e in same
        }  # fmt: skip
        best = max(score, key=lambda name: score[name]) if score else None
        nodes = tuple(dict.fromkeys(item.place.node for item in items))[:NODES_SHOWN]
        known = any(e.values.get(env) == value for e in same)
        found.append(NewValue(key, inline, env, value, len(items), nodes,
                              best if best and score[best] else None,
                              tuple(e.name for e in same), known,
                              _agreed(items, env)))  # fmt: skip
    found.sort(key=lambda new: (-new.places, new.key, new.value))
    return env, found


def _with_value(repo: ChainRepo, envmap: EnvMap, name: str, env: str, value: str | None) -> EnvMap:
    if env not in repo.config.environments:
        known = ", ".join(repo.config.environments)
        raise ChainError(f"unknown environment {env!r} (known: {known})")
    entry = envmap.named(name)
    values = (
        {**entry.values, env: value}
        if value is not None
        else {e: v for e, v in entry.values.items() if e != env}
    )
    if not values:
        raise ChainError(f"{name} would have no value left: remove the entry instead")
    ordered = {e: values[e] for e in repo.config.environments if e in values}
    return EnvMap(tuple(
        replace(e, values=ordered) if e is entry else e for e in envmap.entries
    ))  # fmt: skip


def _used(repo: ChainRepo, envmap: EnvMap, key: str, inline: bool, env: str, value: str) -> int:
    """How many places of ``env`` have ``value`` for ``key``: those that follow an entry with
    it there, and those that follow none."""
    seen = survey(repo.root)
    following = sum(
        len(seen.followers.get(e.name, ())) for e in envmap.entries
        if (e.key, e.inline) == (key, inline) and e.values.get(env) == value
    )  # fmt: skip
    return following + _left(repo, key, inline, env, value)


def _left(repo: ChainRepo, key: str, inline: bool, env: str, value: str) -> int:
    """How many places of ``env`` have ``value`` for ``key`` and follow no entry."""
    return sum(
        1 for item in survey(repo.root).unmapped
        if (item.key, item.inline) == (key, inline) and item.values.get(env) == value
    )  # fmt: skip


def adopt_value(
    repo: ChainRepo, key: str, value: str, *, entry: str | None, inline: bool = False
) -> dict[str, Any]:
    """Put a new value of the environment of the branch checked out into the map: into the
    entry ``entry`` (instead of the value it had there), or into a new entry whose other
    environments are left to fill. Committed on the branch of the map."""
    env = _env_of_head(repo)
    spec = parse_spec(key, inline).spec
    envmap = read_map(repo.root, repo.config)
    if entry is not None:
        target = envmap.named(entry)
        if (target.key, target.inline) != (spec, inline):
            raise ChainError(f"{entry} is not an entry of {key} (it is of {target.key})")
        old = target.values.get(env)
        names = [entry]
        if old is not None and _used(repo, envmap, spec, inline, env, old) == 0:
            # renamed in all of the environment: every entry that had it takes the new one
            names = [
                e.name for e in envmap.entries
                if (e.key, e.inline) == (spec, inline) and e.values.get(env) == old
            ]  # fmt: skip
        changed = envmap
        for name in names:
            changed = _with_value(repo, changed, name, env, value)
        said = ", ".join(names)
        write_map(repo.root, repo.config, changed, f"map: {said} {env} {old} -> {value}")
        name = entry
    else:
        old = None
        name = _free_name(envmap, parse_spec(key, inline))
        group = next(
            (
                v
                for v in new_values(repo)[1]
                if (v.key, v.inline, v.value) == (spec, inline, value)
            ),
            None,
        )
        given = {**(group.others if group else {}), env: value}
        ordered = {e: given[e] for e in repo.config.environments if e in given}
        added = MapEntry(name, spec, ordered, inline)
        changed = EnvMap((*envmap.entries, added))
        write_map(repo.root, repo.config, changed, f"map: add {name} ({env} {value})")
        names = [name]
    values = changed.named(name).values
    return {
        "entry": name, "entries": names, "env": env, "old": old, "new": value,
        "left": 0 if old is None else _left(repo, spec, inline, env, old),
        "to_fill": [e for e in repo.config.environments if e not in values],
    }  # fmt: skip


def set_entry_value(repo: ChainRepo, name: str, env: str, value: str | None) -> EnvMap:
    """The value of one environment in the entry ``name`` set, or left to fill (None);
    committed on the branch of the map."""
    envmap = _with_value(repo, read_map(repo.root, repo.config), name, env, value)
    said = value if value is not None else "to fill"
    write_map(repo.root, repo.config, envmap, f"map: {name} {env} {said}")
    return envmap


# ---------------------------------------------------------------- following everywhere


@dataclass(frozen=True)
class EnvFollow:
    """What a follow changes on the branch of one environment, as committed."""

    env: str
    branch: str
    key: str
    old: str
    new: str
    places: int
    protected: bool  # the trunk: production is never edited here
    change: ChangeSet

    def to_json(self) -> dict[str, Any]:
        return {
            "env": self.env, "branch": self.branch, "key": self.key, "old": self.old,
            "new": self.new, "places": self.places, "protected": self.protected,
            "files": [edit.path for edit in self.change.edits],
        }  # fmt: skip


def _pair(envmap: EnvMap, entry: str, other: str) -> tuple[MapEntry, MapEntry]:
    wrong, right = envmap.named(entry), envmap.named(other)
    if (wrong.key, wrong.inline) != (right.key, right.inline):
        raise InvalidChange(f"{entry} and {other} are not entries of the same key")
    return wrong, right


def follow_everywhere(repo: ChainRepo, entry: str, other: str) -> list[EnvFollow]:
    """What following ``other`` instead of ``entry`` changes on the branch of every
    environment where the two differ: the places that follow ``entry`` get ``other``'s value
    of that environment. Writes nothing."""
    repo = load_repo(repo.root)
    wrong, right = _pair(read_map(repo.root, repo.config), entry, other)
    by_node: dict[str, list[Place]] = {}
    for place in survey(repo.root).followers.get(entry, ()):
        by_node.setdefault(place.node, []).append(place)
    plan = []
    for env in repo.config.environments:
        old, new = wrong.values.get(env), right.values.get(env)
        branch = branch_of_env(repo.config, env)
        if old is None or new is None or old == new or not branch_exists(repo.root, branch):
            continue
        with snapshot(repo.root, branch) as tree:
            tracked = _tracked(tree)
            with _sandbox(tracked) as box:
                changed = sum(
                    _follow_node(box, node, places, old, new, wrong.inline)
                    for node, places in by_node.items()
                )
                change = _finish(tracked, box, f"follow({env}): {entry} -> {other}", [])
        protected = repo.config.git_rules.refusal(branch) is not None
        plan.append(EnvFollow(env, branch, wrong.key, old, new, changed, protected, change))
    if not plan:
        raise InvalidChange(
            f"{entry} and {other} have the same value in every environment that has a branch: "
            "nothing to change"
        )
    return plan


def _commit_here(root: Path, paths: Sequence[str], message: str) -> str:
    _git(root, "add", "--", *paths)
    _git(root, "commit", "-q", "-m", message, "--", *paths)
    return str(_git(root, "rev-parse", "HEAD")).strip()


def apply_follow_everywhere(repo: ChainRepo, entry: str, other: str) -> list[dict[str, Any]]:
    """Follow ``other`` instead of ``entry`` on the branch of every environment where they
    differ: one commit on each (the branch checked out too, which must have no uncommitted
    chain file), none on the trunk, which production's import file changes. What was done,
    by environment."""
    repo = load_repo(repo.root)
    plan = follow_everywhere(repo, entry, other)
    here = current_branch(repo.root)
    if any(f.branch == here and f.change.edits and not f.protected for f in plan):
        count = chain_changes(repo.root)
        if count:
            raise UncommittedChanges(
                f"{count} uncommitted chain file(s) on {here}: commit or discard them before "
                "the follow commits there",
                count,
            )
    done = []
    for follow in plan:
        if follow.protected or not follow.change.edits:
            done.append({**follow.to_json(), "commit": None})
            continue
        message = f"follow({follow.env}): {entry} -> {other}"
        if follow.branch == here:
            apply_change(load_repo(repo.root), follow.change)
            sha = _commit_here(repo.root, [e.path for e in follow.change.edits], message)
        else:
            files = {edit.path: edit.after for edit in follow.change.edits}
            sha = commit_files(repo.root, follow.branch, files, message)
        done.append({**follow.to_json(), "commit": sha})
    return done
