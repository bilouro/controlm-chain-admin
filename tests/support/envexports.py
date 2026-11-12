"""A synthetic repository with constants, and the same exports as other environments have them."""

from __future__ import annotations

import re
from pathlib import Path

from controlm_chain_admin.core.constants import Selector, define_constant, parse_spec
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.gitrepo import APP, chain_git_repo, commit_all, git
from tests.support.rawxml import split_folders
from tests.support.samples import SAMPLE_EXPORT


def constants_repo(tmp_path: Path) -> ChainRepo:
    """The synthetic chain with constants for RUN_AS, NODEID and %%GEIENV (uat values)."""
    repo = chain_git_repo(tmp_path)
    define_constant(repo, "user.proc", Selector("RUN_AS"), {"uat": "aup77proc"})
    define_constant(repo, "node.batch", Selector("NODEID"),
                    {"uat": "UP77_BATCH", "prod": "PP77_BATCH"})  # fmt: skip
    define_constant(repo, "var.geienv", parse_spec("VARIABLE[NAME=%%GEIENV]/@VALUE"), {"uat": "u"})
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    commit_all(repo.root, "chore: constants")
    return repo


def to_prod(data: bytes) -> bytes:
    """The same export as prod has it: letter P, prod user and GEIENV."""
    for before, after in (
        (b"UP77", b"PP77"), (b"URQ_", b"PRQ_"), (b"URC_", b"PRC_"),
        (b'RUN_AS="aup77proc"', b'RUN_AS="app77proc"'),
        (b'NAME="%%GEIENV" VALUE="u"', b'NAME="%%GEIENV" VALUE="x"'),
    ):  # fmt: skip
        data = data.replace(before, after)
    return data


def job(data: bytes, name: bytes, before: bytes, after: bytes) -> bytes:
    """Replace ``before`` by ``after`` on the line of job ``name`` only."""
    lines = data.split(b"\n")
    for i, line in enumerate(lines):
        if f'JOBNAME="{name.decode()}"'.encode() in line:
            lines[i] = line.replace(before, after)
    return b"\n".join(lines)


def both() -> bytes:
    """The two synthetic folders in one export."""
    raw = split_folders(ANOMALY_EXPORT)
    chunk = ANOMALY_EXPORT[raw.folders[0].start : raw.folders[0].end]
    return SAMPLE_EXPORT.replace(b"</DEFTABLE>", chunk + b"</DEFTABLE>")


def prod_export() -> bytes:
    """Both folders as prod has them, also with prod's mail and subject."""
    return (
        to_prod(both())
        .replace(b"[P77][UAT]", b"[P77][PROD]")
        .replace(b'DEST="ops@example.com"', b'DEST="ops-prod@example.com"')
    )


def fresh_repo(tmp_path: Path, data: bytes | None = None) -> ChainRepo:
    """A repository of four environments that knows only a prod export, as one starts it."""
    root = tmp_path / "repo"
    repo = init_repo(root, APP, ("test", "uat", "bench", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, prod_export() if data is None else data, env="prod")
    git(root, "init", "-q", "-b", "main")
    commit_all(root, "the prod baseline")
    return load_repo(root)


def uat_full() -> bytes:
    """A full export of uat: without P77_E, with a job of its own, one more condition, another
    task type and another order than production."""
    data = re.sub(rb'\n\s*<JOB JOBISN="6".*?</JOB>', b"", both(), flags=re.S)  # no P77_E
    data = data.replace(
        b'<JOB JOBISN="7"',
        b'<JOB JOBISN="9" APPLICATION="P77_RISK_ENGINE" SUB_APPLICATION="UP77_BATCH" '
        b'MEMNAME="UP77_UATONLY" JOBNAME="UP77_UATONLY" RUN_AS="aup77proc" TASKTYPE="Dummy" '
        b'NODEID="UP77_BATCH" PARENT_FOLDER="UP77_CHAIN" />\n        <JOB JOBISN="7"',
    )
    data = data.replace(
        b'<INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" AND_OR="A" />',
        b'<INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" AND_OR="A" />\n'
        b'            <INCOND NAME="UP77_X-UP77_B_OK" ODATE="ODAT" AND_OR="A" />',
    )
    data = job(data, b"UP77_D", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"')
    c = re.search(rb'\n\s*<JOB JOBISN="4".*?</JOB>', data, flags=re.S)
    assert c is not None
    data = data.replace(c[0], b"", 1)  # uat lists P77_C after P77_D
    d_end = data.index(b"</JOB>", data.index(b'<JOB JOBISN="5"')) + len(b"</JOB>")
    data = data[:d_end] + c[0] + data[d_end:]
    data = data.replace(b'<JOB JOBISN="2"', b'<JOB JOBISN="22"')  # volatile, uat's own
    return data.replace(b"Exported at 01-01-2026", b"Exported at 05-05-2026")
