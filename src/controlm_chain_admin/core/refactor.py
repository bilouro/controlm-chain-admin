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
import os
import re
import shutil
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.errors import ChangeConflict, DuplicateName, ModelError
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

_TRACKED_DIRS = ("folders", "meta")
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


def _tracked(root: Path) -> dict[str, str]:
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


def _require_job(repo: ChainRepo, node: str) -> NodeRef:
    ref = NodeRef.parse(node)
    if ref.job is None or not repo.job_file(ref.folder, ref.job).is_file():
        raise ModelError(f"unknown job {node!r} (use FOLDER/JOB)")
    return ref


def _require_folder(repo: ChainRepo, folder: str) -> None:
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


def _renamed_names(links: Sequence[Link], old: str, new: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for link in links:
        renamed = rename_in_condition(link.name, old, new)
        if renamed != link.name:
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
    names = (
        _renamed_names(_touching(load_links(repo), ref), old_name, new_name)
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
    names = (
        _renamed_names(_touching(load_links(repo), ref), folder, new_name) if update_names else {}
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
    new = NodeRef.parse(node)
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
    while new_id in links:
        new_id, suffix = f"{base_id}_{suffix}", suffix + 1
    warnings = [*_name_warnings(repo, new.job), "the new job has no JOBISN; Control-M assigns one"]
    names = _renamed_names([existing], downstream.name, new.job)
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
    ref = NodeRef.parse(target)
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
