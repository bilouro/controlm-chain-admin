"""Operations of the core: import an export into the repository, export it back.

Every operation takes a :class:`ChainRepo` and returns serialisable results or raises typed
errors. Nothing here prints or exits. Operations re-read ``chain.json`` from disk, so a caller
may keep using the :class:`ChainRepo` it loaded even after an import updated the rules.
"""

from __future__ import annotations

import re
import shutil
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
from controlm_chain_admin.core.links import rebuild_links
from controlm_chain_admin.core.model import XmlDeclaration, XmlDocument, XmlElement
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json, write_json
from controlm_chain_admin.core.xmlio import parse_xml, serialize_xml

FOLDER_TAGS = ("SMART_FOLDER", "FOLDER")
JOB_TAG = "JOB"
JOBS_KEY = "jobs"
TAG_KEY = "tag"
#: Separator between a JOBNAME and the occurrence number when a folder repeats a JOBNAME.
DUPLICATE_SEPARATOR = "~"

_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]*")


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
        }


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


def import_xml(repo: ChainRepo, data: bytes, env: str | None = None) -> ImportReport:
    """Import a Control-M export: folders of the repository's application become JSON files.

    With the letter rule enabled, ``env`` names the environment the export came from and its
    letter is stripped from names; file and directory names are environment-neutral.
    """
    repo = load_repo(repo.root)
    letter = _letter(repo, env, "import")
    document = parse_xml(data)
    kept, skipped = _split_by_application(document, repo.config.application)
    constants_report = ImportConstantsReport(0, {})
    if env is not None and repo.config.constants:
        kept, constants_report = apply_import(
            kept, repo.config.constants, repo.load_env(env).constants
        )
    letter_report = LetterReport((), ())
    if letter is not None:
        known = tuple(repo.env_letters().values())
        kept, letter_report = strip_letter(kept, letter, repo.config.letter_rule, known)
    attr_observed, child_observed = observe_orders(document)
    config = replace(
        repo.config,
        attribute_order=merge_orders(repo.config.attribute_order, attr_observed),
        child_order=merge_orders(repo.config.child_order, child_observed),
    )
    repo = repo.save_config(config)

    imported: list[str] = []
    duplicates: list[str] = []
    jobs = 0
    files = 1  # chain.json
    for folder in kept.root.elements():
        name = _check_safe(folder.get("FOLDER_NAME"), "folder")
        if name in imported:
            raise DuplicateName(f"folder {name} appears twice in the export")
        written, repeated = _write_folder(repo, folder, name)
        files += written
        duplicates.extend(f"{name}/{job}" for job in repeated)
        imported.append(name)
        jobs += len(folder.find_all(JOB_TAG))

    write_json(repo.export_meta_file, _export_meta(repo, document, imported))
    rebuild_links(repo)  # derived links.json per folder
    return ImportReport(
        application=config.application,
        folders=tuple(imported),
        jobs=jobs,
        skipped=skipped,
        duplicate_job_names=tuple(duplicates),
        files_written=files + 1,
        environment=env,
        literal_marks=letter_report.literal_marks,
        suspicious_values=letter_report.suspicious,
        constants_replaced=constants_report.replaced,
        unmapped=constants_report.unmapped,
    )


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


def _write_folder(repo: ChainRepo, folder: XmlElement, name: str) -> tuple[int, list[str]]:
    """Write folder.json, the job files and the metadata sidecar. Returns (files, repeats)."""
    config = repo.config
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
    write_json(repo.folder_meta_file(name), {"attrs": folder_meta, JOBS_KEY: jobs_meta})
    return 2 + len(ids), repeated


def _export_meta(repo: ChainRepo, document: XmlDocument, imported: list[str]) -> dict[str, Any]:
    """Header of the export plus the folder order, merged with a previous import if any."""
    previous: list[str] = []
    if repo.export_meta_file.exists():
        recorded = read_json(repo.export_meta_file).get("folder_order", [])
        previous = [f for f in recorded if repo.folder_file(f).exists()]
    order = previous + [f for f in imported if f not in previous]
    declaration = document.declaration
    return {
        "declaration": {
            "version": declaration.version,
            "encoding": declaration.encoding,
            "standalone": declaration.standalone,
        },
        "prolog_comments": list(document.prolog_comments),
        "root_tag": document.root.tag,
        "root_attrs": dict(document.root.attrs),
        "folder_order": order,
    }


# ---------------------------------------------------------------- export


def load_document(repo: ChainRepo) -> XmlDocument:
    """The repository as one neutral document: names without letter, metadata merged back."""
    repo = load_repo(repo.root)
    if not repo.export_meta_file.exists():
        raise ModelError(f"{repo.root}: nothing to export yet (no import was done)")
    meta = read_json(repo.export_meta_file)
    folders = tuple(_read_folder(repo, name) for name in meta.get("folder_order", []))
    root = XmlElement(str(meta["root_tag"]), tuple(dict(meta["root_attrs"]).items()), folders)
    declaration = XmlDeclaration(**meta["declaration"])
    return XmlDocument(root, declaration, tuple(meta.get("prolog_comments", [])))


def export_document(
    repo: ChainRepo, env: str | None = None, *, allow_unresolved: bool = False
) -> tuple[bytes, ExportConstantsReport]:
    """Export for ``env`` and report the constants resolved; unresolved raise unless allowed."""
    repo = load_repo(repo.root)
    letter = _letter(repo, env, "export")
    document = load_document(repo)
    report = ExportConstantsReport(0, ())
    if env is not None and repo.config.constants:
        document, report = apply_export(
            document,
            repo.config.constants,
            repo.load_env(env).constants,
            allow_unresolved=allow_unresolved,
        )
    if letter is not None:
        document = add_letter(document, letter, repo.config.letter_rule)
    return serialize_xml(document), report


def export_xml(
    repo: ChainRepo, env: str | None = None, *, allow_unresolved: bool = False
) -> bytes:
    """Regenerate the Control-M export for ``env``; byte-identical for untouched content."""
    return export_document(repo, env, allow_unresolved=allow_unresolved)[0]


def _read_folder(repo: ChainRepo, name: str) -> XmlElement:
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
