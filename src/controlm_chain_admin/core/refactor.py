"""Refactorings computed as change sets, previewed, then applied atomically.

Each refactoring runs on a *sandbox*: a temporary copy of the repository's tracked files
(``chain.json``, ``meta/``, ``folders/`` without the derived ``index.json``). The refactoring edits
the sandbox with the ordinary file helpers, the links' ``links.json`` files are recomputed there,
and the change set is the difference between the two trees. Nothing touches the repository until
:func:`apply`, which first checks that every file is still what the preview saw.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import inspect
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.errors import (
    ChainError,
    ChangeConflict,
    DuplicateName,
    InvalidChange,
    ModelError,
    UnsafeName,
)
from controlm_chain_admin.core.jsonmodel import json_to_element
from controlm_chain_admin.core.links import (
    INDEX_FILE,
    LINK_KEY,
    Link,
    NodeRef,
    build_links,
    collect_conditions,
    folder_names,
    load_links,
    read_names,
    rebuild_links,
    write_names,
)
from controlm_chain_admin.core.ops import ORIGINALS_KEY, _check_safe
from controlm_chain_admin.core.overrides import (
    OVERRIDES_FILE,
    Override,
    load_overrides,
    write_overrides,
)
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json, write_json

#: Canonical child order measured on real Control-M exports; used to place a group that a
#: refactoring adds when the repository has never seen it under that parent.
DEFAULT_CHILD_ORDER: dict[str, tuple[str, ...]] = {
    "SMART_FOLDER": (
        "JOB", "VARIABLE", "CONTROL", "SHOUT", "INCOND", "OUTCOND", "RULE_BASED_CALENDAR", "ON",
    ),
    "JOB": (
        "VARIABLE", "SHOUT", "CONTROL", "INCOND", "QUANTITATIVE", "OUTCOND",
        "RULE_BASED_CALENDARS", "ON",
    ),
}  # fmt: skip

_TRACKED_DIRS = ("folders", "meta", "envs")
_TRACKED_FILES = ("chain.json",)


# ---------------------------------------------------------------- change sets


@dataclass(frozen=True)
class FileEdit:
    """One file of a change set; ``before``/``after`` is ``None`` for a created/deleted file."""

    path: str  # relative to the repository root, POSIX separators
    before: str | None
    after: str | None

    @property
    def kind(self) -> str:
        if self.before is None:
            return "create"
        if self.after is None:
            return "delete"
        return "modify"


@dataclass(frozen=True)
class ChangeSet:
    summary: str
    edits: tuple[FileEdit, ...]
    warnings: tuple[str, ...] = ()

    def diff(self) -> str:
        """Unified diff of every file of the change set."""
        chunks: list[str] = []
        for edit in self.edits:
            before = (edit.before or "").splitlines(keepends=True)
            after = (edit.after or "").splitlines(keepends=True)
            source = f"a/{edit.path}" if edit.before is not None else "/dev/null"
            target = f"b/{edit.path}" if edit.after is not None else "/dev/null"
            chunks.extend(difflib.unified_diff(before, after, fromfile=source, tofile=target, n=2))
        return "".join(chunks)

    def stat(self) -> str:
        return "".join(f"  {edit.kind:6}  {edit.path}\n" for edit in self.edits)

    def to_json(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "warnings": list(self.warnings),
            "files": [{"path": edit.path, "change": edit.kind} for edit in self.edits],
        }


@dataclass(frozen=True)
class ApplyResult:
    written: int
    deleted: int


#: Inside :func:`batch`, the sandbox every operation edits in place (no copy, no diff per step).
_IN_PLACE: ContextVar[Path | None] = ContextVar("ctmchain_in_place", default=None)


def _tracked(root: Path) -> dict[str, str]:
    if _IN_PLACE.get() == root:
        return {}  # in a batch: the diff is computed once, at the end
    files: dict[str, str] = {}
    for name in _TRACKED_FILES:
        path = root / name
        if path.is_file():
            files[name] = path.read_text(encoding="utf-8")
    for directory in _TRACKED_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.name != INDEX_FILE:
                files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return files


@contextmanager
def _sandbox(files: Mapping[str, str]) -> Iterator[ChainRepo]:
    in_place = _IN_PLACE.get()
    if in_place is not None:
        yield load_repo(in_place)
        return
    with tempfile.TemporaryDirectory(prefix="ctmchain-") as tmp:
        root = Path(tmp)
        for relative, text in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        yield load_repo(root)


def _finish(
    original: Mapping[str, str],
    box: ChainRepo,
    summary: str,
    warnings: Sequence[str],
    names: Mapping[str, str] | None = None,
) -> ChangeSet:
    """Recompute links.json in the sandbox and diff it against the original files."""
    if _IN_PLACE.get() is not None:  # a step of a batch: keep new names, diff at the end
        if names:
            resolved = {**read_names(box), **names}
            write_names(box, build_links(collect_conditions(box), resolved))
        return ChangeSet(summary, (), tuple(warnings))
    resolved = {**read_names(box), **(names or {})}
    write_names(box, build_links(collect_conditions(box), resolved))
    after = _tracked(box.root)
    edits = tuple(
        FileEdit(path, original.get(path), after.get(path))
        for path in sorted(set(original) | set(after))
        if original.get(path) != after.get(path)
    )
    return ChangeSet(summary, edits, tuple(warnings))


def apply(repo: ChainRepo, change: ChangeSet) -> ApplyResult:
    """Write a change set: all files or none, refusing if any file changed since the preview."""
    root = repo.root.resolve()
    targets: list[tuple[FileEdit, Path]] = []
    for edit in change.edits:
        path = (root / edit.path).resolve()
        if root not in path.parents:
            raise ModelError(f"change set path {edit.path!r} is outside the repository")
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != edit.before:
            raise ChangeConflict(
                f"{edit.path} changed since the preview; compute the change again"
            )
        targets.append((edit, path))
    staged: list[tuple[Path, Path]] = []
    try:
        for edit, path in targets:
            if edit.after is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".ctmchain-tmp")
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(edit.after)
            staged.append((temporary, path))
    except OSError:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        raise
    for temporary, path in staged:
        os.replace(temporary, path)
    deleted = 0
    for edit, path in targets:
        if edit.after is None:
            path.unlink()
            deleted += 1
    _prune(root / "folders")
    rebuild_links(load_repo(repo.root))
    return ApplyResult(written=len(staged), deleted=deleted)


def _prune(folders: Path) -> None:
    """Remove folder directories left without folder.json (and the derived files inside)."""
    if not folders.is_dir():
        return
    for directory in folders.iterdir():
        if directory.is_dir() and not (directory / "folder.json").exists():
            (directory / INDEX_FILE).unlink(missing_ok=True)
    for directory in sorted(folders.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


# ---------------------------------------------------------------- helpers


def rename_in_condition(name: str, old: str, new: str) -> str:
    """Replace ``old`` by ``new`` in the dash-separated parts of a condition name.

    A part matches when it equals ``old`` or ``old`` followed by an ``_OK`` suffix (any case),
    so ``A-B_OK``, ``A-TO-B`` and ``A-B_OK-U26`` are handled; ``A_B_OK`` is left alone.
    """
    parts: list[str] = []
    for part in name.split("-"):
        if part == old:
            parts.append(new)
        elif part.upper().endswith("_OK") and part[:-3] == old:
            parts.append(new + part[-3:])
        else:
            parts.append(part)
    return "-".join(parts)


#: A folder or job id as stored on disk: a safe file name, plus ``~n`` for a repeated JOBNAME.
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]*(?:~\d+)?")


def _safe_ref(node: str) -> NodeRef:
    """Parse ``FOLDER/JOB`` or ``FOLDER/``; names that could leave their directory are refused."""
    ref = NodeRef.parse(node)
    if not _SAFE_ID.fullmatch(ref.folder) or (
        ref.job is not None and not _SAFE_ID.fullmatch(ref.job)
    ):
        raise UnsafeName(f"invalid node {node!r} (use FOLDER/JOB or FOLDER/)")
    return ref


def _require_job(repo: ChainRepo, node: str) -> NodeRef:
    ref = _safe_ref(node)
    if ref.job is None or not repo.job_file(ref.folder, ref.job).is_file():
        raise ModelError(f"unknown job {node!r} (use FOLDER/JOB)")
    return ref


def _require_folder(repo: ChainRepo, folder: str) -> None:
    if not _SAFE_ID.fullmatch(folder):
        raise UnsafeName(f"invalid folder name {folder!r}")
    if not repo.folder_file(folder).is_file():
        raise ModelError(f"unknown folder {folder!r}")


def _name_warnings(repo: ChainRepo, name: str) -> list[str]:
    """Warn about names that will not behave as expected under the letter rule."""
    rule = repo.config.letter_rule
    if not rule.enabled:
        return []
    alternation = "|".join(re.escape(p) for p in rule.prefixes)
    if re.match(rf"^(?:{alternation})", name):
        return []
    if re.match(rf"^[A-Z](?:{alternation})", name):
        return [
            f"{name} looks like it carries an environment letter; names in the repository are "
            "environment-neutral (drop the letter, export adds it)"
        ]
    return [f"{name} has no prefix of the letter rule; it is exported as is in every environment"]


def _touching(links: Mapping[str, Link], ref: NodeRef) -> list[Link]:
    return [
        link
        for link in links.values()
        if ref in link.consumers
        or ref in link.all_producers
        or ref in link.deleters
        or any(node == ref for node, _ in link.docond_delete)
    ]


def _renamed_names(
    links: Sequence[Link],
    old: str,
    new: str,
    every: Mapping[str, Link],
    warnings: list[str],
) -> dict[str, str]:
    """New names of the ``links`` whose name embeds ``old``; never a name another link uses.

    Condition names are global in Control-M: a name already used elsewhere (``every``) would
    join two chains, so that link keeps its name and a warning says so.
    """
    result: dict[str, str] = {}
    for link in links:
        renamed = rename_in_condition(link.name, old, new)
        if renamed == link.name:
            continue
        used = _name_in_use(every, renamed, except_id=link.id)
        if used is None and renamed in result.values():
            used = next(i for i, name in result.items() if name == renamed)
        if used is not None:
            warnings.append(
                f"condition {link.name} keeps its name: {renamed} is already used by link {used}"
            )
            continue
        result[link.id] = renamed
    return result


def _rename_key(mapping: Mapping[str, Any], old: str, new: str) -> dict[str, Any]:
    return {(new if key == old else key): value for key, value in mapping.items()}


def _ensure_child_tag(box: ChainRepo, parent: str, tag: str) -> tuple[str, ...]:
    """The canonical child order of ``parent``, extended with ``tag`` if it was never seen."""
    config = box.config
    order = config.child_order.get(parent, ())
    if tag in order:
        return order
    default = DEFAULT_CHILD_ORDER.get(parent, ())
    position = len(order)
    if tag in default:
        later = default[default.index(tag) + 1 :]
        for index, known in enumerate(order):
            if known in later:
                position = index
                break
    extended = (*order[:position], tag, *order[position:])
    box.save_config(replace(config, child_order={**config.child_order, parent: extended}))
    return extended


def _with_groups(
    box: ChainRepo, parent: str, data: Mapping[str, Any], updates: Mapping[str, Any]
) -> dict[str, Any]:
    """``data`` with ``updates`` merged; attributes first, then groups in the canonical order."""
    if "children" in data:
        raise ModelError(f"this <{parent}> keeps an ordered child list; edit it by hand")
    merged = {**data, **updates}
    order: tuple[str, ...] = box.config.child_order.get(parent, ())
    for tag in updates:
        order = _ensure_child_tag(box, parent, tag)
    result = {key: value for key, value in merged.items() if isinstance(value, str)}
    groups = {key: value for key, value in merged.items() if not isinstance(value, str)}
    for tag in order:
        if tag in groups:
            result[tag] = groups.pop(tag)
    result.update(groups)
    return result


def _load_meta(box: ChainRepo, folder: str) -> dict[str, Any]:
    path = box.folder_meta_file(folder)
    return dict(read_json(path)) if path.exists() else {"attrs": {}, "jobs": {}}


# ---------------------------------------------------------------- refactorings


def rename_job(
    repo: ChainRepo,
    node: str,
    new_name: str,
    *,
    update_names: bool = True,
    with_memname: bool = False,
) -> ChangeSet:
    """Rename a job; condition names that embed its name follow unless ``update_names`` is off."""
    repo = load_repo(repo.root)
    ref = _require_job(repo, node)
    assert ref.job is not None
    _check_safe(new_name, "job")
    if repo.job_file(ref.folder, new_name).exists():
        raise DuplicateName(f"job {new_name} already exists in folder {ref.folder}")
    warnings = _name_warnings(repo, new_name)
    old_name = ref.name
    every = load_links(repo)
    names = (
        _renamed_names(_touching(every, ref), old_name, new_name, every, warnings)
        if update_names
        else {}
    )
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        data = dict(read_json(box.job_file(ref.folder, ref.job)))
        data["JOBNAME"] = new_name
        if data.get("MEMNAME") == old_name:
            if with_memname:
                data["MEMNAME"] = new_name
            else:
                warnings.append(f"MEMNAME stays {old_name} (use --with-memname to rename it too)")
        write_json(box.job_file(ref.folder, new_name), data)
        box.job_file(ref.folder, ref.job).unlink()
        folder = dict(read_json(box.folder_file(ref.folder)))
        folder["jobs"] = [new_name if job == ref.job else job for job in folder.get("jobs", [])]
        write_json(box.folder_file(ref.folder), folder)
        meta = _load_meta(box, ref.folder)
        meta["jobs"] = _rename_key(meta.get("jobs", {}), ref.job, new_name)
        originals = dict(meta.get(ORIGINALS_KEY, {}))
        originals.pop(ref.job, None)  # an explicit rename replaces the deduplicated name
        if originals:
            meta[ORIGINALS_KEY] = originals
        else:
            meta.pop(ORIGINALS_KEY, None)
        write_json(box.folder_meta_file(ref.folder), meta)
        summary = f"rename job {ref} -> {ref.folder}/{new_name}"
        if names:
            summary += f"; {len(names)} condition name(s) updated"
        return _finish(original, box, summary, warnings, names)


def rename_folder(
    repo: ChainRepo, folder: str, new_name: str, *, update_names: bool = True
) -> ChangeSet:
    """Rename a folder: directory, FOLDER_NAME, PARENT_FOLDER of its jobs, metadata, order."""
    repo = load_repo(repo.root)
    _require_folder(repo, folder)
    _check_safe(new_name, "folder")
    if repo.folder_file(new_name).exists():
        raise DuplicateName(f"folder {new_name} already exists")
    warnings = _name_warnings(repo, new_name)
    ref = NodeRef(folder)
    every = load_links(repo)
    names = (
        _renamed_names(_touching(every, ref), folder, new_name, every, warnings)
        if update_names
        else {}
    )
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        shutil.move(box.folder_dir(folder), box.folder_dir(new_name))
        data = dict(read_json(box.folder_file(new_name)))
        for key in ("FOLDER_NAME", "JOBNAME", "PARENT_FOLDER"):
            if data.get(key) == folder:
                data[key] = new_name
        write_json(box.folder_file(new_name), data)
        for job_id in (str(j) for j in data.get("jobs", [])):
            job = dict(read_json(box.job_file(new_name, job_id)))
            if job.get("PARENT_FOLDER") == folder:
                job["PARENT_FOLDER"] = new_name
                write_json(box.job_file(new_name, job_id), job)
        if box.folder_meta_file(folder).exists():
            shutil.move(box.folder_meta_file(folder), box.folder_meta_file(new_name))
        if box.export_meta_file.exists():
            export_meta = dict(read_json(box.export_meta_file))
            export_meta["folder_order"] = [
                new_name if name == folder else name
                for name in export_meta.get("folder_order", [])
            ]
            write_json(box.export_meta_file, export_meta)
        summary = f"rename folder {folder} -> {new_name}"
        if names:
            summary += f"; {len(names)} condition name(s) updated"
        return _finish(original, box, summary, warnings, names)


def rename_subapp(repo: ChainRepo, old: str, new: str, *, folder: str | None = None) -> ChangeSet:
    """Rename a SUB_APPLICATION on the folders and jobs that carry it (one folder or all)."""
    repo = load_repo(repo.root)
    if folder is not None:
        _require_folder(repo, folder)
    folders = [folder] if folder is not None else folder_names(repo)
    warnings = _name_warnings(repo, new)
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        count = 0
        for name in folders:
            data = dict(read_json(box.folder_file(name)))
            if data.get("SUB_APPLICATION") == old:
                data["SUB_APPLICATION"] = new
                write_json(box.folder_file(name), data)
                count += 1
            for job_id in (str(j) for j in data.get("jobs", [])):
                job = dict(read_json(box.job_file(name, job_id)))
                if job.get("SUB_APPLICATION") == old:
                    job["SUB_APPLICATION"] = new
                    write_json(box.job_file(name, job_id), job)
                    count += 1
        scope = f" in folder {folder}" if folder else ""
        summary = f"rename sub-application {old} -> {new}{scope}: {count} node(s)"
        return _finish(original, box, summary, warnings)


def move_job(repo: ChainRepo, node: str, target: str) -> ChangeSet:
    """Move a job to another folder; its conditions and links travel with it."""
    repo = load_repo(repo.root)
    ref = _require_job(repo, node)
    assert ref.job is not None
    _require_folder(repo, target)
    if target == ref.folder:
        raise ModelError(f"job {ref} is already in folder {target}")
    if repo.job_file(target, ref.job).exists():
        raise DuplicateName(f"folder {target} already has a job {ref.job}")
    warnings: list[str] = []
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        job = dict(read_json(box.job_file(ref.folder, ref.job)))
        if job.get("PARENT_FOLDER") == ref.folder:
            job["PARENT_FOLDER"] = target
        target_folder = dict(read_json(box.folder_file(target)))
        if job.get("SUB_APPLICATION") != target_folder.get("SUB_APPLICATION"):
            warnings.append(
                f"SUB_APPLICATION {job.get('SUB_APPLICATION')} differs from the target folder's "
                f"{target_folder.get('SUB_APPLICATION')}; use rename-subapp if needed"
            )
        write_json(box.job_file(target, ref.job), job)
        box.job_file(ref.folder, ref.job).unlink()
        source_folder = dict(read_json(box.folder_file(ref.folder)))
        source_folder["jobs"] = [j for j in source_folder.get("jobs", []) if j != ref.job]
        write_json(box.folder_file(ref.folder), source_folder)
        target_folder["jobs"] = [*target_folder.get("jobs", []), ref.job]
        write_json(box.folder_file(target), target_folder)
        source_meta, target_meta = _load_meta(box, ref.folder), _load_meta(box, target)
        jobs_meta = dict(source_meta.get("jobs", {}))
        target_meta["jobs"] = {**target_meta.get("jobs", {}), ref.job: jobs_meta.pop(ref.job, {})}
        source_meta["jobs"] = jobs_meta
        source_originals = dict(source_meta.get(ORIGINALS_KEY, {}))
        if ref.job in source_originals:
            moved = source_originals.pop(ref.job)
            target_meta[ORIGINALS_KEY] = {**target_meta.get(ORIGINALS_KEY, {}), ref.job: moved}
            if source_originals:
                source_meta[ORIGINALS_KEY] = source_originals
            else:
                source_meta.pop(ORIGINALS_KEY, None)
        write_json(box.folder_meta_file(ref.folder), source_meta)
        write_json(box.folder_meta_file(target), target_meta)
        summary = f"move job {ref} -> {target}/{ref.job}"
        return _finish(original, box, summary, warnings)


def _clone_without_conditions(template: Mapping[str, Any]) -> dict[str, Any]:
    """A job template without its own conditions (INCOND, OUTCOND, DOCOND in ON blocks)."""
    job = copy.deepcopy({k: v for k, v in template.items() if k not in ("INCOND", "OUTCOND")})
    blocks = []
    for block in job.pop("ON", []):
        children = [c for c in block.get("children", []) if c.get("tag") != "DOCOND"]
        if children:
            blocks.append({**block, "children": children})
    if blocks:
        job["ON"] = blocks
    return job


def insert_job(
    repo: ChainRepo,
    node: str,
    *,
    after: str,
    before: str,
    like: str | None = None,
    link: str | None = None,
) -> ChangeSet:
    """Insert a new job between two linked jobs: ``after -> new -> before``.

    The existing link keeps its id and now ends at the new job (its name follows when it embeds
    the downstream job); a new link ``<NEW>-<BEFORE>_OK`` takes the new job to ``before``, which
    now waits for and cleans up that link. ``like`` clones another job's attributes.
    """
    repo = load_repo(repo.root)
    new = _safe_ref(node)
    if new.job is None:
        raise ModelError(f"insert-job needs FOLDER/JOB, got {node!r}")
    _require_folder(repo, new.folder)
    _check_safe(new.job, "job")
    if repo.job_file(new.folder, new.job).exists():
        raise DuplicateName(f"job {new.job} already exists in folder {new.folder}")
    upstream, downstream = _require_job(repo, after), _require_job(repo, before)
    assert downstream.job is not None
    links = load_links(repo)
    candidates = [
        candidate
        for candidate in links.values()
        if upstream in candidate.all_producers
        and downstream in candidate.consumers
        and link in (None, candidate.id, candidate.name)
    ]
    if not candidates:
        raise ModelError(f"no link from {after} to {before}")
    if len(candidates) > 1:
        ids = ", ".join(c.id for c in candidates)
        raise ModelError(f"several links from {after} to {before} ({ids}); choose one with --link")
    existing = candidates[0]
    base_id = f"{new.job}-{downstream.name}_OK"
    new_id, suffix = base_id, 2
    while new_id in links or _name_in_use(links, new_id):
        new_id, suffix = f"{base_id}_{suffix}", suffix + 1
    warnings = [*_name_warnings(repo, new.job), "the new job has no JOBISN; Control-M assigns one"]
    names = _renamed_names([existing], downstream.name, new.job, links, warnings)
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        waiting = dict(read_json(box.job_file(downstream.folder, downstream.job)))
        entry = next(e for e in waiting.get("INCOND", []) if e.get(LINK_KEY) == existing.id)
        odate, and_or = entry.get("ODATE", "ODAT"), entry.get("AND_OR", "A")
        entry[LINK_KEY] = new_id
        for cleanup in waiting.get("OUTCOND", []):
            if cleanup.get(LINK_KEY) == existing.id and cleanup.get("SIGN") == "-":
                cleanup[LINK_KEY] = new_id
        write_json(box.job_file(downstream.folder, downstream.job), waiting)

        folder = dict(read_json(box.folder_file(new.folder)))
        if like is not None:
            template_ref = _require_job(box, like)
            assert template_ref.job is not None
            template = read_json(box.job_file(template_ref.folder, template_ref.job))
            job = _clone_without_conditions(template)
            if template.get("MEMNAME") == template.get("JOBNAME"):
                job["MEMNAME"] = new.job
            job["JOBNAME"] = new.job
        else:
            job = {
                "APPLICATION": str(folder.get("APPLICATION", "")),
                "SUB_APPLICATION": str(folder.get("SUB_APPLICATION", "")),
                "MEMNAME": new.job,
                "JOBNAME": new.job,
                "DESCRIPTION": f"inserted between {upstream.name} and {downstream.name}",
                "TASKTYPE": "Dummy",
            }
        job["PARENT_FOLDER"] = new.folder
        conditions = {
            "INCOND": [{LINK_KEY: existing.id, "ODATE": odate, "AND_OR": and_or}],
            "OUTCOND": [
                {LINK_KEY: existing.id, "ODATE": odate, "SIGN": "-"},
                {LINK_KEY: new_id, "ODATE": odate, "SIGN": "+"},
            ],
        }
        write_json(box.job_file(new.folder, new.job), _with_groups(box, "JOB", job, conditions))

        jobs = [str(j) for j in folder.get("jobs", [])]
        if upstream.folder == new.folder and upstream.job in jobs:
            jobs.insert(jobs.index(upstream.job) + 1, new.job)
        elif downstream.folder == new.folder and downstream.job in jobs:
            jobs.insert(jobs.index(downstream.job), new.job)
        else:
            jobs.append(new.job)
        folder["jobs"] = jobs
        write_json(box.folder_file(new.folder), folder)
        meta = _load_meta(box, new.folder)
        meta["jobs"] = {**meta.get("jobs", {}), new.job: {}}
        write_json(box.folder_meta_file(new.folder), meta)
        summary = f"insert job {new} between {upstream} and {downstream} (new link {new_id})"
        return _finish(original, box, summary, warnings, names)


def extract_variable(
    repo: ChainRepo, target: str, literal: str, variable: str, *, attribute: str = "CMDLINE"
) -> ChangeSet:
    """Move a literal out of an attribute into a job variable (one job or a whole folder)."""
    if not variable.startswith("%%"):
        raise ModelError(f"Control-M variable names start with %%, got {variable!r}")
    repo = load_repo(repo.root)
    ref = _safe_ref(target)
    _require_folder(repo, ref.folder)
    if ref.job is not None:
        _require_job(repo, target)
        job_ids = [ref.job]
    else:
        job_ids = [str(j) for j in read_json(repo.folder_file(ref.folder)).get("jobs", [])]
    hits = [
        job_id
        for job_id in job_ids
        if literal in str(read_json(repo.job_file(ref.folder, job_id)).get(attribute, ""))
    ]
    if not hits:
        raise ModelError(f"{literal!r} not found in {attribute} of {target}")
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        for job_id in hits:
            data = dict(read_json(box.job_file(ref.folder, job_id)))
            data[attribute] = str(data[attribute]).replace(literal, variable)
            variables = [dict(v) for v in data.get("VARIABLE", [])]
            same = next((v for v in variables if v.get("NAME") == variable), None)
            if same is not None and same.get("VALUE") != literal:
                raise ModelError(
                    f"{ref.folder}/{job_id} already defines {variable} with another value"
                )
            if same is None:
                variables.append({"NAME": variable, "VALUE": literal})
            updated = _with_groups(box, "JOB", data, {"VARIABLE": variables})
            write_json(box.job_file(ref.folder, job_id), updated)
        summary = f"extract {literal!r} from {attribute} into {variable} in {len(hits)} job(s)"
        return _finish(original, box, summary, [])


# ---------------------------------------------------------------- environments

_CONSTANT_NAME = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+")


def set_exception(
    repo: ChainRepo,
    env: str,
    node: str,
    attributes: Mapping[str, str | None] | None = None,
    variables: Mapping[str, str] | None = None,
    drop: Sequence[str] = (),
) -> ChangeSet:
    """Set (or ``drop``) what one environment uses for one job or folder instead of the base.

    An attribute set to ``None`` is left out of that environment's export.
    """
    repo = load_repo(repo.root)
    repo.load_env(env)  # an unknown environment fails first
    ref = _require_node(repo, node)
    attributes, variables = dict(attributes or {}), dict(variables or {})
    if not attributes and not variables and not drop:
        raise InvalidChange("nothing to set or drop")
    names = set(repo.config.letter_rule.attributes) | {"FOLDER_NAME", "JOBNAME", "PARENT_FOLDER"}
    for attribute in attributes:
        if not _ATTRIBUTE_NAME.fullmatch(attribute):
            raise InvalidChange(f"invalid attribute name {attribute!r}")
        if attribute in names:
            raise InvalidChange(
                f"{attribute} is a name: it differs per environment by the letter only"
            )
    for variable in variables:
        if not variable.startswith("%%"):
            raise InvalidChange(f"Control-M variable names start with %%, got {variable!r}")
    key = str(ref) if ref.job is not None else f"{ref.folder}/"
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        overrides = load_overrides(box, env)
        current = overrides.get(key, Override())
        merged = Override(
            {k: v for k, v in {**current.attributes, **attributes}.items() if k not in drop},
            {k: v for k, v in {**current.variables, **variables}.items() if k not in drop},
        )
        overrides[key] = merged
        write_overrides(box, env, overrides)
        parts = [f"{k}={v if v is not None else '(left out)'}" for k, v in attributes.items()]
        parts += [f"{k}={v}" for k, v in variables.items()]
        parts += [f"drop {name}" for name in drop]
        return _finish(original, box, f"exception for {env} on {key}: {', '.join(parts)}", [])


def rename_constant(repo: ChainRepo, old: str, new: str) -> ChangeSet:
    """Rename a constant everywhere: placeholders, chain.json, environment values, exceptions."""
    repo = load_repo(repo.root)
    if not _CONSTANT_NAME.fullmatch(new):
        raise InvalidChange(f"invalid constant name {new!r}: use lower-case group.name")
    if old not in repo.config.constants:
        raise InvalidChange(f"unknown constant {old!r}")
    if new in repo.config.constants:
        raise InvalidChange(f"constant {new!r} already exists")
    before, after = "@{" + old + "}", "@{" + new + "}"
    original = _tracked(repo.root)
    uses = 0
    with _sandbox(original) as box:
        targets = [
            p for p in sorted((box.root / "folders").rglob("*.json")) if p.name != INDEX_FILE
        ]
        targets += sorted((box.root / "envs").glob(f"*/{OVERRIDES_FILE}"))
        for path in targets:
            text = path.read_text(encoding="utf-8")
            if before in text:
                uses += text.count(before)
                with path.open("w", encoding="utf-8", newline="\n") as handle:
                    handle.write(text.replace(before, after))
        config = box.config
        constants = {(new if k == old else k): v for k, v in config.constants.items()}
        box = box.save_config(replace(config, constants=constants))
        for env in box.config.environments:
            env_config = box.load_env(env)
            values = {(new if k == old else k): v for k, v in env_config.constants.items()}
            write_json(box.env_file(env), replace(env_config, constants=values).to_json())
        return _finish(original, box, f"rename constant {old} -> {new} ({uses} uses)", [])


# ---------------------------------------------------------------- editing operations

_ATTRIBUTE_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
_RENAMED_BY = {
    "JOBNAME": "rename-job",
    "FOLDER_NAME": "rename-folder",
    "PARENT_FOLDER": "move-job",
}
_AND_OR = ("A", "O")


def fingerprint(change: ChangeSet) -> str:
    """Identity of a change set's content; apply checks it to refuse stale previews."""
    payload = json.dumps([[e.path, e.before, e.after] for e in change.edits], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_node(repo: ChainRepo, node: str) -> NodeRef:
    ref = _safe_ref(node)
    _require_folder(repo, ref.folder)
    if ref.job is not None and not repo.job_file(ref.folder, ref.job).is_file():
        raise ModelError(f"unknown job {node!r}")
    return ref


def _node_file(repo: ChainRepo, ref: NodeRef) -> Path:
    return repo.folder_file(ref.folder) if ref.job is None else repo.job_file(ref.folder, ref.job)


def _node_tag(ref: NodeRef, data: Mapping[str, Any]) -> str:
    return "JOB" if ref.job is not None else str(data.get("tag", "SMART_FOLDER"))


def _write_node(
    box: ChainRepo, ref: NodeRef, data: Mapping[str, Any], updates: Mapping[str, Any]
) -> None:
    """Write a node with group ``updates``; an empty list removes the group."""
    kept = {key: value for key, value in data.items() if not (key in updates and not updates[key])}
    groups = {key: value for key, value in updates.items() if value}
    write_json(_node_file(box, ref), _with_groups(box, _node_tag(ref, kept), kept, groups))


def set_attributes(repo: ChainRepo, node: str, changes: Mapping[str, str | None]) -> ChangeSet:
    """Set (or remove, with ``None``) plain attributes of a job or a folder."""
    repo = load_repo(repo.root)
    ref = _require_node(repo, node)
    if not changes:
        raise InvalidChange("nothing to change")
    volatile = set(repo.config.volatile_attributes)
    warnings: list[str] = []
    for key, value in changes.items():
        if key in _RENAMED_BY:
            raise InvalidChange(f"{key} is changed with {_RENAMED_BY[key]}")
        if not _ATTRIBUTE_NAME.fullmatch(key):
            raise InvalidChange(f"invalid attribute name {key!r} (upper case, digits, _)")
        if key in volatile:
            raise InvalidChange(f"{key} is export metadata kept in meta/; it is not edited")
        if value is not None and not isinstance(value, str):
            raise InvalidChange(f"{key}: the value must be text")
        if value and key in repo.config.letter_rule.attributes:
            warnings.extend(_name_warnings(repo, value))
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        data = dict(read_json(_node_file(box, ref)))
        for key, value in changes.items():
            if isinstance(data.get(key), list):
                raise InvalidChange(f"{key} is a group of elements, not an attribute")
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        _write_node(box, ref, data, {})
        summary = f"set {len(changes)} attribute(s) on {ref}"
        return _finish(original, box, summary, warnings)


def set_variables(repo: ChainRepo, node: str, variables: Sequence[Mapping[str, Any]]) -> ChangeSet:
    """Replace the VARIABLE elements of a job or a folder (an empty list removes them)."""
    repo = load_repo(repo.root)
    ref = _require_node(repo, node)
    clean: list[dict[str, str]] = []
    for variable in variables:
        name, value = variable.get("NAME"), variable.get("VALUE")
        if not isinstance(name, str) or not name.startswith("%%"):
            raise InvalidChange(f"Control-M variable names start with %%, got {name!r}")
        if not isinstance(value, str):
            raise InvalidChange(f"{name}: the value must be text")
        if any(existing["NAME"] == name for existing in clean):
            raise InvalidChange(f"{name} is defined twice")
        clean.append({"NAME": name, "VALUE": value})
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        _write_node(box, ref, dict(read_json(_node_file(box, ref))), {"VARIABLE": clean})
        summary = f"set {len(clean)} variable(s) on {ref}"
        return _finish(original, box, summary, [])


def replace_node(repo: ChainRepo, node: str, data: Mapping[str, Any]) -> ChangeSet:
    """Replace the whole JSON of a node (advanced editing); identity fields cannot change."""
    repo = load_repo(repo.root)
    ref = _require_node(repo, node)
    if not isinstance(data, Mapping):
        raise InvalidChange("the node must be a JSON object")
    current = read_json(_node_file(repo, ref))
    fixed = ("JOBNAME", "PARENT_FOLDER") if ref.job is not None else ("FOLDER_NAME", "tag", "jobs")
    for key in fixed:
        if data.get(key) != current.get(key):
            raise InvalidChange(
                f"{key} cannot change here (use {_RENAMED_BY.get(key, 'the refactorings')})"
            )
    volatile = sorted(set(data) & set(repo.config.volatile_attributes))
    if volatile:
        raise InvalidChange(f"export metadata is kept in meta/, not in the node: {volatile}")
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        tag = _node_tag(ref, data)
        for key, value in data.items():
            if isinstance(value, list) and _ATTRIBUTE_NAME.fullmatch(key):
                _ensure_child_tag(box, tag, key)
        box = load_repo(box.root)
        body = {k: v for k, v in data.items() if k not in ("tag", "jobs")}
        try:
            json_to_element(tag, body, box.config.child_order)
        except ModelError as exc:
            raise InvalidChange(str(exc)) from exc
        write_json(_node_file(box, ref), _with_groups(box, tag, dict(data), {}))
        return _finish(original, box, f"replace the JSON of {ref}", [])


def _require_link(links: Mapping[str, Link], link_id: str) -> Link:
    if link_id not in links:
        raise InvalidChange(f"unknown link {link_id!r}")
    return links[link_id]


def _name_in_use(links: Mapping[str, Link], name: str, except_id: str | None = None) -> str | None:
    for link in links.values():
        if link.id != except_id and name in (link.id, link.name):
            return link.id
    return None


def link_nodes(
    repo: ChainRepo,
    consumer: str,
    *,
    producer: str | None = None,
    link: str | None = None,
    name: str | None = None,
    odate: str = "ODAT",
    and_or: str = "A",
    cleanup: bool = True,
) -> ChangeSet:
    """Make ``consumer`` wait for ``producer`` (a new link) or for an existing ``link``.

    The producer emits the condition (OUTCOND ``+``), the consumer waits for it (INCOND with
    ``and_or``) and, with ``cleanup``, deletes it once it ran (OUTCOND ``-``).
    """
    repo = load_repo(repo.root)
    target = _require_node(repo, consumer)
    if and_or not in _AND_OR:
        raise InvalidChange(f"AND_OR must be A or O, got {and_or!r}")
    source = _require_node(repo, producer) if producer else None
    if source == target:
        raise InvalidChange("a node cannot wait for itself")
    links = load_links(repo)
    warnings: list[str] = []
    if link is not None:
        existing = _require_link(links, link)
        if target in existing.consumers:
            raise InvalidChange(f"{target} already waits for {link}")
        link_id, emit = link, source is not None and source not in existing.all_producers
        odate = existing.odates[0] if existing.odates else odate
    else:
        if source is None:
            raise InvalidChange("link needs a producer or an existing link")
        already = [
            c.id for c in links.values() if source in c.all_producers and target in c.consumers
        ]
        if already:
            raise InvalidChange(f"{target} already waits for {source} ({already[0]})")
        if name:
            used = _name_in_use(links, name)
            if used:
                raise InvalidChange(f"condition name {name} is already used by link {used}")
            link_id = name
            warnings.extend(_name_warnings(repo, name))
        else:
            base = f"{source.name}-{target.name}_OK"
            link_id, suffix = base, 2
            while _name_in_use(links, link_id):
                link_id, suffix = f"{base}_{suffix}", suffix + 1
        emit = True
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        if emit and source is not None:
            data = dict(read_json(_node_file(box, source)))
            outs = [*data.get("OUTCOND", []), {LINK_KEY: link_id, "ODATE": odate, "SIGN": "+"}]
            _write_node(box, source, data, {"OUTCOND": outs})
        data = dict(read_json(_node_file(box, target)))
        updates: dict[str, Any] = {
            "INCOND": [
                *data.get("INCOND", []),
                {LINK_KEY: link_id, "ODATE": odate, "AND_OR": and_or},
            ]
        }
        if cleanup:
            updates["OUTCOND"] = [
                *data.get("OUTCOND", []),
                {LINK_KEY: link_id, "ODATE": odate, "SIGN": "-"},
            ]
        _write_node(box, target, data, updates)
        summary = f"{target} now waits for {link_id}" + (f" emitted by {source}" if source else "")
        return _finish(original, box, summary, warnings)


def unlink_nodes(repo: ChainRepo, link_id: str, consumer: str) -> ChangeSet:
    """``consumer`` stops waiting for ``link_id``; with no consumer left the emission goes too."""
    repo = load_repo(repo.root)
    target_link = _require_link(load_links(repo), link_id)
    target = _require_node(repo, consumer)
    if target not in target_link.consumers:
        raise InvalidChange(f"{target} does not wait for {link_id}")
    remaining = [c for c in target_link.consumers if c != target]
    warnings: list[str] = []
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        data = dict(read_json(_node_file(box, target)))
        ins = [e for e in data.get("INCOND", []) if e.get(LINK_KEY) != link_id]
        outs = [
            e for e in data.get("OUTCOND", [])
            if not (e.get(LINK_KEY) == link_id and e.get("SIGN") == "-")
        ]  # fmt: skip
        _write_node(box, target, data, {"INCOND": ins, "OUTCOND": outs})
        summary = f"{target} no longer waits for {link_id}"
        if not remaining:
            for producer in target_link.producers:
                pdata = dict(read_json(_node_file(box, producer)))
                pouts = [
                    e for e in pdata.get("OUTCOND", [])
                    if not (e.get(LINK_KEY) == link_id and e.get("SIGN") == "+")
                ]  # fmt: skip
                _write_node(box, producer, pdata, {"OUTCOND": pouts})
            if target_link.producers:
                emitters = ", ".join(str(p) for p in target_link.producers)
                summary += f"; no consumer left: emission removed from {emitters}"
            for node, code in target_link.docond_add:
                warnings.append(f"{node} still emits {link_id} from its ON {code} block")
        return _finish(original, box, summary, warnings)


def _set_odate(data: dict[str, Any], link_id: str, odate: str) -> None:
    for group in ("INCOND", "OUTCOND"):
        for entry in data.get(group, []):
            if entry.get(LINK_KEY) == link_id:
                entry["ODATE"] = odate
    for block in data.get("ON", []):
        for child in block.get("children", []):
            if child.get("tag") == "DOCOND" and child.get(LINK_KEY) == link_id:
                child["ODATE"] = odate


def update_relation(
    repo: ChainRepo,
    link_id: str,
    consumer: str,
    *,
    and_or: str | None = None,
    odate: str | None = None,
    cleanup: bool | None = None,
) -> ChangeSet:
    """Change how ``consumer`` waits for ``link_id``: AND_OR, cleanup (``-``) and the ODATE.

    The ODATE is changed on every element of the link (emission, waits, deletions) so that
    producer and consumers keep matching.
    """
    if and_or is not None and and_or not in _AND_OR:
        raise InvalidChange(f"AND_OR must be A or O, got {and_or!r}")
    if odate is not None and not odate.strip():
        raise InvalidChange("ODATE cannot be empty")
    if and_or is None and odate is None and cleanup is None:
        raise InvalidChange("nothing to change")
    repo = load_repo(repo.root)
    target_link = _require_link(load_links(repo), link_id)
    target = _require_node(repo, consumer)
    if target not in target_link.consumers:
        raise InvalidChange(f"{target} does not wait for {link_id}")
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        if odate is not None:
            touched = {*target_link.producers, *target_link.consumers, *target_link.deleters}
            touched |= {n for n, _ in (*target_link.docond_add, *target_link.docond_delete)}
            for node in touched:
                data = dict(read_json(_node_file(box, node)))
                _set_odate(data, link_id, odate)
                write_json(_node_file(box, node), data)
        data = dict(read_json(_node_file(box, target)))
        current_odate = odate or "ODAT"
        for entry in data.get("INCOND", []):
            if entry.get(LINK_KEY) == link_id:
                current_odate = entry.get("ODATE", current_odate)
                if and_or is not None:
                    entry["AND_OR"] = and_or
        outs = list(data.get("OUTCOND", []))
        deletes = [e for e in outs if e.get(LINK_KEY) == link_id and e.get("SIGN") == "-"]
        if cleanup is True and not deletes:
            outs.append({LINK_KEY: link_id, "ODATE": current_odate, "SIGN": "-"})
        if cleanup is False:
            outs = [e for e in outs if e not in deletes]
        _write_node(box, target, data, {"INCOND": data.get("INCOND", []), "OUTCOND": outs})
        parts = [
            f"AND_OR={and_or}" if and_or else "",
            f"ODATE={odate}" if odate else "",
            {True: "cleanup on", False: "cleanup off", None: ""}[cleanup],
        ]
        summary = f"{target} waiting for {link_id}: " + ", ".join(p for p in parts if p)
        return _finish(original, box, summary, [])


def rename_link(repo: ChainRepo, link_id: str, name: str) -> ChangeSet:
    """Change the export name of a link (every INCOND/OUTCOND/DOCOND that refers to it)."""
    repo = load_repo(repo.root)
    links = load_links(repo)
    _require_link(links, link_id)
    if not name or any(ch.isspace() for ch in name):
        raise InvalidChange(f"invalid condition name {name!r}")
    used = _name_in_use(links, name, except_id=link_id)
    if used:
        raise InvalidChange(f"condition name {name} is already used by link {used}")
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        summary = f"rename condition {links[link_id].name} -> {name}"
        return _finish(original, box, summary, _name_warnings(repo, name), {link_id: name})


def emit_condition(repo: ChainRepo, link_id: str, producer: str) -> ChangeSet:
    """``producer`` starts emitting ``link_id`` (OUTCOND ``+``) for the jobs that wait for it."""
    repo = load_repo(repo.root)
    target_link = _require_link(load_links(repo), link_id)
    source = _require_node(repo, producer)
    if source in target_link.all_producers:
        raise InvalidChange(f"{source} already emits {link_id}")
    if source in target_link.consumers:
        raise InvalidChange("a node cannot wait for itself")
    odate = target_link.odates[0] if target_link.odates else "ODAT"
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        data = dict(read_json(_node_file(box, source)))
        outs = [*data.get("OUTCOND", []), {LINK_KEY: link_id, "ODATE": odate, "SIGN": "+"}]
        _write_node(box, source, data, {"OUTCOND": outs})
        return _finish(original, box, f"{source} now emits {link_id}", [])


def stop_emitting(repo: ChainRepo, link_id: str, producer: str) -> ChangeSet:
    """``producer`` stops emitting ``link_id`` (its OUTCOND ``+`` goes)."""
    repo = load_repo(repo.root)
    target_link = _require_link(load_links(repo), link_id)
    source = _require_node(repo, producer)
    if source not in target_link.producers:
        raise InvalidChange(f"{source} does not emit {link_id} (OUTCOND +)")
    warnings = [f"{c} still waits for {link_id}" for c in target_link.consumers]
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        data = dict(read_json(_node_file(box, source)))
        outs = [
            e for e in data.get("OUTCOND", [])
            if not (e.get(LINK_KEY) == link_id and e.get("SIGN") == "+")
        ]  # fmt: skip
        _write_node(box, source, data, {"OUTCOND": outs})
        return _finish(original, box, f"{source} no longer emits {link_id}", warnings)


_BATCH_SUMMARIES = 5


def batch(repo: ChainRepo, changes: Sequence[Mapping[str, Any]]) -> ChangeSet:
    """Several operations as one change set, each computed on the result of the previous ones.

    A repeated operation is run once; a failing one is named (``change n of m``).
    """
    unique: dict[str, Mapping[str, Any]] = {}
    for item in changes:
        unique.setdefault(json.dumps(item, sort_keys=True), item)
    items = list(unique.values())
    if not items:
        raise InvalidChange("nothing to change")
    repo = load_repo(repo.root)
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        summaries: list[str] = []
        warnings: list[str] = []
        token = _IN_PLACE.set(box.root)
        try:
            for number, item in enumerate(items, 1):
                op = str(item.get("op", ""))
                if op == "batch":
                    raise InvalidChange("a batch cannot contain another batch")
                try:
                    change = run_operation(box, op, dict(item.get("params", {})))
                except ChainError as exc:
                    raise InvalidChange(f"change {number} of {len(items)} ({op}): {exc}") from exc
                summaries.append(change.summary)
                warnings.extend(change.warnings)
        finally:
            _IN_PLACE.reset(token)
        shown = "; ".join(summaries[:_BATCH_SUMMARIES])
        if len(summaries) > _BATCH_SUMMARIES:
            shown += f"; and {len(summaries) - _BATCH_SUMMARIES} more"
        plural = "" if len(items) == 1 else "s"
        return _finish(original, box, f"{len(items)} change{plural}: {shown}", warnings)


# ---------------------------------------------------------------- registry (used by the web API)

OPERATIONS: dict[str, Callable[..., ChangeSet]] = {
    "set-attributes": set_attributes,
    "set-variables": set_variables,
    "replace-node": replace_node,
    "link": link_nodes,
    "unlink": lambda repo, link, consumer: unlink_nodes(repo, link, consumer),
    "update-relation": lambda repo, link, consumer, **kw: update_relation(
        repo, link, consumer, **kw
    ),
    "rename-link": lambda repo, link, name: rename_link(repo, link, name),
    "emit": lambda repo, link, producer: emit_condition(repo, link, producer),
    "stop-emitting": lambda repo, link, producer: stop_emitting(repo, link, producer),
    "batch": lambda repo, changes: batch(repo, changes),
    "rename-job": rename_job,
    "rename-folder": rename_folder,
    "rename-subapp": rename_subapp,
    "move-job": move_job,
    "insert-job": insert_job,
    "extract-variable": extract_variable,
    "set-exception": set_exception,
    "rename-constant": lambda repo, old, new: rename_constant(repo, old, new),
}


def run_operation(repo: ChainRepo, op: str, params: Mapping[str, Any]) -> ChangeSet:
    """Compute the change set of a named operation; parameters are checked before running."""
    function = OPERATIONS.get(op)
    if function is None:
        raise InvalidChange(f"unknown operation {op!r}; known: {', '.join(sorted(OPERATIONS))}")
    try:
        inspect.signature(function).bind(repo, **params)
    except TypeError as exc:
        raise InvalidChange(f"{op}: {exc}") from exc
    return function(repo, **params)
