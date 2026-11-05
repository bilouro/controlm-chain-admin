"""How far the repository's export of an environment is from that environment's own export.

Folders and jobs are paired by their names without the environment letter (a name twice in one
folder by its place: ``FOLDER/JOB#2``) and compared field by field: every attribute but the
volatile ones, and every kind of child element (``INCOND``, ``ON/DOMAIL``, ``VARIABLE``...). For
each field the check names the nodes where the repository's export still differs from the
export and, for an environment other than production, counts the nodes where the export differs
from production's: what the environment changes, and how much of it the repository holds. It
reports counts and node names, never values.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.intake import detect_env
from controlm_chain_admin.core.letter import strip_letter
from controlm_chain_admin.core.model import XmlDocument, XmlElement
from controlm_chain_admin.core.ops import JOB_TAG, export_document, only_application
from controlm_chain_admin.core.overrides import load_overrides
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from controlm_chain_admin.core.xmlio import parse_xml, serialize_xml

Fields = dict[str, Any]  # attribute name or child path -> its value(s)


@dataclass(frozen=True)
class FieldCheck:
    field: str  # an attribute (``NODEID``) or a path of child elements (``ON/DOMAIL``)
    differs: tuple[str, ...]  # nodes where the repository's export differs from the export
    from_production: int | None  # nodes where the export differs from production's

    def to_json(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "differs": list(self.differs),
            "from_production": self.from_production,
        }


@dataclass(frozen=True)
class Check:
    env: str
    evidence: tuple[str, ...]
    warnings: tuple[str, ...]
    identical: bool  # the repository's export is the export, byte for byte
    nodes: int  # folders and jobs of the export
    both: int  # of them, also in the repository's export
    only_export: tuple[str, ...]
    only_repository: tuple[str, ...]
    fields: tuple[FieldCheck, ...]
    constants: int  # constants with a value in the environment
    unresolved: tuple[str, ...]  # constants the export needs and the environment has no value of
    exceptions: int  # values and lines the environment's exceptions set
    production: str | None  # the environment compared with, None when it is production

    @property
    def clean(self) -> bool:
        """Nothing but volatile attributes, order or layout differs."""
        return not (
            self.only_export or self.only_repository or any(f.differs for f in self.fields)
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "identical": self.identical,
            "clean": self.clean,
            "nodes": self.nodes,
            "both": self.both,
            "only_export": list(self.only_export),
            "only_repository": list(self.only_repository),
            "fields": [f.to_json() for f in self.fields],
            "constants": self.constants,
            "unresolved": list(self.unresolved),
            "exceptions": self.exceptions,
            "production": self.production,
        }


def _children(element: XmlElement, fields: dict[str, list[Any]], prefix: str = "") -> None:
    for child in element.elements():
        if not prefix and child.tag == JOB_TAG:
            continue  # a job of the folder is a node of its own
        path = prefix + child.tag
        fields[path].append(tuple(sorted(child.attrs)))
        _children(child, fields, path + "/")


def _fields(element: XmlElement, volatile: frozenset[str]) -> Fields:
    children: dict[str, list[Any]] = defaultdict(list)
    _children(element, children)
    attributes = {k: v for k, v in element.attrs if k not in volatile}
    return {**attributes, **{path: tuple(values) for path, values in children.items()}}


def _nodes(repo: ChainRepo, document: XmlDocument, env: str) -> dict[str, Fields]:
    """Every folder (``FOLDER/``) and job of the document, by its name without the letter."""
    rule = repo.config.letter_rule
    letters = repo.env_letters()
    document = strip_letter(document, letters[env], rule, tuple(letters.values()))[0]
    volatile = frozenset(repo.config.volatile_attributes)
    nodes: dict[str, Fields] = {}
    for folder in document.root.elements():
        name = folder.get("FOLDER_NAME") or ""
        nodes[f"{name}/"] = _fields(folder, volatile)
        seen: dict[str, int] = defaultdict(int)
        for job in folder.find_all(JOB_TAG):
            jobname = job.get("JOBNAME") or ""
            seen[jobname] += 1
            place = f"#{seen[jobname]}" if seen[jobname] > 1 else ""
            nodes[f"{name}/{jobname}{place}"] = _fields(job, volatile)
    return nodes


def _differing(left: Mapping[str, Fields], right: Mapping[str, Fields]) -> dict[str, list[str]]:
    """Field -> the nodes of both where it differs."""
    differs: dict[str, list[str]] = defaultdict(list)
    for node, fields in left.items():
        if node not in right:
            continue
        other = right[node]
        for name in dict.fromkeys([*fields, *other]):
            if fields.get(name) != other.get(name):
                differs[name].append(node)
    return differs


def check_export(repo: ChainRepo, data: bytes, env: str | None = None) -> Check:
    """Compare the export of one environment with the repository's export of it."""
    repo = load_repo(repo.root)
    document = only_application(parse_xml(data), repo.config.application)
    detected, evidence = detect_env(repo, document)
    warnings: list[str] = []
    if env is None:
        if detected is None:
            raise ModelError(
                f"cannot tell the environment of this export ({'; '.join(evidence)}): name it"
            )
        env = detected
    elif detected != env:
        warnings.append(
            f"the names say {detected}, not {env}" if detected else "; ".join(evidence)
        )
    ours, report = export_document(repo, env, allow_unresolved=True, jobnames="original")
    theirs = _nodes(repo, document, env)
    mine = _nodes(repo, parse_xml(ours), env)
    differs = _differing(theirs, mine)
    production: str | None = repo.config.git_rules.production
    from_production: dict[str, list[str]] = {}
    if production == env or production not in repo.config.environments:
        production = None
    else:
        prod_data = export_document(repo, production, allow_unresolved=True, jobnames="original")[
            0
        ]
        from_production = _differing(theirs, _nodes(repo, parse_xml(prod_data), production))
    fields = sorted(
        (
            FieldCheck(
                name,
                tuple(differs.get(name, ())),
                None if production is None else len(from_production.get(name, ())),
            )
            for name in dict.fromkeys([*differs, *from_production])
        ),
        key=lambda f: (-len(f.differs), -(f.from_production or 0), f.field),
    )
    values = repo.load_env(env).constants
    overrides = load_overrides(repo, env).values()
    return Check(
        env=env,
        evidence=evidence,
        warnings=tuple(warnings),
        identical=ours == serialize_xml(document),
        nodes=len(theirs),
        both=sum(1 for node in theirs if node in mine),
        only_export=tuple(node for node in theirs if node not in mine),
        only_repository=tuple(node for node in mine if node not in theirs),
        fields=tuple(fields),
        constants=sum(1 for name in repo.config.constants if values.get(name) is not None),
        unresolved=tuple(sorted(report.constants.unresolved)),
        exceptions=sum(o.count for o in overrides),
        production=production,
    )
