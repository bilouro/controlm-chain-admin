"""One environment's branch read in the terms of another, to compare them and to take from one.

Two environments differ in what is expected to differ: the letter of the names, the machines,
the users, the datacenter, a code inside a text. Before two of their branches are compared, the
head side (the *source* environment) is rewritten, in a copy, with the values the base side (the
*target*) would have:

* a value the target has at the same place already is kept as it is;
* a value the map (:mod:`controlm_chain_admin.core.envmap`) knows is replaced by the target's;
  when the map gives several, the one the target has there wins, then the one of a preferred
  entry, else the value is kept and a warning says so;
* a word the map knows inside a text is replaced by the target's word;
* the source's letter in front of a prefix of the chain (``UP77_BATCH``) becomes the target's;
* a condition whose name differs by the environments' letters only, or that the same jobs use
  the same way under another name, is called as the target calls it.

What is left after that is a real difference. And what is taken from the copy arrives in the
target's terms: its user, its machine, its condition names.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.compare import (
    _load,
    _match_folders,
    _match_jobs,
    _name_pairs,
    _relinked,
    _Side,
)
from controlm_chain_admin.core.constants import Selector
from controlm_chain_admin.core.envmap import (
    STRUCTURE,
    EnvMap,
    Fact,
    children,
    facts,
    letter_pattern,
    load_nodes,
    read_map,
)
from controlm_chain_admin.core.letter import LetterRule
from controlm_chain_admin.core.links import LINKS_FILE
from controlm_chain_admin.core.memfs import copy_file, copy_tree, memory_dir
from controlm_chain_admin.core.repo import CHAIN_FILE, ChainConfig, load_repo, write_json
from controlm_chain_admin.core.textcache import read_text
from controlm_chain_admin.core.timing import phase

_BOUNDARY = r"(?<![A-Za-z0-9])"
_PARTS = (CHAIN_FILE, "envs", "folders", "meta")
_MARK = "\x00"


@dataclass(frozen=True)
class Unsure:
    """A value of the source the map gives several answers for: kept as it is."""

    key: str
    value: str
    options: tuple[tuple[str, str], ...]  # (the target's value, the entry of the map)
    places: tuple[tuple[str, str, str], ...]  # (node, path of the element, attribute)

    def message(self, source: str, target: str, nodes: Sequence[str]) -> str:
        more = f" and {len(nodes) - 1} more" if len(nodes) > 1 else ""
        options = " or ".join(f"{value} ({name})" for value, name in self.options)
        return (
            f"{self.key} {self.value} of {source} is {options} in {target}: kept as it is "
            f"({nodes[0]}{more}); prefer one of the entries to settle it"
        )


@dataclass(frozen=True)
class Translation:
    """What was rewritten on the head side, from the ``source`` environment to the ``target``."""

    source: str
    target: str
    values: int = 0  # whole values the map knows
    texts: int = 0  # values with a word the map knows
    letters: int = 0  # values with the letter of the environment in front of a prefix
    links: int = 0  # conditions called as the target calls them
    warnings: tuple[str, ...] = ()
    unsure: tuple[Unsure, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "values": self.values,
            "texts": self.texts,
            "letters": self.letters,
            "links": self.links,
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------- the values


@dataclass
class _Values:
    """Rewrites the values of the source environment as the target has them, and counts."""

    source: str
    target: str
    whole: list[tuple[Selector, str, str, str, str]]  # selector, source, target, key, entry
    words: list[tuple[Selector, re.Pattern[str], str]]  # selector, source word, target word
    letter: re.Pattern[str] | None
    target_letter: str
    skip: frozenset[str]
    prefer: frozenset[str] = frozenset()
    values: int = 0
    texts: int = 0
    letters: int = 0
    unsure: dict[tuple[str, str, tuple[tuple[str, str], ...]], list[tuple[str, str, str]]] = field(
        default_factory=dict
    )

    def value(self, node: str, fact: Fact, there: str | None) -> str:
        """``fact``'s value as the target has it; ``there`` is what the target has in place."""
        value = fact.value
        if value == there:
            return value
        found = [
            (key, to, name)
            for sel, was, to, key, name in self.whole
            if was == value and fact.fits(sel)
        ]
        if found:
            options = tuple(dict.fromkeys(to for _key, to, _name in found))
            preferred = tuple(dict.fromkeys(to for _k, to, name in found if name in self.prefer))
            if there not in options and len(preferred) == 1:
                options = preferred
            if there in options or len(options) == 1:
                chosen = there if there in options else options[0]
                self.values += chosen != value
                return str(chosen)
            first = {to: name for _key, to, name in reversed(found)}  # a value's first entry
            answers = tuple((to, first[to]) for to in options)
            place = (node, fact.path, fact.attribute)
            self.unsure.setdefault((found[0][0], value, answers), []).append(place)
            return value
        text = value
        for selector, word, to in self.words:
            if fact.fits(selector):
                text = word.sub(to.replace("\\", "\\\\"), text)
        self.texts += text != value
        if self.letter is not None:
            named = self.letter.sub(self.target_letter, text)
            self.letters += named != text
            text = named
        return text

    def rewrite(
        self,
        node: str,
        tag: str,
        data: dict[str, Any],
        there: Mapping[tuple[str, str], str],
        path: str = "",
    ) -> bool:
        """Rewrite, in place, the attributes of an element and of the elements inside it;
        whether anything changed."""
        element = {k: v for k, v in data.items() if isinstance(v, str) and k not in STRUCTURE}
        changed = self._attributes(node, Fact(path, tag, "", "", element), data, there)
        for step, child_tag, child in children(data):
            changed |= self.rewrite(node, child_tag, child, there, f"{path}/{step}")
        return changed

    def _attributes(
        self, node: str, place: Fact, attrs: dict[str, Any], there: Mapping[tuple[str, str], str]
    ) -> bool:
        changed = False
        for attribute, value in list(attrs.items()):
            if not isinstance(value, str) or attribute in self.skip:
                continue
            fact = Fact(place.path, place.tag, attribute, value, place.element)
            new = self.value(node, fact, there.get((place.path, attribute)))
            if new != value:
                attrs[attribute] = new
                changed = True
        return changed

    def technical(
        self,
        node: str,
        tag: str,
        element: Mapping[str, Any],
        attrs: dict[str, Any],
        there: Mapping[tuple[str, str], str],
    ) -> bool:
        """Rewrite, in place, the attributes of a node that are kept apart from it."""
        own = {k: v for k, v in element.items() if isinstance(v, str) and k not in STRUCTURE}
        return self._attributes(node, Fact("", tag, "", "", own), attrs, there)

    def kept(self) -> tuple[Unsure, ...]:
        return tuple(
            Unsure(key, value, options, tuple(places))
            for (key, value, options), places in self.unsure.items()
        )


def kept_unsure(
    translation: Translation, root: Path, folders: Collection[str] | None = None
) -> list[str]:
    """One warning per value of the source environment that the map could not settle and that
    the files at ``root`` hold (in ``folders`` only, when given): it goes on as it is."""
    if not translation.unsure:
        return []
    nodes = load_nodes(root)
    found = []
    for unsure in translation.unsure:
        holding = []
        for node, path, attribute in unsure.places:
            if node not in nodes or (folders is not None and node.split("/")[0] not in folders):
                continue
            tag, data, technical = nodes[node]
            if any(
                (f.path, f.attribute, f.value) == (path, attribute, unsure.value)
                for f in facts(tag, data, technical)
            ):
                holding.append(node)
        if holding:
            found.append(unsure.message(translation.source, translation.target, holding))
    return found


def _values(config: ChainConfig, envmap: EnvMap, letters: Mapping[str, str], source: str,
            target: str, prefer: Sequence[str] = ()) -> _Values:  # fmt: skip
    for name in prefer:
        envmap.named(name)  # an entry the map lacks is refused
    whole: list[tuple[Selector, str, str, str, str]] = []
    words: list[tuple[Selector, re.Pattern[str], str]] = []
    for entry in envmap.entries:
        was, to = entry.values.get(source), entry.values.get(target)
        if was is None or to is None or was == to:
            continue
        if entry.inline:
            pattern = re.compile(rf"{_BOUNDARY}{re.escape(was)}(?![A-Za-z0-9])")
            words.append((entry.selector, pattern, to))
        else:
            whole.append((entry.selector, was, to, entry.key, entry.name))
    rule = config.letter_rule
    letter = letters.get(source, "")
    other = letters.get(target, "")
    pattern_ = letter_pattern(rule, letter) if other and other != letter else None
    return _Values(source, target, whole, words, pattern_, other,
                   frozenset(rule.attributes) | STRUCTURE, frozenset(prefer))  # fmt: skip


def _read(path: Path) -> dict[str, Any]:
    loaded = json.loads(read_text(path))
    return loaded if isinstance(loaded, dict) else {}


def _translate_values(base_root: Path, copy: Path, rewriter: _Values) -> None:
    base = load_nodes(base_root)
    sidecars: dict[str, dict[str, Any]] = {}
    stale: set[str] = set()
    for node, (tag, data, _technical) in load_nodes(copy).items():
        folder, _, job = node.partition("/")
        there: dict[tuple[str, str], str] = {}
        if node in base:
            base_tag, base_data, base_technical = base[node]
            there = {(f.path, f.attribute): f.value
                     for f in facts(base_tag, base_data, base_technical)}  # fmt: skip
        own = {k: v for k, v in data.items() if isinstance(v, str)}
        if rewriter.rewrite(node, tag, data, there):
            file = copy / "folders" / folder
            write_json(file / "jobs" / f"{job}.json" if job else file / "folder.json", data)
        sidecar = copy / "meta" / "folders" / f"{folder}.json"
        if folder not in sidecars and sidecar.is_file():
            sidecars[folder] = _read(sidecar)
        meta = sidecars.get(folder)
        if meta is None:
            continue
        attrs = meta.get("jobs", {}).get(job) if job else meta.get("attrs")
        if isinstance(attrs, dict) and rewriter.technical(node, tag, own, attrs, there):
            stale.add(folder)
    for folder in sorted(stale):
        write_json(copy / "meta" / "folders" / f"{folder}.json", sidecars[folder])


# ---------------------------------------------------------------- the names of the conditions


def _shape(
    rule: LetterRule, letters: Mapping[str, str], pair: tuple[str, str]
) -> Callable[[str], str]:
    """A condition name without the letters it may carry: any environment's (or none) in front
    of a prefix of the chain, and one of the two environments' at the start of any other name.
    Two names of the same shape differ by those letters only."""
    ends = "|".join(re.escape(letter) for letter in dict.fromkeys(pair))
    other = re.compile(rf"(?<![A-Za-z0-9{_MARK}])(?:{ends})")
    known = "|".join(re.escape(letter) for letter in dict.fromkeys(letters.values()) if letter)
    chain = (
        re.compile(rf"{_BOUNDARY}(?:{known})?(?={rule._alternation()})") if rule.enabled else None
    )

    def shape(name: str) -> str:
        return other.sub(_MARK, name if chain is None else chain.sub(_MARK, name))

    return shape


def _letter_pairs(base: _Side, head: _Side, shape: Callable[[str], str]) -> dict[str, str]:
    """Head link id -> base link id, for a condition whose names differ by the letters of the
    environments only. A name of another application carries the letter of its environment and
    keeps it here; a name promoted as it was carries the letter of where it came from."""

    def by_shape(links: list[str]) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for link in links:
            found.setdefault(shape(link), []).append(link)
        return found

    gone = by_shape([k for k in base.names if k not in head.names])
    arrived = by_shape([k for k in head.names if k not in base.names])
    return {
        new[0]: gone[key][0]
        for key, new in arrived.items()
        if _MARK in key and len(new) == 1 and len(gone.get(key, ())) == 1
    }


def _relink(copy: Path, pairs: Mapping[str, str], names: Mapping[str, str]) -> None:
    """Call the conditions of ``pairs`` (id there -> id here) as the target calls them, in
    every file of the copy that mentions one."""
    if not pairs:
        return
    folders = copy / "folders"
    for path in sorted(folders.glob("*/folder.json")) + sorted(folders.glob("*/jobs/*.json")):
        data = _read(path)
        renamed = _relinked(data, pairs)
        if renamed != data:
            write_json(path, renamed)
    for path in sorted(folders.glob(f"*/{LINKS_FILE}")):
        entries = _read(path).get("links")
        if not isinstance(entries, dict) or not any(link in pairs for link in entries):
            continue
        renamed = {}
        for link, entry in entries.items():
            if link in pairs:
                renamed[pairs[link]] = {"name": names.get(pairs[link], pairs[link])}
            else:
                renamed[link] = entry
        write_json(path, {"links": renamed})


def _translate_links(base_root: Path, copy: Path, shape: Callable[[str], str] | None) -> int:
    base = _load(base_root)
    pairs = {} if shape is None else _letter_pairs(base, _load(copy), shape)
    _relink(copy, pairs, base.names)
    head = _load(copy)
    folder_map = _match_folders(base, head)
    job_map, _kinds = _match_jobs(base, head, folder_map)
    node_map = {f"{old}/": f"{new}/" for old, new in folder_map.items()} | job_map
    same_use = {new: old for old, new in _name_pairs(base, head, node_map).items()}
    _relink(copy, same_use, base.names)
    return len(pairs) + len(same_use)


# ---------------------------------------------------------------- the whole side


def _rules(base_root: Path, head_root: Path) -> tuple[ChainConfig, dict[str, str]] | None:
    """The rules and the letters of the environments, as the target's side says them."""
    for root in (base_root, head_root):
        if (root / CHAIN_FILE).is_file():
            repo = load_repo(root)
            return repo.config, repo.env_letters()
    return None


@contextmanager
def translated(
    root: Path,
    base_root: Path,
    head_root: Path,
    source: str,
    target: str,
    prefer: Sequence[str] = (),
) -> Iterator[tuple[Path, Translation]]:
    """A copy of ``head_root`` (what ``source`` has) in the terms of ``target``, whose side is
    ``base_root``, and what was rewritten. ``root`` is the repository: the map is on a branch
    of it. ``prefer`` names the entries of the map that win where it gives several answers.
    Neither side is changed."""
    with memory_dir(f"{source} as {target}") as tmp:  # the copy lives in memory
        copy = tmp / "head"
        copy.mkdir()
        with phase("translate"):
            for name in _PARTS:  # what a snapshot holds: the working tree may have much more
                part = head_root / name
                if part.is_dir():
                    copy_tree(part, copy / name)
                elif part.is_file():
                    copy_file(part, copy / name)
            rules = _rules(base_root, copy)
        if rules is None:
            yield copy, Translation(source, target)
            return
        config, letters = rules
        with phase("translate"):
            rewriter = _values(config, read_map(root, config), letters, source, target, prefer)
            _translate_values(base_root, copy, rewriter)
            pair = (letters.get(source, ""), letters.get(target, ""))
            shape = _shape(config.letter_rule, letters, pair) if all(pair) else None
            links = _translate_links(base_root, copy, shape)
            kept = rewriter.kept()
        warnings = tuple(
            u.message(source, target, list(dict.fromkeys(node for node, _p, _a in u.places)))
            for u in kept
        )
        yield copy, Translation(
            source, target, rewriter.values, rewriter.texts, rewriter.letters, links,
            warnings, kept,
        )  # fmt: skip
