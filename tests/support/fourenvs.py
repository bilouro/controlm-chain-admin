"""Four synthetic environments (prod, uat, egma, bench), each with its own full export.

They differ in what an environment is expected to differ in: the letter of the names, the
user, the machine, the datacenter, the environment code in a variable and in a mail subject.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from controlm_chain_admin.core.envmap import DEFAULT_KEYS, EnvMap, derive, write_map
from controlm_chain_admin.core.refresh import refresh
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo
from tests.support.envexports import both, job
from tests.support.gitrepo import APP, commit_all, git
from tests.support.rawxml import filter_applications, split_folders

LETTERS = {"prod": "P", "uat": "U", "egma": "E", "bench": "B"}
ENVS = tuple(LETTERS)
USERS = {"prod": "app77proc", "uat": "aup77proc", "egma": "aep77proc", "bench": "abp77proc"}
HOSTS = {"prod": "srvp-bat1", "uat": "srvu-bat1", "egma": "srve-bat1", "bench": "srvb-bat1"}
CENTERS = {"prod": "CTMPROD", "uat": "CTMUAT", "egma": "CTMEGMA", "bench": "CTMBENCH"}
CHAIN = "P77_CHAIN"
INGEST = "P77_INGEST_DAILY"


def uat_export() -> bytes:
    """The two synthetic folders as uat has them: the jobs of the chain folder run on a host
    (the ingest ones on a host group named with the letter), every folder in a datacenter."""
    lines = both().split(b"\n")
    chain = False
    for i, line in enumerate(lines):
        if b"<SMART_FOLDER " in line:
            chain = b'FOLDER_NAME="UP77_CHAIN"' in line
            lines[i] = line.replace(b"<SMART_FOLDER ", b'<SMART_FOLDER DATACENTER="CTMUAT" ')
        elif chain:
            lines[i] = line.replace(b'NODEID="UP77_BATCH"', b'NODEID="srvu-bat1"')
    return b"\n".join(lines)


def export_of(env: str, data: bytes | None = None) -> bytes:
    """``data`` (the uat export by default) as ``env`` has it."""
    letter = LETTERS[env].encode()
    out = uat_export() if data is None else data
    for before, after in (
        (b"UP77", letter + b"P77"), (b"URQ_", letter + b"RQ_"), (b"URC_", letter + b"RC_"),
        (b"UOTH", letter + b"OTH"),
        (b'RUN_AS="aup77proc"', f'RUN_AS="{USERS[env]}"'.encode()),
        (b'NODEID="srvu-bat1"', f'NODEID="{HOSTS[env]}"'.encode()),
        (b'DATACENTER="CTMUAT"', f'DATACENTER="{CENTERS[env]}"'.encode()),
        (b'NAME="%%GEIENV" VALUE="u"', b'NAME="%%%%GEIENV" VALUE="%s"' % letter.lower()),
        (b"[P77][UAT]", f"[P77][{env.upper()}]".encode()),
    ):  # fmt: skip
        out = out.replace(before, after)
    return out


def own(data: bytes) -> bytes:
    """The folders of the application alone: what the repository gives back byte for byte."""
    return filter_applications(data, {APP})


def without_folder(data: bytes, name: str) -> bytes:
    """``data`` without the folder called ``name`` there (with its letter)."""
    raw = split_folders(data)
    body = b"".join(data[f.start : f.end] for f in raw.folders if f.name != name)
    return raw.header + body + raw.footer


def without_job(data: bytes, name: str) -> bytes:
    """``data`` without the job called ``name`` there (with its letter)."""
    named = data.index(b'JOBNAME="%s"' % name.encode())
    start = data.index(b"        <JOB ", data.rindex(b"\n", 0, named))
    end = data.index(b"        </JOB>\n", start) + len(b"        </JOB>\n")
    return data[:start] + data[end:]


def with_job(data: bytes, name: str, like: str) -> bytes:
    """``data`` with one more job, ``name``, in front of the job ``like`` and with its
    attributes (no conditions: it is not in the chain yet)."""
    line = next(row for row in data.split(b"\n") if b'JOBNAME="%s"' % like.encode() in row)
    assert line.endswith(b">") and not line.endswith(b"/>")
    alone = line[:-1].rstrip().replace(like.encode(), name.encode()) + b" />\n"  # no children
    return data.replace(line, alone + line, 1)


def with_folder(data: bytes, like: str, old: bytes, new: bytes) -> bytes:
    """``data`` with one more folder: the folder ``like`` with ``old`` in its names turned
    into ``new``."""
    raw = split_folders(data)
    chunk = next(data[f.start : f.end] for f in raw.folders if f.name == like)
    return data.replace(raw.footer, chunk.replace(old, new) + raw.footer)


WEEKLY = "P77_WEEKLY_DAILY"
RETRY = b'        <VARIABLE NAME="%%RETRY" VALUE="3" />\n'


def uat_ahead(env: str, data: bytes) -> bytes:
    """What uat has and no other environment yet: another command line for a job, a new job,
    one more variable on a folder and a whole new folder (same sub-application)."""
    if env != "uat":
        return data
    data = job(data, b"UP77_A", b"/opt/p77/bin/a.ksh", b"/opt/p77/bin/a2.ksh -x")
    data = with_job(data, "UP77_NEW", like="UP77_A")
    geienv = b'        <VARIABLE NAME="%%GEIENV" VALUE="u" />\n'
    data = data.replace(geienv, geienv + RETRY, 1)
    return with_folder(data, "UP77_INGEST_DAILY", b"INGEST", b"WEEKLY")


def empty_repo(tmp_path: Path) -> ChainRepo:
    """A git repository with the rules of the four environments and nothing else, on main."""
    root = tmp_path / "repo"
    init_repo(root, APP, ENVS, prefixes=("P77", "RQ_", "RC_"), leading_only=("RQ_", "RC_"))
    git(root, "init", "-q", "-b", "main")
    commit_all(root, "chore: the rules")
    return load_repo(root)


def write_export(tmp_path: Path, env: str, data: bytes | None = None) -> Path:
    path = tmp_path / f"{env}.xml"
    path.write_bytes(export_of(env) if data is None else data)
    return path


def four_branches(
    tmp_path: Path,
    envs: tuple[str, ...] = ENVS,
    change: Callable[[str, bytes], bytes] | None = None,
) -> ChainRepo:
    """main (prod), env/uat, env/egma and env/bench, each refreshed from its export; on main.
    ``change(env, export)`` gives what an environment has instead of its plain export."""
    repo = empty_repo(tmp_path)
    for env in envs:
        data = export_of(env) if change is None else change(env, export_of(env))
        refresh(repo, data, source=f"{env}.xml", apply=True)
    git(repo.root, "switch", "-q", "main")
    return load_repo(repo.root)


GEIENV = "VARIABLE[NAME=%%GEIENV]/@VALUE"
SUBJECT = "DOMAIL/@SUBJECT"


def with_map(repo: ChainRepo) -> EnvMap:
    """The map of everything the synthetic environments vary in, written on its branch."""
    derived = derive(repo.root, repo.config, EnvMap(), keys=(*DEFAULT_KEYS, GEIENV),
                     text_keys=(SUBJECT,), min_nodes=1)  # fmt: skip
    write_map(repo.root, repo.config, derived.envmap, "map: derived")
    return derived.envmap


def administrator(env: str) -> str:
    return USERS[env].replace("proc", "adm")


def two_users_in(target: str) -> Callable[[str, bytes], bytes]:
    """uat ahead of the others, and ``target`` running one job as an administrator where uat
    has one user for everything: what a new job of uat runs as in ``target`` is not known (the
    map derived from the branches has both, ``run_as.1`` and ``run_as.2``)."""

    def change(env: str, data: bytes) -> bytes:
        data = uat_ahead(env, data)
        if env == target:
            name = f"{LETTERS[env]}P77_B".encode()
            was, to = USERS[env].encode(), administrator(env).encode()
            data = job(data, name, b'RUN_AS="%s"' % was, b'RUN_AS="%s"' % to)
        return data

    return change
