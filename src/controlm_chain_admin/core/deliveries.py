"""Deliveries kept for later: items put aside under a name, and one import file from several.

A change seldom travels alone or at once. Something is chosen today (three items of a
comparison, a job as uat has it), something else next week, and the import file for an
environment is made when it is time, from the ones that are ready. A *delivery* is that choice
kept: a name, the ref and the commit the items come from, and the items, written as ``take``
and ``package`` write them (``job:F/J``, ``attr:F/J@NAME``, ``folder:F``...).

They are kept in ``deliveries.json`` on the branch of the map, which belongs to no
environment, written by plumbing: no checkout changes. A delivery is tied to the commit it was
made from, so the file it gives is the same whenever it is made; when its branch moved since,
the list and the package say so.

:func:`build_delivery` makes one package for a target from one or several deliveries: the
target as its branch has it, with the items of each on it, in order. Two that give one place
two values are refused. An item the target already has as the delivery gives it is packaged
all the same, with its folder: what was chosen goes in the file.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.environments import EXPORT_SUBJECT, held_env
from controlm_chain_admin.core.envmap import branch_file, write_branch_file
from controlm_chain_admin.core.errors import ChainError, InvalidChange, ModelError, TakeConflict
from controlm_chain_admin.core.history import CommitInfo, _git, resolve
from controlm_chain_admin.core.links import (
    build_links,
    collect_conditions,
    read_names,
    write_names,
)
from controlm_chain_admin.core.memfs import copy_tree, memory_dir
from controlm_chain_admin.core.package import Package, assemble
from controlm_chain_admin.core.repo import ChainConfig, ChainRepo, load_repo
from controlm_chain_admin.core.selection import open_sides
from controlm_chain_admin.core.take import KINDS, take_into

FILE = "deliveries.json"
#: kinds of item whose id says a folder: ``KIND:FOLDER/...`` or ``folder:FOLDER``
_IN_A_FOLDER = ("job", "attr", "var", "rel", "group", "folder")


@dataclass(frozen=True)
class Delivery:
    name: str
    head: str  # the ref the items come from, as it was called
    sha: str  # its commit when the delivery was kept
    items: tuple[str, ...]
    base: str | None = None  # the ref it was compared with; None: picked from the chain
    prefer: tuple[str, ...] = ()
    note: str = ""
    saved: str = ""  # the day it was kept

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "head": self.head,
            "sha": self.sha,
            "items": list(self.items),
            "base": self.base,
            "prefer": list(self.prefer),
            "note": self.note,
            "saved": self.saved,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Delivery:
        try:
            return cls(
                str(data["name"]), str(data["head"]), str(data["sha"]),
                tuple(str(item) for item in data["items"]),
                None if data.get("base") is None else str(data["base"]),
                tuple(str(entry) for entry in data.get("prefer", ())),
                str(data.get("note", "")), str(data.get("saved", "")),
            )  # fmt: skip
        except (KeyError, TypeError, AttributeError) as exc:
            raise ModelError(f"{FILE}: a delivery cannot be read ({exc})") from exc


def read_deliveries(root: Path, config: ChainConfig) -> tuple[Delivery, ...]:
    """The deliveries kept, in the order they were; none when nothing was kept yet."""
    content = branch_file(root, config.git_rules.map_branch, FILE)
    if content is None:
        return ()
    try:
        entries = json.loads(content).get("deliveries", [])
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ModelError(f"{FILE} on {config.git_rules.map_branch}: {exc}") from exc
    return tuple(Delivery.from_json(entry) for entry in entries)


def _write(repo: ChainRepo, deliveries: Sequence[Delivery], message: str) -> None:
    data = {"version": 1, "deliveries": [d.to_json() for d in deliveries]}
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    write_branch_file(repo.root, repo.config.git_rules.map_branch, FILE, text, message)


def _named(deliveries: Sequence[Delivery], name: str) -> Delivery:
    for delivery in deliveries:
        if delivery.name == name:
            return delivery
    known = ", ".join(d.name for d in deliveries) or "none"
    raise ChainError(f"no delivery called {name!r} (kept: {known})")


def save_delivery(
    repo: ChainRepo,
    name: str,
    head: str,
    items: Sequence[str],
    *,
    base: str | None = None,
    prefer: Sequence[str] = (),
    note: str = "",
    today: str | None = None,
) -> Delivery:
    """Keep ``items`` of ``head`` (a branch, a tag, a commit) under ``name``. ``base`` is the
    ref they were chosen against, when they come from a comparison."""
    name = name.strip()
    if not name:
        raise InvalidChange("a name is needed to keep a delivery")
    chosen = tuple(dict.fromkeys(items))
    if not chosen:
        raise InvalidChange("nothing to keep: a delivery holds one item at least")
    for item in chosen:
        kind, sep, rest = item.partition(":")
        if not sep or kind not in KINDS or not rest:
            raise InvalidChange(
                f"unknown item {item!r}: an id is KIND:WHAT, as in job:FOLDER/JOB, with one of "
                f"{', '.join(KINDS)}"
            )
    kept = read_deliveries(repo.root, repo.config)
    if any(delivery.name == name for delivery in kept):
        raise InvalidChange(f"there is a delivery called {name!r} already: give it another name")
    sha = resolve(repo.root, head).sha
    if sha is None:
        raise InvalidChange("a delivery is kept from a commit: commit the working tree first")
    if base is not None:
        resolve(repo.root, base)
    delivery = Delivery(
        name, head, sha, chosen, base, tuple(prefer), note.strip(),
        today or datetime.date.today().isoformat(),
    )  # fmt: skip
    _write(repo, [*kept, delivery], f"deliveries: keep {name}")
    return delivery


def remove_delivery(repo: ChainRepo, name: str) -> tuple[Delivery, ...]:
    """Forget the delivery ``name``; the ones that stay."""
    kept = read_deliveries(repo.root, repo.config)
    gone = _named(kept, name)
    left = tuple(delivery for delivery in kept if delivery is not gone)
    _write(repo, left, f"deliveries: remove {name}")
    return left


def _moved(root: Path, delivery: Delivery) -> bool:
    """Whether the ref the delivery was kept from is elsewhere now, or gone."""
    try:
        return resolve(root, delivery.head).sha != delivery.sha
    except ChainError:
        return True


#: beyond this many files, the commits are looked for by folder: a command line has a limit
PATHS_AT_MOST = 100
_SEP = "\x1f"


def item_paths(items: Sequence[str]) -> list[str]:
    """The files the changes of the items are in: a folder's directory for a folder, a job's
    file for a job and for what is inside it, ``folder.json`` for what is the folder's own.
    Items that are in no folder (a link, a constant) have none."""
    paths: list[str] = []
    for item in items:
        kind, _, rest = item.partition(":")
        if kind == "exception":
            rest = rest.partition("@")[2]
        elif kind in ("attr", "var", "rel", "group"):
            rest = rest.rpartition("@")[0]
        elif kind not in _IN_A_FOLDER:
            continue
        folder, _, job = rest.partition("/")
        if not folder:
            continue
        if kind == "folder":
            path = f"folders/{folder}"
        elif job:
            path = f"folders/{folder}/jobs/{job}.json"
        else:
            path = f"folders/{folder}/folder.json"
        if path not in paths:
            paths.append(path)
    if len(paths) > PATHS_AT_MOST:
        return list(dict.fromkeys("/".join(p.split("/")[:2]) for p in paths))
    return paths


def _log(root: Path, revisions: str, paths: Sequence[str]) -> list[CommitInfo]:
    out = _git(root, "log", f"--format=%H{_SEP}%s{_SEP}%an{_SEP}%cI", revisions, "--", *paths)
    commits = []
    for line in str(out).splitlines():
        sha, subject, author, date = line.split(_SEP)
        commits.append(CommitInfo(sha, subject, author, date))
    return commits


def _last_export(root: Path, sha: str) -> str | None:
    """The nearest commit of ``sha``'s history that holds an export: where its work begins."""
    out = _git(root, "log", "-E", f"--grep={EXPORT_SUBJECT.pattern}", "--format=%H%x1f%s", sha)
    for line in str(out).splitlines():
        found, _, subject = line.partition(_SEP)
        if EXPORT_SUBJECT.match(subject):  # --grep also matches a line of the body
            return found
    return None


def delivery_commits(root: Path, delivery: Delivery) -> dict[str, list[dict[str, Any]]]:
    """The commits that changed what the delivery holds: those of its branch since the last
    export, up to the commit it was kept from (the exports left out), and apart those that
    touched the same files after it was kept, which are not in it. Newest first."""
    paths = item_paths(delivery.items)
    if not paths:
        return {"commits": [], "commits_after": []}
    since = _last_export(root, delivery.sha)
    kept = _log(root, f"{since}..{delivery.sha}" if since else delivery.sha, paths)
    try:
        now = resolve(root, delivery.head).sha
    except ChainError:
        now = None
    after = _log(root, f"{delivery.sha}..{now}", paths) if now and now != delivery.sha else []
    return {
        "commits": [c.to_json() for c in kept if not EXPORT_SUBJECT.match(c.subject)],
        "commits_after": [c.to_json() for c in after],
    }


def listed(repo: ChainRepo) -> list[dict[str, Any]]:
    """The deliveries as they are shown: with the environment each comes from, how many items
    it has, whether its ref moved since it was kept, and the commits it carries."""
    rows = []
    for delivery in read_deliveries(repo.root, repo.config):
        try:
            env = held_env(repo.root, repo.config, delivery.sha)
        except ChainError:
            env = None
        rows.append(
            {
                **delivery.to_json(),
                "count": len(delivery.items),
                "environment": env,
                "moved": _moved(repo.root, delivery),
                **delivery_commits(repo.root, delivery),
            }
        )
    return rows


def _folders(items: Sequence[str]) -> list[str]:
    """The folders the items are in: packaged whether the target differs there or not."""
    folders: list[str] = []
    for item in items:
        kind, _, rest = item.partition(":")
        if kind == "exception":
            rest = rest.partition("@")[2]
        elif kind not in _IN_A_FOLDER:
            continue
        folder = rest.partition("/")[0].partition("@")[0]
        if folder and folder not in folders:
            folders.append(folder)
    return folders


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "delivery"


def build_delivery(
    root: Path,
    target: str,
    names: Sequence[str],
    *,
    env: str | None = None,
    today: str | None = None,
    condition_names: str = "original",
    jobnames: str = "original",
) -> Package:
    """The import file of ``target`` (a branch: ``main``, ``env/bench``) with the items of the
    deliveries ``names`` on what it has, in that order."""
    repo = load_repo(root)
    kept = read_deliveries(root, repo.config)
    chosen = [_named(kept, name) for name in dict.fromkeys(names)]
    if not chosen:
        raise InvalidChange("choose one delivery at least")
    day = today or datetime.date.today().isoformat()
    warnings: list[str] = []
    with ExitStack() as stack:
        first = None
        copy = stack.enter_context(memory_dir("deliveries")) / "chosen"
        for delivery in chosen:
            sides = stack.enter_context(
                open_sides(root, target, delivery.sha, prefer=delivery.prefer)
            )
            if first is None:
                first = sides
                copy_tree(sides.base_root, copy)
            try:
                work = take_into(load_repo(copy), sides, delivery.items)
            except TakeConflict as exc:
                raise TakeConflict(
                    f"{delivery.name!r} and what was put before it disagree: {exc}",
                    exc.conflicts,
                ) from exc
            box = work.box
            write_names(
                box, build_links(collect_conditions(box), {**read_names(box), **work.names})
            )
            warnings += work.warnings
            if _moved(root, delivery):
                warnings.append(
                    f"{delivery.head} moved since {delivery.name!r} was kept "
                    f"({delivery.sha[:7]}): the file has what it had then"
                )
        assert first is not None
        items = tuple(dict.fromkeys(item for delivery in chosen for item in delivery.items))
        package = assemble(
            root, replace(first, head_root=copy), warnings, env, condition_names, jobnames,
            day, items, also=_folders(items),
        )  # fmt: skip
    label = "+".join(_slug(delivery.name) for delivery in chosen)
    return replace(package, filename=f"deploy_{package.env}_{label}_{day}.xml")
