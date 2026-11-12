"""Why something is slow here: what this machine costs, and where one comparison goes.

Where every small file is costly (an antivirus that inspects each one, a network drive), a
tool that works through thousands of small files spends nearly all of its time on them. The
core no longer does: a branch comes out of git into memory, a file of the repository is opened
once and remembered until it changes. This module measures whether that holds on a machine:
the machine itself (a small file in the temporary directory and next to the repository, one
git call, plain computing) and one real comparison, phase by phase, with the files it opened
and wrote and the git calls it made.

The report holds numbers, versions and the two refs compared: no name of a job, of a folder or
of a directory, so it can be passed on.
"""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from controlm_chain_admin import __version__
from controlm_chain_admin.core import cache
from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.environments import env_branches
from controlm_chain_admin.core.errors import ChainError, GitError
from controlm_chain_admin.core.history import _git
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.core.timing import Timings, collect

#: about what one job is in the repository: a small JSON file
_PAYLOAD = json.dumps({"JOBNAME": "X" * 24, "values": ["value"] * 120}, indent=2)
#: the phases that do not overlap (git runs inside them)
_TOP_PHASES = ("snapshot", "translate", "diff")
#: a small file that costs more than this is slow: a local disk does it in a fraction of it
SLOW_FILE_MS = 2.0


def _files(place: Path, files: int) -> dict[str, Any]:
    """Milliseconds to write, read and delete one small file in a new directory of ``place``."""
    with tempfile.TemporaryDirectory(prefix="ctmchain-probe-", dir=place) as tmp:
        paths = [Path(tmp, f"{number // 100}", f"{number}.json") for number in range(files)]
        started = perf_counter()
        for path in paths:
            path.parent.mkdir(exist_ok=True)
            path.write_text(_PAYLOAD, encoding="utf-8")
        written = perf_counter()
        for path in paths:
            path.read_text(encoding="utf-8")
        read = perf_counter()
        for path in paths:
            path.unlink()
        deleted = perf_counter()
    per_file = 1000 / max(files, 1)
    return {
        "files": files,
        "write_ms": round((written - started) * per_file, 3),
        "read_ms": round((read - written) * per_file, 3),
        "delete_ms": round((deleted - read) * per_file, 3),
    }


def _git_dir(root: Path) -> Path:
    """Where git keeps the repository of ``root``: a place next to the chains that no status
    shows; ``root`` itself when it is not a git repository."""
    try:
        return Path(str(_git(root, "rev-parse", "--absolute-git-dir")).strip())
    except GitError:
        return root


def _spawn(spawns: int) -> dict[str, Any]:
    started = perf_counter()
    for _ in range(spawns):
        subprocess.run(["git", "--version"], capture_output=True, check=False)
    return {"calls": spawns, "ms": round((perf_counter() - started) * 1000 / max(spawns, 1), 2)}


def _cpu() -> dict[str, Any]:
    """A fixed piece of plain computing (JSON written and read 300 times): how fast the machine
    is when no file and no other program is involved."""
    data = {"jobs": [{"JOBNAME": f"J{number}", "values": list(range(40))} for number in range(60)]}
    started = perf_counter()
    for _ in range(300):
        json.loads(json.dumps(data, indent=2))
    return {"ms": round((perf_counter() - started) * 1000, 1)}


def machine(root: Path, *, files: int = 2000, spawns: int = 10) -> dict[str, dict[str, Any]]:
    """What this machine costs: a small file in the temporary directory (where a comparison
    works) and next to the repository, one git call, and plain computing."""
    try:
        git_spawn = _spawn(spawns)
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    return {
        "temp_files": _files(Path(tempfile.gettempdir()), files),
        "repo_files": _files(_git_dir(root), files),
        "git_spawn": git_spawn,
        "cpu": _cpu(),
    }


@dataclass(frozen=True)
class Run:
    """One real comparison, measured."""

    environments: tuple[str, str] | None
    seconds: float
    timings: Timings
    folders: Mapping[str, int]
    jobs: Mapping[str, int]
    again_seconds: float | None  # the same comparison once more, right after
    again_kept: bool = False  # that second answer came from what is kept by commit

    def to_json(self) -> dict[str, Any]:
        return {
            "environments": None if self.environments is None else list(self.environments),
            "seconds": round(self.seconds, 3),
            "again_seconds": None if self.again_seconds is None else round(self.again_seconds, 3),
            "again_kept": self.again_kept,
            "timings": self.timings.to_json(),
            "folders": dict(self.folders),
            "jobs": dict(self.jobs),
        }


@dataclass(frozen=True)
class Diagnosis:
    version: str
    platform: Mapping[str, str]
    base: str
    head: str
    probes: Mapping[str, Mapping[str, Any]]
    run: Run | None

    @property
    def files_seconds(self) -> float:
        """What the files of the comparison cost at this machine's price per small file."""
        if self.run is None:
            return 0.0
        counts, price = self.run.timings.counts, self.probes["temp_files"]
        written = counts.get("files_written", 0)  # temporary files: each one is deleted too
        cost = written * (price["write_ms"] + price["delete_ms"])
        cost += counts.get("files_read", 0) * price["read_ms"]
        return float(cost) / 1000

    @property
    def files_share(self) -> float:
        """The part of the comparison its small files explain, from 0 to 1 (an estimate)."""
        if self.run is None or self.run.seconds <= 0:
            return 0.0
        return min(1.0, self.files_seconds / self.run.seconds)

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "platform": dict(self.platform),
            "base": self.base,
            "head": self.head,
            "probes": {name: dict(probe) for name, probe in self.probes.items()},
            "run": None if self.run is None else self.run.to_json(),
            "files_seconds": round(self.files_seconds, 3),
            "files_share": round(self.files_share, 3),
        }


def _platform() -> dict[str, str]:
    try:
        git = subprocess.run(["git", "--version"], capture_output=True, check=False, text=True)
        git_version = git.stdout.strip().removeprefix("git version ")
    except FileNotFoundError:
        git_version = "not found"
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "git": git_version,
    }


def _refs(root: Path, base: str | None, head: str | None) -> tuple[str, str]:
    """The two refs to compare: the ones given, else the trunk and the first other environment
    that has a branch (the comparison that costs the most: two whole branches)."""
    if base is not None and head is not None:
        return base, head
    branches = list(env_branches(root, load_repo(root).config).values())
    if len(branches) < 2 or (base is None) != (head is None):
        raise ChainError(
            "no two environments have a branch here: name two refs to compare "
            "(ctmchain diagnose BASE HEAD)"
        )
    return branches[0], branches[1]


def _measured(root: Path, base: str, head: str) -> Run:
    started = perf_counter()
    with collect() as timings, cache.fresh():  # worked out here and now, whatever is kept
        result = compare(root, base, head)
    seconds = perf_counter() - started
    started = perf_counter()
    with collect() as second:
        compare(root, base, head)
    again = perf_counter() - started
    summary = result.summary()
    return Run(
        result.environments, seconds, timings, summary["folders"], summary["jobs"], again,
        second.counts.get("cache_hits", 0) > 0,
    )  # fmt: skip


def diagnose(
    root: Path,
    base: str | None = None,
    head: str | None = None,
    *,
    files: int = 2000,
    spawns: int = 10,
) -> Diagnosis:
    """Measure this machine and one comparison of ``base`` with ``head`` (see :func:`_refs`)."""
    base, head = _refs(root, base, head)
    probes = machine(root, files=files, spawns=spawns)
    return Diagnosis(__version__, _platform(), base, head, probes, _measured(root, base, head))


def _verdict(found: Diagnosis) -> list[str]:
    run, temp = found.run, found.probes["temp_files"]
    if run is None:
        return []
    share = round(found.files_share * 100)
    lines = [
        f"  its small files, at this machine's price: about {found.files_seconds:.1f} s, "
        f"{share}% of the comparison (an estimate)"
    ]
    slow = max(temp["write_ms"], temp["read_ms"]) >= SLOW_FILE_MS
    if slow and share >= 50:
        lines.append(
            "  Small files are slow here and they are most of the comparison: an antivirus "
            "that inspects every file, or a network drive, is the usual cause."
        )
    elif share >= 50:
        lines.append("  The files are most of the comparison, though each one is cheap here.")
    else:
        calls = run.timings.counts.get("git_calls", 0) * found.probes["git_spawn"]["ms"] / 1000
        lines.append(
            f"  The files do not explain it. Its git calls, at this machine's price: about "
            f"{calls:.1f} s; the rest is computing."
        )
    repo = found.probes["repo_files"]
    if slow and repo["write_ms"] * 3 <= temp["write_ms"]:
        lines.append(
            "  Next to the repository a small file is at least three times cheaper than in "
            "the temporary directory: the temporary directory is the slow place."
        )
    return lines


def render_text(found: Diagnosis) -> str:
    """The diagnosis for a terminal."""
    system = found.platform
    lines = [
        f"ctmchain diagnose {found.version}: Python {system['python']}, git {system['git']}, "
        f"{system['system']} {system['release']} ({system['machine']})",
        "",
        "Machine",
    ]
    places = (("temp_files", "temporary directory"), ("repo_files", "next to the repository"))
    for name, title in places:
        probe = found.probes[name]
        lines.append(
            f"  small files, {title}: write {probe['write_ms']} ms, read {probe['read_ms']} ms, "
            f"delete {probe['delete_ms']} ms each ({probe['files']} files)"
        )
    spawn, cpu = found.probes["git_spawn"], found.probes["cpu"]
    lines.append(f"  one git call: {spawn['ms']} ms (of {spawn['calls']})")
    lines.append(f"  plain computing: {cpu['ms']} ms (a fixed piece of work)")
    run = found.run
    if run is None:
        return "\n".join(lines) + "\n"
    between = "" if run.environments is None else f" ({' and '.join(run.environments)})"
    counts = run.timings.counts
    lines += [
        "",
        f"One comparison: {found.base} with {found.head}{between}",
        f"  {run.seconds:.1f} s; once more, right after: {run.again_seconds:.1f} s"
        + (" (kept by commit)" if run.again_kept else ""),
        f"  files written: {counts.get('files_written', 0)}, opened: "
        f"{counts.get('files_read', 0)}, git calls: {counts.get('git_calls', 0)}",
        "  jobs: " + ", ".join(f"{n} {kind}" for kind, n in run.jobs.items()),
        "",
        "Where the time goes (a phase inside another counts in both)",
    ]
    phases = run.timings.phases
    for name, seconds in phases.items():
        lines.append(f"  {name}: {seconds:.1f} s ({run.timings.calls.get(name, 0)}x)")
    rest = run.seconds - sum(phases.get(name, 0.0) for name in _TOP_PHASES)
    lines.append(f"  the rest: {max(rest, 0.0):.1f} s")
    lines += _verdict(found)
    return "\n".join(lines) + "\n"
