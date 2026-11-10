"""The map of what varies from one environment to another, and nothing else.

Each environment has its own branch, with what its export says. Their machines, users and
datacenters differ, as expected: the map says which value of one environment stands for which
value of another, so that comparing two environments shows the real differences only, and what
is taken from one is adapted to the other.

The map is part of no environment: it lives in ``map.json`` on a branch of its own (``map``,
an orphan), read with ``git show`` and written with git plumbing. No checkout is needed: the
working tree and the current branch are never touched.

An entry is a key (which attribute: ``NODEID``, ``TAG/@ATTR``, ``TAG[K=V]/@ATTR``) and one
value per environment. An *inline* entry is a word inside a text (``UAT`` in a mail subject).
The letters of the names are not in the map: they come from ``envs/<env>/env.json``.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.constants import Selector, parse_spec
from controlm_chain_admin.core.environments import branch_exists, current_branch, env_branches
from controlm_chain_admin.core.errors import ChainError, GitError, ModelError
from controlm_chain_admin.core.history import _git, snapshot
from controlm_chain_admin.core.letter import LetterRule
from controlm_chain_admin.core.repo import ChainConfig, ChainRepo, load_repo

MAP_FILE = "map.json"
#: What is expected to differ from one environment to another, whatever the chain.
DEFAULT_KEYS: tuple[str, ...] = ("NODEID", "RUN_AS", "DATACENTER")
#: Keys of the JSON files that are structure, not attributes of the element.
STRUCTURE = frozenset({"tag", "link", "jobs"})
_WORDS = re.compile(r"([^A-Za-z0-9]+)")
_MARK = "\x00"


# ---------------------------------------------------------------- the map itself


@dataclass(frozen=True)
class MapEntry:
    """One thing that varies: ``key`` says where, ``values`` what each environment has."""

    name: str
    key: str
    values: Mapping[str, str]
    inline: bool = False

    @property
    def selector(self) -> Selector:
        return parse_spec(self.key, self.inline)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "key": self.key, "values": dict(self.values)}
        if self.inline:
            data["inline"] = True
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> MapEntry:
        try:
            values = {str(env): str(value) for env, value in data["values"].items()}
            return cls(str(data["name"]), str(data["key"]), values, bool(data.get("inline")))
        except (KeyError, AttributeError, TypeError) as exc:
            raise ModelError(f"{MAP_FILE}: an entry cannot be read ({exc})") from exc


@dataclass(frozen=True)
class EnvMap:
    entries: tuple[MapEntry, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {"version": 1, "entries": [entry.to_json() for entry in self.entries]}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> EnvMap:
        entries = data.get("entries", []) if isinstance(data, Mapping) else None
        if not isinstance(entries, list):
            raise ModelError(f"{MAP_FILE}: no list of entries")
        return cls(tuple(MapEntry.from_json(entry) for entry in entries))

    def named(self, name: str) -> MapEntry:
        for entry in self.entries:
            if entry.name == name:
                return entry
        known = ", ".join(entry.name for entry in self.entries) or "none"
        raise ChainError(f"no entry called {name!r} in the map (known: {known})")


def _slug(selector: Selector) -> str:
    source = selector.where.get("NAME") or selector.attribute
    return re.sub(r"[^a-z0-9]+", "_", source.lower()).strip("_") or "value"


def _free_name(envmap: EnvMap, selector: Selector) -> str:
    taken = {entry.name for entry in envmap.entries}
    slug, number = _slug(selector), 1
    while f"{slug}.{number}" in taken:
        number += 1
    return f"{slug}.{number}"


def add_entry(
    envmap: EnvMap,
    key: str,
    values: Mapping[str, str],
    *,
    environments: Sequence[str],
    name: str | None = None,
    inline: bool = False,
) -> EnvMap:
    """The map with one more entry; ``environments`` are the ones the repository declares."""
    selector = parse_spec(key, inline)
    unknown = [env for env in values if env not in environments]
    if unknown:
        known = ", ".join(environments)
        raise ChainError(f"unknown environment {unknown[0]!r} in the map entry (known: {known})")
    if len(values) < 2:
        raise ChainError("a map entry needs the values of two environments at least")
    if len(set(values.values())) == 1:
        raise ChainError(f"every environment has the same value for {key}: nothing varies")
    ordered = {env: values[env] for env in environments if env in values}
    for entry in envmap.entries:
        if (entry.key, entry.inline, dict(entry.values)) == (selector.spec, inline, ordered):
            raise ChainError(f"the map has these values for {key} already: {entry.name}")
    chosen = name or _free_name(envmap, selector)
    if any(entry.name == chosen for entry in envmap.entries):
        raise ChainError(f"the map has an entry called {chosen!r} already")
    return EnvMap((*envmap.entries, MapEntry(chosen, selector.spec, ordered, inline)))


def remove_entry(envmap: EnvMap, name: str) -> EnvMap:
    gone = envmap.named(name)
    return EnvMap(tuple(entry for entry in envmap.entries if entry is not gone))


def rename_entry(envmap: EnvMap, old: str, new: str) -> EnvMap:
    renamed = envmap.named(old)
    if any(entry.name == new for entry in envmap.entries):
        raise ChainError(f"the map has an entry called {new!r} already")
    return EnvMap(
        tuple(replace(entry, name=new) if entry is renamed else entry for entry in envmap.entries)
    )


# ---------------------------------------------------------------- its branch


def _plumb(root: Path, *args: str, data: bytes) -> str:
    """A git command that reads ``data`` on its standard input; its output, stripped."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], input=data, capture_output=True, check=False
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    if result.returncode != 0:
        raise GitError(f"git {args[0]}: {result.stderr.decode().strip() or 'failed'}")
    return result.stdout.decode().strip()


def _content(root: Path, branch: str) -> str | None:
    if not branch_exists(root, branch):
        return None
    try:
        return str(_git(root, "show", f"refs/heads/{branch}:{MAP_FILE}"))
    except GitError as exc:
        raise GitError(f"the branch {branch} has no {MAP_FILE}: it is not the map") from exc


def read_map(root: Path, config: ChainConfig) -> EnvMap:
    """The map on its branch; empty when the branch is not there yet."""
    content = _content(root, config.git_rules.map_branch)
    if content is None:
        return EnvMap()
    try:
        return EnvMap.from_json(json.loads(content))
    except json.JSONDecodeError as exc:
        raise ModelError(f"{MAP_FILE} on {config.git_rules.map_branch}: {exc}") from exc


def write_map(root: Path, config: ChainConfig, envmap: EnvMap, message: str) -> str | None:
    """Commit ``envmap`` on the branch of the map, which is created when missing; the commit,
    or None when the map there says the same. Neither the working tree nor the current branch
    changes."""
    branch = config.git_rules.map_branch
    text = json.dumps(envmap.to_json(), indent=2, ensure_ascii=False) + "\n"
    if _content(root, branch) == text:
        return None
    if current_branch(root) == branch:
        raise GitError(f"{branch} is checked out: switch to another branch to change the map")
    blob = _plumb(root, "hash-object", "-w", "--stdin", data=text.encode("utf-8"))
    tree = _plumb(root, "mktree", data=f"100644 blob {blob}\t{MAP_FILE}\n".encode())
    parent: list[str] = []
    if branch_exists(root, branch):
        parent = ["-p", str(_git(root, "rev-parse", f"refs/heads/{branch}")).strip()]
    commit = str(_git(root, "commit-tree", tree, *parent, "-m", message)).strip()
    _git(root, "update-ref", f"refs/heads/{branch}", commit)
    return commit


# ---------------------------------------------------------------- reading the branches


@dataclass(frozen=True)
class Fact:
    """One attribute of one element of a node: where it is and what it says."""

    path: str  # "" for the node itself, "/ON[0]/DOMAIL[1]" for an element inside it
    tag: str
    attribute: str
    value: str
    element: Mapping[str, str]  # the element's attributes, for the conditions of a key

    def fits(self, selector: Selector) -> bool:
        if self.attribute != selector.attribute:
            return False
        if selector.tag is not None and selector.tag != self.tag:
            return False
        return all(self.element.get(key) == value for key, value in selector.where.items())

    @property
    def key(self) -> str:
        """The key that names this attribute, as narrow as the element allows."""
        if not self.path:
            return self.attribute
        name = self.element.get("NAME")
        if self.tag == "VARIABLE" and self.attribute == "VALUE" and name:
            return f"{self.tag}[NAME={name}]/@{self.attribute}"
        return f"{self.tag}/@{self.attribute}"


def children(data: Mapping[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """The elements inside ``data``: (step of the path, tag, element), in document order."""
    for key, value in data.items():
        if key in STRUCTURE or not isinstance(value, list):
            continue
        seen: dict[str, int] = {}
        for entry in value:
            if not isinstance(entry, dict):
                continue
            tag = str(entry.get("tag", key))
            label = str(entry.get("NAME") or entry.get("link") or "")
            step = f"{tag}[{label}]"
            seen[step] = seen.get(step, 0) + 1
            yield (step if label and seen[step] == 1 else f"{step}#{seen[step]}", tag, entry)


def facts(
    tag: str, data: Mapping[str, Any], extra: Mapping[str, str] | None = None, path: str = ""
) -> Iterator[Fact]:
    """Every attribute of a node and of the elements inside it; ``extra`` are the attributes
    kept apart from the node (the technical ones: the datacenter is one of them)."""
    element = {k: v for k, v in data.items() if isinstance(v, str) and k not in STRUCTURE}
    for attribute, value in {**element, **(extra or {})}.items():
        yield Fact(path, tag, attribute, value, element)
    for step, child_tag, child in children(data):
        yield from facts(child_tag, child, None, f"{path}/{step}")


def node_tag(data: Mapping[str, Any]) -> str:
    return str(data.get("tag") or "JOB")


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def load_nodes(root: Path) -> dict[str, tuple[str, dict[str, Any], dict[str, str]]]:
    """Node (``F/`` a folder, ``F/J`` a job) -> its tag, its JSON and its technical attributes,
    for the snapshot at ``root``."""
    nodes: dict[str, tuple[str, dict[str, Any], dict[str, str]]] = {}
    folders = root / "folders"
    if not folders.is_dir():
        return nodes
    for folder in sorted(p for p in folders.iterdir() if (p / "folder.json").is_file()):
        sidecar = root / "meta" / "folders" / f"{folder.name}.json"
        meta = _read(sidecar) if sidecar.is_file() else {}
        data = _read(folder / "folder.json")
        nodes[f"{folder.name}/"] = (node_tag(data), data, dict(meta.get("attrs", {})))
        jobs = folder / "jobs"
        for job in sorted(jobs.glob("*.json")) if jobs.is_dir() else ():
            technical = dict(meta.get("jobs", {}).get(job.stem, {}))
            nodes[f"{folder.name}/{job.stem}"] = ("JOB", _read(job), technical)
    return nodes


# ---------------------------------------------------------------- the letter and the words


def letter_pattern(rule: LetterRule, letter: str) -> re.Pattern[str] | None:
    """``letter`` in front of a prefix of the rule, at the start of a name inside a value."""
    if not rule.enabled or not letter:
        return None
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(letter)}(?={rule._alternation()})")


def without_letter(value: str, pattern: re.Pattern[str] | None) -> str:
    """``value`` with the environment's letter replaced by a mark, wherever a name starts."""
    return value if pattern is None else pattern.sub(_MARK, value)


def one_word(values: Mapping[str, str]) -> dict[str, str] | None:
    """The one word that differs between texts otherwise the same, per environment; None when
    the texts differ in more than a word, or are a single word each."""
    split = {env: _WORDS.split(value) for env, value in values.items()}
    lengths = {len(parts) for parts in split.values()}
    if len(lengths) != 1 or lengths == {1}:
        return None
    differing = [
        i for i in range(lengths.pop()) if len({parts[i] for parts in split.values()}) > 1
    ]
    if len(differing) != 1 or differing[0] % 2:  # odd positions are what separates the words
        return None
    words = {env: parts[differing[0]] for env, parts in split.items()}
    return words if all(words.values()) else None


@dataclass(frozen=True)
class _Seen:
    """What the branches show for one attribute of one node: the value of each environment
    that has it, when they are not all the same and the letter does not explain them."""

    node: str
    fact: Fact  # as the first environment that has it shows it
    values: Mapping[str, str]


def _varying(root: Path, config: ChainConfig, branches: Mapping[str, str]) -> Iterator[_Seen]:
    letters = load_repo(root).env_letters()
    patterns = {env: letter_pattern(config.letter_rule, letters.get(env, "")) for env in branches}
    found: dict[tuple[str, str, str], dict[str, Fact]] = {}
    for env, branch in branches.items():
        with snapshot(root, branch) as tree:
            for node, (tag, data, technical) in load_nodes(tree).items():
                for fact in facts(tag, data, technical):
                    found.setdefault((node, fact.path, fact.attribute), {})[env] = fact
    for (node, _path, _attribute), per_env in found.items():
        if len(per_env) < 2:
            continue
        values = {env: fact.value for env, fact in per_env.items()}
        if len(set(values.values())) == 1:
            continue
        if len({without_letter(value, patterns[env]) for env, value in values.items()}) == 1:
            continue  # the same name, with the letter of each environment
        yield _Seen(node, next(iter(per_env.values())), values)


# ---------------------------------------------------------------- derived from the branches


@dataclass(frozen=True)
class LeftOut:
    """Values that vary but are not in the map: too few nodes show them."""

    key: str
    values: Mapping[str, str]
    nodes: int
    inline: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"key": self.key, "values": dict(self.values), "nodes": self.nodes,
                "inline": self.inline}  # fmt: skip


@dataclass(frozen=True)
class Derived:
    """What the branches say varies: the entries the map lacks, and the map with them."""

    environments: tuple[str, ...]
    entries: tuple[MapEntry, ...]  # new ones only
    nodes: Mapping[str, int]  # entry -> the nodes that show it
    left_out: tuple[LeftOut, ...]
    envmap: EnvMap

    def to_json(self) -> dict[str, Any]:
        return {
            "environments": list(self.environments),
            "entries": [{**e.to_json(), "nodes": self.nodes.get(e.name, 0)} for e in self.entries],
            "known": [
                {"name": e.name, "nodes": self.nodes.get(e.name, 0)}
                for e in self.envmap.entries
                if e not in self.entries
            ],
            "left_out": [item.to_json() for item in self.left_out],
        }


def _covers(entry: MapEntry, key: str, inline: bool, values: Mapping[str, str]) -> bool:
    if (entry.key, entry.inline) != (key, inline):
        return False
    return all(entry.values.get(env) == value for env, value in values.items())


@dataclass
class _Tally:
    counts: dict[tuple[str, bool, tuple[tuple[str, str], ...]], int] = field(default_factory=dict)

    def add(self, key: str, inline: bool, values: Mapping[str, str]) -> None:
        item = (key, inline, tuple(values.items()))
        self.counts[item] = self.counts.get(item, 0) + 1

    def ordered(self, keys: Sequence[str]) -> list[tuple[str, bool, dict[str, str], int]]:
        """More environments first, then more nodes: the fuller picture names the entry."""
        rows = [(k, inline, dict(v), n) for (k, inline, v), n in self.counts.items()]
        return sorted(rows, key=lambda r: (keys.index(r[0]), -len(r[2]), -r[3], sorted(r[2])))


def derive(
    root: Path,
    config: ChainConfig,
    envmap: EnvMap,
    *,
    keys: Sequence[str] = DEFAULT_KEYS,
    text_keys: Sequence[str] = (),
    min_nodes: int = 2,
) -> Derived:
    """What the environments' branches show for ``keys`` (the whole value) and ``text_keys``
    (one word of a text), as entries the map does not have yet. Nothing is removed from the
    map, and values that fewer than ``min_nodes`` nodes show are left out of it: they are what
    one job has, not what the environment has."""
    branches = _branches(root, config)
    whole = [parse_spec(key) for key in keys]
    texts = [parse_spec(key, inline=True) for key in text_keys]
    tally = _Tally()
    for seen in _varying(root, config, branches):
        for selector in whole:
            if seen.fact.fits(selector):
                tally.add(selector.spec, False, seen.values)
        for selector in texts:
            if seen.fact.fits(selector):
                words = one_word(seen.values)
                tally.add(selector.spec, words is not None, words or seen.values)
    order = [selector.spec for selector in (*whole, *texts)]
    merged = envmap
    nodes: dict[str, int] = {}
    left: list[LeftOut] = []
    for key, inline, values, count in tally.ordered(order):
        known = next((e for e in merged.entries if _covers(e, key, inline, values)), None)
        if known is not None:
            nodes[known.name] = nodes.get(known.name, 0) + count
        elif count < min_nodes or (key in text_keys and not inline):
            left.append(LeftOut(key, values, count, inline))
        else:
            merged = add_entry(merged, key, values, environments=tuple(config.environments),
                               inline=inline)  # fmt: skip
            nodes[merged.entries[-1].name] = count
    new = tuple(entry for entry in merged.entries if entry not in envmap.entries)
    return Derived(tuple(branches), new, nodes, tuple(left), merged)


def _branches(root: Path, config: ChainConfig) -> dict[str, str]:
    branches = env_branches(root, config)
    if len(branches) < 2:
        have = ", ".join(branches.values()) or "none"
        raise ChainError(
            "two environments at least are needed to see what varies between them "
            f"(branches there: {have}): refresh each one from its export first"
        )
    return branches


# ---------------------------------------------------------------- what else varies


@dataclass(frozen=True)
class Suggestion:
    """An attribute the map does not explain, whose values vary between environments."""

    key: str
    nodes: int
    tuples: int  # distinct sets of whole values
    words: int | None  # distinct sets of the one word that differs; None when more differs
    example: Mapping[str, str]

    @property
    def text(self) -> bool:
        """The values are texts that differ in one word: a key for ``--text``."""
        return self.words is not None

    def to_json(self) -> dict[str, Any]:
        return {"key": self.key, "nodes": self.nodes, "tuples": self.tuples, "words": self.words,
                "text": self.text, "example": dict(self.example)}  # fmt: skip


def explained(envmap: EnvMap, fact: Fact, values: Mapping[str, str]) -> bool:
    """Whether an entry of the map says these values stand for each other."""
    for entry in envmap.entries:
        if not fact.fits(entry.selector):
            continue
        if not entry.inline and all(entry.values.get(e) == v for e, v in values.items()):
            return True
        words = one_word(values) if entry.inline else None
        if words and all(entry.values.get(e) == v for e, v in words.items()):
            return True
    return False


def suggest(root: Path, config: ChainConfig, envmap: EnvMap) -> tuple[Suggestion, ...]:
    """The attributes whose values vary between the environments' branches and that neither
    the letter nor the map explains, most frequent first. The technical attributes (dates,
    versions) are not looked at: they always vary."""
    technical = set(config.volatile_attributes)
    whole: dict[str, dict[tuple[tuple[str, str], ...], int]] = {}
    words: dict[str, set[tuple[tuple[str, str], ...]] | None] = {}
    for seen in _varying(root, config, _branches(root, config)):
        if seen.fact.attribute in technical or explained(envmap, seen.fact, seen.values):
            continue
        key = seen.fact.key
        item = tuple(seen.values.items())
        whole.setdefault(key, {})
        whole[key][item] = whole[key].get(item, 0) + 1
        word = one_word(seen.values)
        known = words.setdefault(key, set())
        if word is None:
            words[key] = None
        elif known is not None:
            known.add(tuple(word.items()))
    found = []
    for key, tuples in whole.items():
        fitting = words[key]
        first = max(tuples, key=lambda item: tuples[item])
        example = one_word(dict(first)) if fitting is not None else None
        found.append(Suggestion(key, sum(tuples.values()), len(tuples),
                                None if fitting is None else len(fitting),
                                example or dict(first)))  # fmt: skip
    return tuple(sorted(found, key=lambda s: (-s.nodes, s.key)))


# ---------------------------------------------------------------- what every adapter does


def show_map(repo: ChainRepo) -> dict[str, Any]:
    """The map as it is shown: its branch, the letter and the branch of each environment (the
    branches that exist), and the entries."""
    return {
        "branch": repo.config.git_rules.map_branch,
        "letters": repo.env_letters(),
        "branches": env_branches(repo.root, repo.config),
        **read_map(repo.root, repo.config).to_json(),
    }


def suggest_map(repo: ChainRepo) -> tuple[Suggestion, ...]:
    """What else varies between the branches, that neither the letter nor the map explains."""
    return suggest(repo.root, repo.config, read_map(repo.root, repo.config))


def derive_map(
    repo: ChainRepo,
    *,
    keys: Sequence[str] = (),
    text_keys: Sequence[str] = (),
    min_nodes: int = 2,
    apply: bool = False,
) -> tuple[Derived, bool]:
    """What the branches show and the map lacks, for :data:`DEFAULT_KEYS` and ``keys``; with
    ``apply`` the new entries are committed on the branch of the map. The second value says
    whether anything was written."""
    root, config = repo.root, repo.config
    found = derive(
        root,
        config,
        read_map(root, config),
        keys=tuple(dict.fromkeys((*DEFAULT_KEYS, *keys))),
        text_keys=tuple(text_keys),
        min_nodes=min_nodes,
    )
    count = len(found.entries)
    if not (apply and count):
        return found, False
    write_map(root, config, found.envmap, f"map: {count} {_entries(count)} derived")
    return found, True


def _entries(count: int) -> str:
    return "entry" if count == 1 else "entries"


def add_to_map(
    repo: ChainRepo,
    key: str,
    values: Mapping[str, str],
    *,
    name: str | None = None,
    inline: bool = False,
) -> tuple[EnvMap, str]:
    """One more entry, committed on the branch of the map; the map and the name it got."""
    envmap = add_entry(
        read_map(repo.root, repo.config),
        key,
        values,
        name=name,
        inline=inline,
        environments=tuple(repo.config.environments),
    )
    given = envmap.entries[-1].name
    write_map(repo.root, repo.config, envmap, f"map: add {given}")
    return envmap, given


def remove_from_map(repo: ChainRepo, name: str) -> EnvMap:
    """The map without the entry ``name``, committed on its branch."""
    envmap = remove_entry(read_map(repo.root, repo.config), name)
    write_map(repo.root, repo.config, envmap, f"map: remove {name}")
    return envmap


def rename_in_map(repo: ChainRepo, old: str, new: str) -> EnvMap:
    """The entry ``old`` called ``new``, committed on the branch of the map."""
    envmap = rename_entry(read_map(repo.root, repo.config), old, new)
    write_map(repo.root, repo.config, envmap, f"map: rename {old} to {new}")
    return envmap
