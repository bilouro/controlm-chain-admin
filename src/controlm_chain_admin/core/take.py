"""Take changes of another branch into the checked-out one, item by item.

The comparison of the checked-out branch (base) with another branch (head) lists what the
other branch changed since they parted. Any item of it can be taken alone: one attribute of a
job, a job without its folder, a whole folder... Taking applies the change: where the checkout
still has the value the change started from, it gets the new one; where it already has the new
one, nothing happens; where it has a third value, that is a conflict, taken only when named in
``theirs``.

Items:

* ``subapp:S``: every folder of a sub-application that differs, each one whole;
* ``folder:F``: a whole folder (its jobs, conditions and metadata);
* ``job:F/J``: a whole job, not its folder;
* ``attr:NODE@ATTR``, ``var:NODE@%%NAME``: one attribute or variable of a folder (``F/``) or
  job (``F/J``);
* ``rel:NODE@LINK``: one predecessor or successor, at both of its ends;
* ``group:NODE@TAG``: one group of children (``ON``, ``QUANTITATIVE``...);
* ``link:LINK``: the name of a condition;
* ``const:ENV@NAME``: the value of a constant in one environment (its definition too, when the
  checkout does not have it);
* ``exception:ENV@NODE``: the exceptions of a folder or job in one environment.

Constants the taken content uses and the checkout does not have come along; neighbour jobs do
not: a condition nobody emits or waits for any more is a warning.

When the two branches hold different environments, the other branch is read in the terms of the
checked-out one first (:mod:`controlm_chain_admin.core.crossenv`): what is taken arrives with
the users, the machines and the condition names of the environment it arrives in.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from controlm_chain_admin.core.compare import (
    Comparison,
    _load,
    _match_folders,
    _match_jobs,
    _Side,
    compare,
)
from controlm_chain_admin.core.constants import PLACEHOLDER
from controlm_chain_admin.core.environments import current_branch
from controlm_chain_admin.core.errors import InvalidChange, TakeConflict
from controlm_chain_admin.core.history import resolve
from controlm_chain_admin.core.links import INDEX_FILE, LINK_KEY, collect_conditions, read_names
from controlm_chain_admin.core.memfs import remove_tree
from controlm_chain_admin.core.ops import JOBS_KEY, ORIGINALS_KEY
from controlm_chain_admin.core.overrides import Override, load_overrides, write_overrides
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json, write_json
from controlm_chain_admin.core.selection import Sides, open_sides
from controlm_chain_admin.core.textcache import read_text

if TYPE_CHECKING:
    from controlm_chain_admin.core.refactor import ChangeSet

KINDS = (
    "subapp", "folder", "job", "attr", "var", "rel", "group", "link", "const", "exception"
)  # fmt: skip
_SUBAPP = "SUB_APPLICATION"
_CONDITIONS = ("INCOND", "OUTCOND")
_ORDER_KEY = "folder_order"


@dataclass(frozen=True)
class Conflict:
    item: str
    mine: Any
    before: Any
    theirs: Any

    def to_json(self) -> dict[str, object]:
        return {"item": self.item, "mine": self.mine, "before": self.before, "theirs": self.theirs}


def _node_json(side: _Side, identity: str) -> dict[str, Any] | None:
    if identity.endswith("/"):
        return side.folders.get(identity[:-1])
    return side.jobs.get(identity)


def _refs(data: Mapping[str, Any] | None, link: str) -> dict[str, list[Any]]:
    """The conditions of a node through ``link``, by group."""
    return {
        group: [e for e in (data or {}).get(group, []) if e.get(LINK_KEY) == link]
        for group in _CONDITIONS
    }


def _uses_docond(data: Mapping[str, Any] | None, link: str) -> bool:
    return any(
        child.get(LINK_KEY) == link
        for block in (data or {}).get("ON", [])
        for child in block.get("children", [])
    )


def _links_of(data: Any) -> set[str]:
    """Every link a JSON tree references."""
    found: set[str] = set()
    if isinstance(data, dict):
        if isinstance(data.get(LINK_KEY), str):
            found.add(data[LINK_KEY])
        for value in data.values():
            found |= _links_of(value)
    elif isinstance(data, list):
        for value in data:
            found |= _links_of(value)
    return found


def _subapp_folders(side: _Side, name: str) -> list[str]:
    """The folders of a sub-application: the folder names it, or one of its jobs does."""
    found = []
    for folder, data in side.folders.items():
        jobs = (side.jobs.get(f"{folder}/{job}") for job in data.get(JOBS_KEY, []))
        if data.get(_SUBAPP) == name or any((job or {}).get(_SUBAPP) == name for job in jobs):
            found.append(folder)
    return found


def _place(order: Sequence[str], theirs: Sequence[str], folder: str) -> int:
    """Where ``folder`` goes in ``order`` to stand as it does in ``theirs``: after the nearest
    folder before it that both have, else in front of the nearest one after it, else last."""
    at = theirs.index(folder)
    earlier = [f for f in theirs[:at] if f in order]
    if earlier:
        return order.index(earlier[-1]) + 1
    later = [f for f in theirs[at + 1 :] if f in order]
    return order.index(later[0]) if later else len(order)


def _folder_files(root: Path, folder: str) -> dict[str, str]:
    """The files of a folder (no derived index) and its metadata sidecar, as text."""
    files: dict[str, str] = {}
    directory = root / "folders" / folder
    if directory.is_dir():
        for path in sorted(directory.rglob("*.json")):
            if path.name != INDEX_FILE:
                files[path.relative_to(root).as_posix()] = read_text(path)
    meta = root / "meta" / "folders" / f"{folder}.json"
    if meta.is_file():
        files[meta.relative_to(root).as_posix()] = read_text(meta)
    return files


@dataclass
class _Take:
    box: ChainRepo
    before: _Side
    after: _Side
    base_root: Path
    head_root: Path
    reverse: Mapping[str, str]  # head identity -> base identity
    forward: Mapping[str, str]  # base identity -> head identity
    theirs: set[str]
    conflicts: list[Conflict] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)  # link names to bring
    taken: set[str] = field(default_factory=set)  # nodes (head identities) taken in some way
    links: set[str] = field(default_factory=set)  # links the taken content references
    warnings: list[str] = field(default_factory=list)
    #: link -> the name the other environment has for it, where the two call it differently
    other_names: Mapping[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------ helpers

    def settle(self, item: str, mine: Any, before: Any, theirs: Any) -> bool:
        """Whether to write ``theirs``: the checkout still has ``before`` or it is forced."""
        if mine == theirs:
            return False
        if mine == before or item in self.theirs:
            return True
        self.conflicts.append(Conflict(item, mine, before, theirs))
        return False

    def path(self, identity: str) -> Path:
        folder, _, job = identity.partition("/")
        return self.box.job_file(folder, job) if job else self.box.folder_file(folder)

    def target(self, identity: str, item: str) -> str:
        """The checkout's node for a node of the other branch (by its name there or before)."""
        for candidate in (identity, self.reverse.get(identity, identity)):
            if self.path(candidate).is_file():
                return candidate
        what = "folder" if identity.endswith("/") else "job"
        raise InvalidChange(f"{item}: {identity} is not in the checkout: take the whole {what}")

    def read(self, identity: str) -> dict[str, Any]:
        return dict(read_json(self.path(identity)))

    def write(self, identity: str, data: Mapping[str, Any]) -> None:
        write_json(self.path(identity), data)

    def bring_names(self, data: Any) -> None:
        refs = _links_of(data)
        self.links |= refs
        for link in refs:
            if link in self.after.names:
                self.names.setdefault(link, self.after.names[link])

    # ------------------------------------------------------------ items

    def take(self, item: str) -> None:
        kind, sep, rest = item.partition(":")
        if not sep or kind not in KINDS or not rest:
            raise InvalidChange(
                f"unknown item {item!r}: an id is KIND:WHAT, as in job:FOLDER/JOB, with one of "
                f"{', '.join(KINDS)} (the list of what can be taken gives the ids)"
            )
        if kind in ("attr", "var", "rel", "group", "const", "exception"):
            left, at, right = rest.rpartition("@") if kind != "exception" else rest.partition("@")
            if not at or not left or not right:
                raise InvalidChange(f"unknown item {item!r}: {kind}:...@... expected")
            getattr(self, f"_{kind}")(item, left, right)
        else:
            getattr(self, f"_{kind}")(item, rest)

    def _originals(self, folder: str) -> dict[str, str]:
        meta_file = self.box.folder_meta_file(folder)
        if not meta_file.is_file():
            return {}
        return dict(read_json(meta_file).get(ORIGINALS_KEY, {}))

    def _set_original(self, folder: str, job: str, name: str) -> None:
        """Make ``name`` the JOBNAME Control-M has for the job: kept aside when it is not the
        name the repository calls it, forgotten when it is."""
        meta_file = self.box.folder_meta_file(folder)
        meta = dict(read_json(meta_file)) if meta_file.is_file() else {"attrs": {}, JOBS_KEY: {}}
        originals = {j: n for j, n in meta.get(ORIGINALS_KEY, {}).items() if j != job}
        if name != job:
            originals[job] = name
        if originals:
            meta[ORIGINALS_KEY] = originals
        else:
            meta.pop(ORIGINALS_KEY, None)
        write_json(meta_file, meta)

    def _jobname(self, item: str, node: str) -> None:
        """The JOBNAME Control-M has for a job the import numbered: it lives beside the job,
        not in it."""
        old = self.reverse.get(node, node)
        before = self.before.originals.get(old, old.partition("/")[2])
        theirs = self.after.originals.get(node, node.partition("/")[2])
        target = self.target(node, item)
        folder, _, job = target.partition("/")
        mine = self._originals(folder).get(job, job)
        if self.settle(item, mine, before, theirs):
            self._set_original(folder, job, theirs)
            self.taken.add(node)

    def _attr(self, item: str, node: str, name: str) -> None:
        if name == "JOBNAME" and not node.endswith("/"):
            self._jobname(item, node)
            return
        before = (_node_json(self.before, self.reverse.get(node, node)) or {}).get(name)
        theirs = (_node_json(self.after, node) or {}).get(name)
        target = self.target(node, item)
        data = self.read(target)
        if self.settle(item, data.get(name), before, theirs):
            if theirs is None:
                data.pop(name, None)
            else:
                data[name] = theirs
            self.write(target, data)
            self.taken.add(node)

    def _var(self, item: str, node: str, name: str) -> None:
        def value(data: Mapping[str, Any] | None) -> str | None:
            for variable in (data or {}).get("VARIABLE", []):
                if variable.get("NAME") == name:
                    return str(variable.get("VALUE", ""))
            return None

        before = value(_node_json(self.before, self.reverse.get(node, node)))
        theirs = value(_node_json(self.after, node))
        target = self.target(node, item)
        data = self.read(target)
        if not self.settle(item, value(data), before, theirs):
            return
        variables = [dict(v) for v in data.get("VARIABLE", []) if v.get("NAME") != name]
        if theirs is not None:
            mine = [v.get("NAME") for v in data.get("VARIABLE", [])]
            index = mine.index(name) if name in mine else len(variables)
            variables.insert(index, {"NAME": name, "VALUE": theirs})
        if variables:
            data["VARIABLE"] = variables
        else:
            data.pop("VARIABLE", None)
        self.write(target, data)
        self.taken.add(node)

    def _group(self, item: str, node: str, tag: str) -> None:
        before_node = _node_json(self.before, self.reverse.get(node, node))
        after_node = _node_json(self.after, node)
        target = self.target(node, item)
        data = self.read(target)
        if any("children" in (d or {}) for d in (before_node, after_node, data)):
            raise InvalidChange(
                f"{item}: the children of {node} keep their own order: take the whole job"
            )
        before, theirs = (before_node or {}).get(tag), (after_node or {}).get(tag)
        if self.settle(item, data.get(tag), before, theirs):
            if theirs is None:
                data.pop(tag, None)
            else:
                data[tag] = theirs
                self.bring_names(theirs)
            self.write(target, data)
            self.taken.add(node)

    def _rel(self, item: str, node: str, link: str) -> None:
        users = {i for i, d in self.after.jobs.items() if _links_of(d) & {link}}
        users |= {f"{f}/" for f, d in self.after.folders.items() if link in _links_of(d)}
        users |= {
            self.forward.get(i, i)
            for i, d in (*self.before.jobs.items(), *((f"{f}/", d) for f, d in
                                                        self.before.folders.items()))
            if link in _links_of(d)
        }  # fmt: skip
        if node not in users:
            raise InvalidChange(f"{item}: {node} has no condition {link}")
        for identity in sorted(users):
            before_node = _node_json(self.before, self.reverse.get(identity, identity))
            after_node = _node_json(self.after, identity)
            if _uses_docond(before_node, link) or _uses_docond(after_node, link):
                raise InvalidChange(
                    f"{item}: {identity} sets {link} in an ON block: take its ON group or the job"
                )
            try:
                target = self.target(identity, item)
            except InvalidChange:
                self.warnings.append(
                    f"{identity} is not in the checkout: its end of {link} stays out"
                )
                continue
            data = self.read(target)
            mine, before, theirs = (
                _refs(data, link),
                _refs(before_node, link),
                _refs(after_node, link),
            )
            if not self.settle(f"{item}", mine, before, theirs):
                continue
            for group in _CONDITIONS:
                kept = [e for e in data.get(group, []) if e.get(LINK_KEY) != link]
                ordered = (after_node or {}).get(group, [])
                for entry in theirs[group]:
                    index = ordered.index(entry)
                    kept.insert(min(index, len(kept)), entry)
                if kept:
                    data[group] = kept
                else:
                    data.pop(group, None)
            self.write(target, data)
            self.taken.add(identity)
        self.bring_names([{LINK_KEY: link}])

    def _job(self, item: str, identity: str) -> None:
        old = self.reverse.get(identity)
        after_job = self.after.jobs.get(identity)
        if after_job is None:  # removed by the other branch: listed under its old name
            old, after_job = identity, None
        before_job = self.before.jobs.get(old) if old else None
        if after_job is None and before_job is None:
            raise InvalidChange(f"{item}: neither side of the comparison has that job")
        if old and old != identity and after_job is not None:  # renamed or moved
            self._remove_job(item, old, before_job)
            self._add_job(item, identity, None, after_job)
            return
        if after_job is None:
            self._remove_job(item, identity, before_job)
        else:
            self._add_job(item, identity, before_job, after_job)

    def _remove_job(self, item: str, identity: str, before: Mapping[str, Any] | None) -> None:
        if not self.path(identity).is_file():
            return
        if not self.settle(item, self.read(identity), before, None):
            return
        folder, _, job = identity.partition("/")
        self.path(identity).unlink()
        folder_json = dict(read_json(self.box.folder_file(folder)))
        folder_json[JOBS_KEY] = [j for j in folder_json.get(JOBS_KEY, []) if j != job]
        write_json(self.box.folder_file(folder), folder_json)
        meta_file = self.box.folder_meta_file(folder)
        if meta_file.is_file():
            meta = dict(read_json(meta_file))
            meta[JOBS_KEY] = {j: v for j, v in meta.get(JOBS_KEY, {}).items() if j != job}
            originals = {j: n for j, n in meta.get(ORIGINALS_KEY, {}).items() if j != job}
            if originals:
                meta[ORIGINALS_KEY] = originals
            else:
                meta.pop(ORIGINALS_KEY, None)
            write_json(meta_file, meta)

    def _add_job(
        self, item: str, identity: str, before: Mapping[str, Any] | None, after: dict[str, Any]
    ) -> None:
        folder, _, job = identity.partition("/")
        if not self.box.folder_file(folder).is_file():
            raise InvalidChange(f"{item}: folder {folder} is not in the checkout: take it whole")
        mine = self.read(identity) if self.path(identity).is_file() else None
        if not self.settle(item, mine, before, after):
            if mine == after:  # the same job: its JOBNAME in Control-M may still differ
                self._jobname(item, identity)
            return
        self.write(identity, after)
        folder_json = dict(read_json(self.box.folder_file(folder)))
        ids = [str(j) for j in folder_json.get(JOBS_KEY, [])]
        if job not in ids:
            order = [str(j) for j in self.after.folders.get(folder, {}).get(JOBS_KEY, [])]
            earlier = [j for j in order[: order.index(job)] if j in ids] if job in order else []
            ids.insert(ids.index(earlier[-1]) + 1 if earlier else len(ids), job)
            folder_json[JOBS_KEY] = ids
            write_json(self.box.folder_file(folder), folder_json)
        head_meta = self.head_root / "meta" / "folders" / f"{folder}.json"
        meta_file = self.box.folder_meta_file(folder)
        if head_meta.is_file() and meta_file.is_file():
            theirs = read_json(head_meta).get(JOBS_KEY, {}).get(job)
            meta = dict(read_json(meta_file))
            jobs = dict(meta.get(JOBS_KEY, {}))
            if theirs is not None:
                jobs[job] = theirs
            meta[JOBS_KEY] = {j: jobs[j] for j in ids if j in jobs}
            write_json(meta_file, meta)
        if meta_file.is_file():  # with the JOBNAME Control-M has for it there
            self._set_original(folder, job, self.after.originals.get(identity, job))
        self.bring_names(after)
        self.taken.add(identity)

    def _folder(self, item: str, folder: str) -> None:
        identity = f"{folder}/"
        old = self.reverse.get(identity, identity)[:-1]
        if folder not in self.after.folders:  # removed by the other branch
            old = folder
            if folder not in self.before.folders:
                raise InvalidChange(f"{item}: neither side of the comparison has that folder")
        mine = _folder_files(self.box.root, old)
        before = _folder_files(self.base_root, old)
        theirs = _folder_files(self.head_root, folder) if folder in self.after.folders else {}
        if old != folder:
            mine = {**mine, **_folder_files(self.box.root, folder)}
        if not self.settle(item, mine, before, theirs):
            return
        for name in {old, folder}:
            remove_tree(self.box.folder_dir(name), ignore_errors=True)
            self.box.folder_meta_file(name).unlink(missing_ok=True)
        for relative, text in theirs.items():
            path = self.box.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        meta_path = self.box.export_meta_file
        if meta_path.is_file():
            meta = dict(read_json(meta_path))
            order = [f for f in meta.get(_ORDER_KEY, []) if f not in (old, folder)]
            if theirs:
                order.insert(_place(order, self.after.order, folder), folder)
            meta[_ORDER_KEY] = order
            write_json(meta_path, meta)
        if theirs:
            self.bring_names(self.after.folders[folder])
            for job in self.after.folders[folder].get(JOBS_KEY, []):
                self.bring_names(self.after.jobs.get(f"{folder}/{job}"))
            self.taken.add(identity)

    def _differs(self, folder: str) -> bool:
        """Whether a folder of the other branch holds anything the checkout's does not."""
        old = self.reverse.get(f"{folder}/", f"{folder}/")[:-1]
        theirs = self.after.folders[folder]
        if self.before.folders.get(old) != theirs:
            return True
        return any(
            self.before.jobs.get(f"{old}/{job}") != self.after.jobs.get(f"{folder}/{job}")
            for job in theirs.get(JOBS_KEY, [])
        )

    def _subapp(self, item: str, name: str) -> None:
        theirs = _subapp_folders(self.after, name)
        if not theirs:
            raise InvalidChange(f"{item}: the other branch has no sub-application {name}")
        for folder in theirs:
            if not self._differs(folder):
                continue
            part = f"folder:{folder}"
            if item in self.theirs:
                self.theirs.add(part)
            self._folder(part, folder)
        for folder in _subapp_folders(self.before, name):
            if self.forward.get(f"{folder}/", f"{folder}/")[:-1] not in self.after.folders:
                self.warnings.append(
                    f"folder {folder} of {name} is not in the other branch: it stays as it "
                    f"is (folder:{folder} removes it)"
                )

    def _link(self, item: str, link: str) -> None:
        theirs = self.other_names.get(link) or self.after.names.get(link)
        if theirs is None:
            raise InvalidChange(f"{item}: the other branch has no condition {link}")
        if self.settle(item, read_names(self.box).get(link), self.before.names.get(link), theirs):
            self.names[link] = theirs

    def _const(self, item: str, env: str, name: str) -> None:
        head = load_repo(self.head_root)
        if env not in self.box.config.environments:
            raise InvalidChange(f"{item}: no environment {env} in the checkout")
        if name not in self.box.config.constants:
            if name not in head.config.constants:
                raise InvalidChange(f"{item}: the other branch has no constant {name}")
            self._define(name, head)
            return
        before = self.before.constants.get(env, {}).get(name)
        theirs = self.after.constants.get(env, {}).get(name)
        config = self.box.load_env(env)
        if self.settle(item, config.constants.get(name), before, theirs):
            constants = {**config.constants, name: theirs}
            write_json(self.box.env_file(env), replace(config, constants=constants).to_json())

    def _define(self, name: str, head: ChainRepo) -> None:
        """A constant of the other branch, with its value in every environment there."""
        config = self.box.config
        self.box = self.box.save_config(
            replace(config, constants={**config.constants, name: head.config.constants[name]})
        )
        for env in self.box.config.environments:
            values = self.after.constants.get(env, {})
            env_config = self.box.load_env(env)
            constants = {**env_config.constants, name: values.get(name)}
            write_json(self.box.env_file(env), replace(env_config, constants=constants).to_json())

    def _exception(self, item: str, env: str, node: str) -> None:
        if env not in self.box.config.environments:
            raise InvalidChange(f"{item}: no environment {env} in the checkout")
        before = load_overrides(load_repo(self.base_root), env).get(self.reverse.get(node, node))
        theirs = load_overrides(load_repo(self.head_root), env).get(node)
        mine_all = dict(load_overrides(self.box, env))
        target = node if self.path(node).is_file() else self.reverse.get(node, node)
        if self.settle(item, _plain(mine_all.get(target)), _plain(before), _plain(theirs)):
            if theirs is None:
                mine_all.pop(target, None)
            else:
                mine_all[target] = theirs
            write_overrides(self.box, env, mine_all)

    # ------------------------------------------------------------ after the items

    def constants(self) -> None:
        """Constants the taken nodes use that the checkout does not define."""
        head = load_repo(self.head_root)
        used: set[str] = set()
        for identity in self.taken:
            if self.path(identity).is_file():
                used |= set(PLACEHOLDER.findall(read_text(self.path(identity))))
        for name in sorted(used - set(self.box.config.constants)):
            if name in head.config.constants:
                self._define(name, head)
                self.warnings.append(f"constant {name} comes along: the taken content uses it")

    def dangling(self) -> None:
        """Conditions of the taken content that nobody emits or waits for in the checkout."""
        ends: dict[str, set[str]] = {}
        for condition in collect_conditions(self.box):
            role = "in" if condition.kind == "in" else "out" if condition.kind in (
                "out+", "do+") else None  # fmt: skip
            if role and condition.id in self.links:
                ends.setdefault(condition.id, set()).add(role)
        for link in sorted(self.links):
            roles = ends.get(link, set())
            name = self.names.get(link) or read_names(self.box).get(link, link)
            if roles == {"in"}:
                self.warnings.append(f"{name}: a job waits for it but no job emits it here")
            elif roles == {"out"}:
                self.warnings.append(f"{name}: a job emits it but no job waits for it here")


def shown(value: Any) -> str:
    """A value of an item, ``(none)`` when absent."""
    return "(none)" if value is None else str(value)


def conflict_line(conflict: Mapping[str, Any]) -> str:
    """One conflict of a :class:`TakeConflict` in a line: the item and its three values."""
    return (
        f"conflict {conflict['item']}: mine {shown(conflict['mine'])}, before "
        f"{shown(conflict['before'])}, theirs {shown(conflict['theirs'])}"
    )


def _subapp_items(result: Comparison) -> list[tuple[str, str]]:
    """One item per sub-application that has folders to take (added or changed in any way)."""
    folders: dict[str, set[str]] = {}
    for node in (*result.folders, *result.jobs):
        if node.after is None or (node.kind == "folder" and node.change == "removed"):
            continue
        name = node.after.get(_SUBAPP)
        if isinstance(name, str) and name:
            folders.setdefault(name, set()).add(node.node.partition("/")[0])
    return [
        (f"subapp:{name}", f"{len(found)} folder{'s' if len(found) != 1 else ''} that differ")
        for name, found in folders.items()
    ]


def items_of(result: Comparison) -> tuple[tuple[str, str], ...]:
    """Every item of a comparison that can be taken, with a short description."""
    items: list[tuple[str, str]] = _subapp_items(result)
    for node in (*result.folders, *result.jobs):
        whole = f"folder:{node.node[:-1]}" if node.kind == "folder" else f"job:{node.node}"
        items.append((whole, f"the whole {node.kind}, {node.change}"))
        if node.change in ("added", "removed"):  # its parts come with it
            continue
        items += [
            (f"attr:{node.node}@{a.name}", f"{shown(a.before)} -> {shown(a.after)}")
            for a in node.attributes
        ]
        items += [
            (f"var:{node.node}@{v.name}", f"{shown(v.before)} -> {shown(v.after)}")
            for v in node.variables
        ]
        items += [
            (f"rel:{node.node}@{r.link}", f"{r.direction} {r.name}, {r.change}")
            for r in node.relations
        ]
        items += [(f"group:{node.node}@{tag}", f"{tag} changed") for tag in node.groups]
    items += [
        (f"link:{lk.link}", f"condition {lk.before} -> {lk.after}")
        for lk in result.links
        if lk.change == "renamed"
    ]
    if result.translation is not None:  # called otherwise there: each may keep its own name
        items += [
            (
                f"link:{name.link}",
                f"condition {name.base} -> {name.head}: the name {result.translation.source} uses",
            )
            for name in result.translation.names
        ]
    items += [
        (f"const:{c.env}@{c.name}", f"{shown(c.before)} -> {shown(c.after)}")
        for c in result.constants
    ]
    items += [(f"exception:{e.env}@{e.node}", "exceptions changed") for e in result.exceptions]
    return tuple(items)


def _plain(override: Override | None) -> dict[str, Any] | None:
    if override is None:
        return None
    return {"set": dict(override.attributes), "variables": dict(override.variables)}


@dataclass(frozen=True)
class Takeable:
    """What one side has that the other can take: the list ``take`` accepts items from."""

    into: str  # the branch the items arrive in
    source: str  # the ref they come from
    environments: tuple[str, str] | None  # (of ``into``, of ``source``) when both are one's
    items: tuple[tuple[str, str], ...]  # (id, what it is)

    def to_json(self) -> dict[str, Any]:
        return {
            "into": self.into,
            "from": self.source,
            "environments": None if self.environments is None else list(self.environments),
            "items": [{"id": item, "label": label} for item, label in self.items],
        }


def takeable(
    root: Path,
    base: str,
    head: str,
    *,
    use_merge_base: bool = True,
    commits: Sequence[str] | None = None,
    prefer: Sequence[str] = (),
) -> Takeable:
    """The items ``head`` has that ``base`` can take, from the smallest to the largest. The
    default base (``HEAD``) is named by the branch checked out."""
    result = compare(
        root, base, head, use_merge_base=use_merge_base, commits=commits, prefer=prefer
    )
    into = result.base.name
    if into == "HEAD":
        into = current_branch(root) or into
    return Takeable(into, result.head.name, result.environments, items_of(result))


def _check_destination(root: Path, base: str) -> None:
    head_sha = resolve(root, "HEAD").sha
    if base == "WORKTREE" or resolve(root, base).sha != head_sha:
        raise InvalidChange(
            "changes are taken into the checked-out branch: compare it (as base) with the "
            "branch to take from (as head)"
        )


def take_into(
    box: ChainRepo, sides: Sides, items: Sequence[str], theirs: Iterable[str] = ()
) -> _Take:
    """The ``items`` of the two opened sides applied to the files of ``box``; conflicts raise.
    The names of the conditions that come along are in the result, not written yet."""
    before, after = _load(sides.base_root), _load(sides.head_root)
    folders = _match_folders(before, after)
    jobs, _ = _match_jobs(before, after, folders)
    forward = {f"{old}/": f"{new}/" for old, new in folders.items()} | jobs
    reverse = {new: old for old, new in forward.items()}
    work = _Take(
        box, before, after, sides.base_root, sides.head_root, reverse, forward, set(theirs)
    )
    if sides.translation is not None:
        work.other_names = {name.link: name.head for name in sides.translation.names}
    for item in dict.fromkeys(items):
        work.take(item)
    if work.conflicts:
        shown = ", ".join(c.item for c in work.conflicts[:3])
        raise TakeConflict(
            f"{len(work.conflicts)} item(s) changed in the checkout too: {shown}; "
            "keep yours (leave them out) or take theirs",
            tuple(c.to_json() for c in work.conflicts),
        )
    work.constants()
    work.dangling()
    if sides.translation is not None:
        from controlm_chain_admin.core.crossenv import kept_unsure  # it imports the comparison

        work.warnings.extend(kept_unsure(sides.translation, box.root))
    return work


def take(
    repo: ChainRepo,
    base: str,
    head: str,
    items: Sequence[str],
    *,
    theirs: Iterable[str] = (),
    use_merge_base: bool = True,
    commits: Sequence[str] | None = None,
    prefer: Sequence[str] = (),
) -> ChangeSet:
    """The ``items`` of the comparison of ``base`` (the checked-out branch) with ``head``,
    taken into the working tree as one change set to preview and apply. Between two
    environments, ``prefer`` names the entries of the map that win where it gives several
    answers for a value."""
    from controlm_chain_admin.core.refactor import _finish, _sandbox, _tracked

    repo = load_repo(repo.root)
    if not items:
        raise InvalidChange("nothing to take")
    _check_destination(repo.root, base)
    with open_sides(
        repo.root, base, head, use_merge_base=use_merge_base, commits=commits, prefer=prefer
    ) as sides:
        original = _tracked(repo.root)
        with _sandbox(original) as box:
            work = take_into(box, sides, items, theirs)
            count = len(dict.fromkeys(items))
            listed = ", ".join(list(dict.fromkeys(items))[:3]) + ("..." if count > 3 else "")
            summary = f"take {count} change{'s' if count != 1 else ''} from {head}: {listed}"
            return _finish(original, work.box, summary, work.warnings, work.names)
