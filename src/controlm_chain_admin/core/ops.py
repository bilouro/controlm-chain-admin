"""Operations of the core: import an export into the repository, export it back.

Every operation takes a :class:`ChainRepo` and returns serialisable results or raises typed
errors. Nothing here prints or exits. Operations re-read ``chain.json`` from disk, so a caller
may keep using the :class:`ChainRepo` it loaded even after an import updated the rules.

Import pipeline: parse → keep the repository's application → constants → letter rule →
condition names become link references → JSON files → links.json (names) and index.json.
Export is the mirror image, with the name policy (``original`` or ``standard``) applied when
link references become ``NAME`` attributes again.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from controlm_chain_admin.core.constants import (
    ExportConstantsReport,
    ImportConstantsReport,
    apply_export,
    apply_import,
)
from controlm_chain_admin.core.errors import (
    DuplicateName,
    EnvironmentRequired,
    ModelError,
    UnsafeName,
    XmlFormatError,
)
from controlm_chain_admin.core.jsonmodel import (
    element_to_json,
    json_to_element,
    merge_orders,
    merge_volatile,
    observe_orders,
    split_volatile,
)
from controlm_chain_admin.core.letter import LetterReport, add_letter, strip_letter
from controlm_chain_admin.core.links import (
    DUPLICATE_SEPARATOR,
    LINK_KEY,
    build_links,
    collect_conditions,
    load_links,
    read_names,
    standard_names,
    write_index,
    write_names,
)
from controlm_chain_admin.core.model import XmlComment, XmlDeclaration, XmlDocument, XmlElement
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json, write_json
from controlm_chain_admin.core.xmlio import parse_xml, serialize_xml

FOLDER_TAGS = ("SMART_FOLDER", "FOLDER")
JOB_TAG = "JOB"
JOBS_KEY = "jobs"
TAG_KEY = "tag"
CONDITION_TAGS = ("INCOND", "OUTCOND", "DOCOND")
NAME_POLICIES = ("original", "standard")
JOBNAME_POLICIES = ("deduped", "original")
ORIGINALS_KEY = "original_jobnames"

_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]*")

__all__ = [
    "DUPLICATE_SEPARATOR",
    "ExportReport",
    "ImportReport",
    "SkippedFolder",
    "dedupe_jobnames",
    "export_document",
    "export_xml",
    "import_xml",
    "job_ids",
    "load_document",
    "only_application",
]


@dataclass(frozen=True)
class SkippedFolder:
    folder: str
    application: str | None


@dataclass(frozen=True)
class ImportReport:
    """What an import did: folders and jobs written, folders of other applications skipped."""

    application: str
    folders: tuple[str, ...]
    jobs: int
    skipped: tuple[SkippedFolder, ...]
    duplicate_job_names: tuple[str, ...]  # "FOLDER/JOBNAME" repeated inside its folder
    files_written: int
    environment: str | None = None
    literal_marks: tuple[str, ...] = ()
    suspicious_values: tuple[str, ...] = ()
    constants_replaced: int = 0
    unmapped: dict[str, tuple[str, ...]] = field(default_factory=dict)
    links: int = 0
    jobnames_deduped: tuple[str, ...] = ()  # "FOLDER/ORIGINAL -> NEW"

    def to_json(self) -> dict[str, Any]:
        return {
            "application": self.application,
            "folders": list(self.folders),
            "jobs": self.jobs,
            "skipped": [{"folder": s.folder, "application": s.application} for s in self.skipped],
            "duplicate_job_names": list(self.duplicate_job_names),
            "files_written": self.files_written,
            "environment": self.environment,
            "literal_marks": list(self.literal_marks),
            "suspicious_values": list(self.suspicious_values),
            "constants_replaced": self.constants_replaced,
            "unmapped": {k: list(v) for k, v in self.unmapped.items()},
            "links": self.links,
            "jobnames_deduped": list(self.jobnames_deduped),
        }


@dataclass(frozen=True)
class ExportReport:
    """What an export did besides writing bytes."""

    constants: ExportConstantsReport
    names: str
    renamed: int  # links whose export name differs from their original name


def _check_safe(name: str | None, what: str) -> str:
    if not name or not _SAFE_NAME.fullmatch(name):
        raise UnsafeName(f"{what} name {name!r} cannot be used as a file name")
    return name


def _strings(data: dict[str, Any]) -> dict[str, str]:
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _non_strings(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if not isinstance(v, str)}


def job_ids(job_names: list[str]) -> list[str]:
    """File stems for the jobs of one folder: JOBNAME, then JOBNAME~2, JOBNAME~3 for repeats."""
    seen: dict[str, int] = {}
    ids: list[str] = []
    for name in job_names:
        seen[name] = seen.get(name, 0) + 1
        ids.append(name if seen[name] == 1 else f"{name}{DUPLICATE_SEPARATOR}{seen[name]}")
    return ids


# ---------------------------------------------------------------- link references


def _to_link_refs(element: XmlElement, ids_by_name: Mapping[str, str]) -> XmlElement:
    """Condition elements: the ``NAME`` attribute becomes a ``link`` reference (same position).

    A name that is already the export name of a known link maps back to that link's id, so a
    renamed link keeps its id when its export is imported again.
    """
    attrs = element.attrs
    if element.tag in CONDITION_TAGS:
        attrs = tuple(
            (LINK_KEY, ids_by_name.get(v, v)) if k == "NAME" else (k, v) for k, v in attrs
        )
    children = tuple(
        c if isinstance(c, XmlComment) else _to_link_refs(c, ids_by_name) for c in element.children
    )
    return replace(element, attrs=attrs, children=children)


def _from_link_refs(element: XmlElement, names: Mapping[str, str], where: str) -> XmlElement:
    """Inverse of :func:`_to_link_refs`: ``link`` references become ``NAME`` attributes."""
    attrs = element.attrs
    if element.tag in CONDITION_TAGS:
        resolved: list[tuple[str, str]] = []
        for key, value in attrs:
            if key == LINK_KEY:
                if value not in names:
                    raise ModelError(f"{where}: <{element.tag}> references unknown link {value!r}")
                resolved.append(("NAME", names[value]))
            else:
                resolved.append((key, value))
        attrs = tuple(resolved)
    children = tuple(
        c if isinstance(c, XmlComment) else _from_link_refs(c, names, where)
        for c in element.children
    )
    return replace(element, attrs=attrs, children=children)


def _dedupe_jobnames(
    document: XmlDocument,
) -> tuple[XmlDocument, tuple[tuple[str, str, str], ...]]:
    """Give every repeated JOBNAME a numeric suffix (``X``, ``X2``, ``X3``) in document order.

    The first occurrence keeps its name; a suffix already used by a real job is skipped. Only
    ``JOBNAME`` changes (``MEMNAME`` and condition names are left alone). Returns the new
    document and the renames as ``(folder, original, new)``.
    """
    taken = {
        job.get("JOBNAME") or ""
        for folder in document.root.elements()
        for job in folder.find_all(JOB_TAG)
    }
    seen: set[str] = set()
    renames: list[tuple[str, str, str]] = []
    new_folders: list[XmlElement | XmlComment] = []
    for folder in document.root.children:
        if not isinstance(folder, XmlElement):
            new_folders.append(folder)
            continue
        children: list[XmlElement | XmlComment] = []
        for child in folder.children:
            if isinstance(child, XmlElement) and child.tag == JOB_TAG:
                name = child.get("JOBNAME") or ""
                if name in seen:
                    suffix = 2
                    while f"{name}{suffix}" in taken:
                        suffix += 1
                    new = f"{name}{suffix}"
                    taken.add(new)
                    renames.append((folder.get("FOLDER_NAME") or "", name, new))
                    attrs = tuple((k, new if k == "JOBNAME" else v) for k, v in child.attrs)
                    child = replace(child, attrs=attrs)
                    name = new
                seen.add(name)
            children.append(child)
        new_folders.append(replace(folder, children=tuple(children)))
    if not renames:
        return document, ()
    return replace(document, root=replace(document.root, children=tuple(new_folders))), tuple(
        renames
    )


dedupe_jobnames = _dedupe_jobnames  # public name; import_xml's flag shadows it inside


# ---------------------------------------------------------------- import


def _letter(repo: ChainRepo, env: str | None, action: str) -> str | None:
    """Letter of ``env`` when the letter rule is enabled; validates the name either way."""
    if env is not None:
        letter = repo.load_env(env).letter
        return letter if repo.config.letter_rule.enabled else None
    if repo.config.letter_rule.enabled or repo.config.constants:
        known = ", ".join(repo.config.environments)
        reason = (
            "the letter rule is enabled"
            if repo.config.letter_rule.enabled
            else "constants are defined"
        )
        raise EnvironmentRequired(f"{reason}: {action} needs --env (one of {known})")
    return None


def _split_by_application(
    document: XmlDocument, application: str
) -> tuple[XmlDocument, tuple[SkippedFolder, ...]]:
    """Keep the folders of ``application``; list the others (by their names in the export)."""
    kept: list[XmlElement] = []
    skipped: list[SkippedFolder] = []
    for folder in document.root.elements():
        if folder.tag not in FOLDER_TAGS:
            raise XmlFormatError(f"unexpected top-level element <{folder.tag}>")
        if folder.get("APPLICATION") == application:
            kept.append(folder)
        else:
            skipped.append(
                SkippedFolder(folder.get("FOLDER_NAME") or "?", folder.get("APPLICATION"))
            )
    root = replace(document.root, children=tuple(kept))
    return replace(document, root=root), tuple(skipped)


def only_application(document: XmlDocument, application: str) -> XmlDocument:
    """The document restricted to the folders of ``application`` (public wrapper)."""
    return _split_by_application(document, application)[0]


def import_xml(
    repo: ChainRepo,
    data: bytes,
    env: str | None = None,
    *,
    dedupe_jobnames: bool | None = None,
) -> ImportReport:
    """Import a Control-M export: folders of the repository's application become JSON files.

    With the letter rule enabled, ``env`` names the environment the export came from and its
    letter is stripped from names; file and directory names are environment-neutral.
    ``dedupe_jobnames`` sets the repository policy (kept in chain.json for later imports).
    """
    repo = load_repo(repo.root)
    letter = _letter(repo, env, "import")
    document = parse_xml(data)
    attr_observed, child_observed = observe_orders(document)
    config = replace(
        repo.config,
        attribute_order=merge_orders(repo.config.attribute_order, attr_observed),
        child_order=merge_orders(repo.config.child_order, child_observed),
    )
    if dedupe_jobnames is not None:
        config = replace(config, dedupe_jobnames=dedupe_jobnames)
    repo = repo.save_config(config)
    existing_names = read_names(repo)  # names the user may have edited survive a re-import
    ids_by_name: dict[str, str] = {}
    for link_id, name in existing_names.items():
        ids_by_name.setdefault(name, link_id)

    kept, skipped = _split_by_application(document, config.application)
    constants_report = ImportConstantsReport(0, {})
    if env is not None and config.constants:
        kept, constants_report = apply_import(kept, config.constants, repo.load_env(env).constants)
    letter_report = LetterReport((), ())
    if letter is not None:
        known = tuple(repo.env_letters().values())
        kept, letter_report = strip_letter(kept, letter, config.letter_rule, known)
    renames: tuple[tuple[str, str, str], ...] = ()
    if config.dedupe_jobnames:
        kept, renames = _dedupe_jobnames(kept)
    originals: dict[str, dict[str, str]] = {}
    for folder_name, original, new in renames:
        originals.setdefault(folder_name, {})[new] = original

    imported: list[str] = []
    duplicates: list[str] = []
    jobs = 0
    files = 1  # chain.json
    for folder in kept.root.elements():
        name = _check_safe(folder.get("FOLDER_NAME"), "folder")
        if name in imported:
            raise DuplicateName(f"folder {name} appears twice in the export")
        refs = _to_link_refs(folder, ids_by_name)
        written, repeated = _write_folder(repo, refs, name, originals.get(name, {}))
        files += written
        duplicates.extend(f"{name}/{job}" for job in repeated)
        imported.append(name)
        jobs += len(folder.find_all(JOB_TAG))

    write_json(repo.export_meta_file, _export_meta(repo, document, imported))
    links = build_links(collect_conditions(repo), existing_names)
    files += write_names(repo, links) + write_index(repo, links) + 1
    return ImportReport(
        application=config.application,
        folders=tuple(imported),
        jobs=jobs,
        skipped=skipped,
        duplicate_job_names=tuple(duplicates),
        files_written=files,
        environment=env,
        literal_marks=letter_report.literal_marks,
        suspicious_values=letter_report.suspicious,
        constants_replaced=constants_report.replaced,
        unmapped=constants_report.unmapped,
        links=len(links),
        jobnames_deduped=tuple(f"{f}/{o} -> {n}" for f, o, n in renames),
    )


def _write_folder(
    repo: ChainRepo, folder: XmlElement, name: str, renamed: Mapping[str, str]
) -> tuple[int, list[str]]:
    """Write folder.json, the job files and the metadata sidecar. Returns (files, repeats).

    ``renamed`` maps deduplicated JOBNAMEs of this import to their originals; originals recorded
    by a previous import are kept for jobs that still carry the deduplicated name.
    """
    config = repo.config
    meta_file = repo.folder_meta_file(name)
    previous: dict[str, str] = (
        read_json(meta_file).get(ORIGINALS_KEY, {}) if meta_file.exists() else {}
    )
    job_elements = folder.find_all(JOB_TAG)
    job_names = [_check_safe(job.get("JOBNAME"), "job") for job in job_elements]
    ids = job_ids(job_names)
    repeated = sorted({n for n in job_names if job_names.count(n) > 1})

    folder_dir = repo.folder_dir(name)
    if folder_dir.exists():
        shutil.rmtree(folder_dir)  # drop jobs that disappeared since the previous import

    kept_attrs, folder_meta = split_volatile(folder.attrs, config.volatile_attributes)
    without_jobs = replace(
        folder,
        attrs=kept_attrs,
        children=tuple(
            c for c in folder.children if not (isinstance(c, XmlElement) and c.tag == JOB_TAG)
        ),
    )
    folder_json = element_to_json(without_jobs, config.child_order)
    if "children" in folder_json:
        raise ModelError(
            f"folder {name}: children cannot be grouped (comments or unexpected order)"
        )
    write_json(repo.folder_file(name), {TAG_KEY: folder.tag, **folder_json, JOBS_KEY: ids})

    jobs_meta: dict[str, dict[str, str]] = {}
    for job_id, job in zip(ids, job_elements, strict=True):
        job_attrs, job_meta = split_volatile(job.attrs, config.volatile_attributes)
        jobs_meta[job_id] = job_meta
        job_json = element_to_json(replace(job, attrs=job_attrs), config.child_order)
        write_json(repo.job_file(name, job_id), job_json)
    meta: dict[str, Any] = {"attrs": folder_meta, JOBS_KEY: jobs_meta}
    originals = {
        job_id: renamed.get(job_id) or previous[job_id]
        for job_id in ids
        if job_id in renamed or (job_id in previous and previous[job_id] != job_id)
    }
    if originals:
        meta[ORIGINALS_KEY] = originals
    write_json(meta_file, meta)
    return 2 + len(ids), repeated


def _export_meta(repo: ChainRepo, document: XmlDocument, imported: list[str]) -> dict[str, Any]:
    """Header of the export plus the folder order, merged with a previous import if any.

    A partial export (some folders of the repository are not in it, e.g. one folder delivered
    on its own) keeps the header of the previous import; a full export replaces it.
    """
    previous: list[str] = []
    recorded_meta: dict[str, Any] = {}
    if repo.export_meta_file.exists():
        recorded_meta = read_json(repo.export_meta_file)
        recorded = recorded_meta.get("folder_order", [])
        previous = [f for f in recorded if repo.folder_file(f).exists()]
    order = previous + [f for f in imported if f not in previous]
    if recorded_meta and set(previous) - set(imported):
        return {**recorded_meta, "folder_order": order}
    declaration = document.declaration
    header: dict[str, Any] = {
        "declaration": {
            "version": declaration.version,
            "encoding": declaration.encoding,
            "standalone": declaration.standalone,
        },
        "prolog_comments": list(document.prolog_comments),
        "root_tag": document.root.tag,
        "root_attrs": dict(document.root.attrs),
    }
    if document.newline != "\n":
        header["newline"] = document.newline
    return {**header, "folder_order": order}


# ---------------------------------------------------------------- export


def _export_names(repo: ChainRepo, names: str) -> tuple[dict[str, str], int]:
    """``id -> NAME`` for the export under a name policy, and how many differ from the original."""
    if names not in NAME_POLICIES:
        raise ModelError(f"unknown name policy {names!r}; use one of {', '.join(NAME_POLICIES)}")
    original = read_names(repo)
    if names == "original":
        return original, 0
    links = load_links(repo)
    standard = standard_names(links)
    resolved = {**original, **standard}
    renamed = sum(1 for link_id, name in standard.items() if original.get(link_id) != name)
    return resolved, renamed


def load_document(
    repo: ChainRepo,
    names: str = "original",
    jobnames: str = "deduped",
    folders: Collection[str] | None = None,
) -> tuple[XmlDocument, int]:
    """The repository as one neutral document (metadata merged, link references resolved).

    ``folders`` keeps only those folders, in export order. Returns the document and the number
    of links renamed by the name policy.
    """
    repo = load_repo(repo.root)
    if not repo.export_meta_file.exists():
        raise ModelError(f"{repo.root}: nothing to export yet (no import was done)")
    meta = read_json(repo.export_meta_file)
    resolved, renamed = _export_names(repo, names)
    if jobnames not in JOBNAME_POLICIES:
        raise ModelError(
            f"unknown jobnames policy {jobnames!r}; use one of {', '.join(JOBNAME_POLICIES)}"
        )
    elements = tuple(
        _from_link_refs(_read_folder(repo, name, jobnames), resolved, f"folder {name}")
        for name in meta.get("folder_order", [])
        if folders is None or name in folders
    )
    root = XmlElement(str(meta["root_tag"]), tuple(dict(meta["root_attrs"]).items()), elements)
    declaration = XmlDeclaration(**meta["declaration"])
    comments = tuple(meta.get("prolog_comments", []))
    return XmlDocument(root, declaration, comments, str(meta.get("newline", "\n"))), renamed


def export_document(
    repo: ChainRepo,
    env: str | None = None,
    *,
    allow_unresolved: bool = False,
    names: str = "original",
    jobnames: str = "deduped",
    folders: Collection[str] | None = None,
) -> tuple[bytes, ExportReport]:
    """Export for ``env`` under a name policy; unresolved constants raise unless allowed.

    ``folders`` exports only those folders (an import package of whole folders).
    """
    repo = load_repo(repo.root)
    letter = _letter(repo, env, "export")
    document, renamed = load_document(repo, names, jobnames, folders)
    constants = ExportConstantsReport(0, ())
    if env is not None and repo.config.constants:
        document, constants = apply_export(
            document,
            repo.config.constants,
            repo.load_env(env).constants,
            allow_unresolved=allow_unresolved,
        )
    if letter is not None:
        document = add_letter(document, letter, repo.config.letter_rule)
    return serialize_xml(document), ExportReport(constants, names, renamed)


def export_xml(
    repo: ChainRepo,
    env: str | None = None,
    *,
    allow_unresolved: bool = False,
    names: str = "original",
    jobnames: str = "deduped",
) -> bytes:
    """Regenerate the Control-M export for ``env``; byte-identical for untouched content."""
    return export_document(
        repo, env, allow_unresolved=allow_unresolved, names=names, jobnames=jobnames
    )[0]


def _read_folder(repo: ChainRepo, name: str, jobnames: str = "deduped") -> XmlElement:
    config = repo.config
    folder_json: dict[str, Any] = dict(read_json(repo.folder_file(name)))
    meta_file = repo.folder_meta_file(name)
    empty_meta: dict[str, Any] = {"attrs": {}, JOBS_KEY: {}}
    folder_meta: dict[str, Any] = read_json(meta_file) if meta_file.exists() else empty_meta
    tag = str(folder_json.pop(TAG_KEY, "SMART_FOLDER"))
    ids = [str(j) for j in folder_json.pop(JOBS_KEY, [])]

    jobs: list[dict[str, Any]] = []
    job_order = config.attribute_order.get(JOB_TAG, ())
    for job_id in ids:
        job_json: dict[str, Any] = dict(read_json(repo.job_file(name, job_id)))
        job_meta = folder_meta.get(JOBS_KEY, {}).get(job_id, {})
        attrs = merge_volatile(_strings(job_json), job_meta, job_order)
        original = folder_meta.get(ORIGINALS_KEY, {}).get(job_id)
        if jobnames == "original" and original:
            attrs = tuple((k, original if k == "JOBNAME" else v) for k, v in attrs)
        jobs.append({**dict(attrs), **_non_strings(job_json)})

    folder_order = config.attribute_order.get(tag, ())
    folder_attrs = merge_volatile(
        _strings(folder_json), folder_meta.get("attrs", {}), folder_order
    )
    folder_data: dict[str, Any] = {
        **dict(folder_attrs),
        **_non_strings(folder_json),
        JOB_TAG: jobs,
    }
    return json_to_element(tag, folder_data, config.child_order)
