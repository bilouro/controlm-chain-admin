"""Where the edits go: release branches from the trunk, their installations, closing them.

The trunk (``main``) mirrors production and is never edited, nor any other protected branch.
Work happens on a release branch (``release/<name>``) started from the trunk: edit, commit,
install the release in one environment after the other (each installation is an annotated tag
``<env>/<name>-<n>`` on the installed commit) and, once its last commit is installed in
production, close it: the release is merged into the trunk and its branch deleted. Names come
from the ``git`` key of ``chain.json`` (:class:`~controlm_chain_admin.core.repo.GitRules`).

Uncommitted chain files never travel silently: starting or switching a release with them is
refused unless they are stashed first, and a stash is restored on a branch that may be edited.
Push and pull use the user's own git credentials and never prompt.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.commit import pending, restore
from controlm_chain_admin.core.errors import (
    GitError,
    MergeConflict,
    NothingToCommit,
    ProtectedBranch,
    UncommittedChanges,
    UnknownEnvironment,
)
from controlm_chain_admin.core.history import _git, chain_changes, full_sha
from controlm_chain_admin.core.repo import ChainRepo, GitRules

_PATHS = ("chain.json", "folders", "meta", "envs")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_STASH = re.compile(r"(?:WIP on|On) ([^:]+): (.*)")
_SEP = "\x1f"
_NETWORK_TIMEOUT = 120  # seconds


@dataclass(frozen=True)
class Installation:
    """The latest installation of a release in one environment."""

    env: str
    tag: str
    sha: str
    behind: int  # commits of the release after the installed one

    def to_json(self) -> dict[str, Any]:
        return {"env": self.env, "tag": self.tag, "sha": self.sha, "behind": self.behind}


@dataclass(frozen=True)
class Release:
    name: str
    branch: str
    sha: str
    local: bool
    remote: bool
    ahead: int  # commits the trunk does not have
    trunk_behind: int  # trunk commits the release does not have
    installed: tuple[Installation, ...]  # in the order of the environments
    closable: bool  # last commit installed in production, nothing of the trunk missing

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "branch": self.branch,
            "sha": self.sha,
            "local": self.local,
            "remote": self.remote,
            "ahead": self.ahead,
            "trunk_behind": self.trunk_behind,
            "installed": [i.to_json() for i in self.installed],
            "closable": self.closable,
        }


@dataclass(frozen=True)
class Stash:
    ref: str  # stash@{n}
    branch: str | None  # where it was made
    message: str

    def to_json(self) -> dict[str, Any]:
        return {"ref": self.ref, "branch": self.branch, "message": self.message}


@dataclass(frozen=True)
class Workspace:
    """Where the repository stands: the branch, whether it may be edited, releases, stashes."""

    branch: str | None  # None when detached
    head: str
    trunk: str
    prefix: str
    editable: bool
    reason: str | None  # why edits are refused
    release: str | None  # name of the checked-out release
    changes: int  # uncommitted chain files
    releases: tuple[Release, ...]
    stashes: tuple[Stash, ...]
    environments: tuple[str, ...]
    production: str
    remote: str | None  # None when the configured remote does not exist
    upstream: str | None
    ahead: int  # commits not pushed to the upstream
    behind: int  # commits of the upstream not here (as of the last fetch)

    def to_json(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "head": self.head,
            "trunk": self.trunk,
            "prefix": self.prefix,
            "editable": self.editable,
            "reason": self.reason,
            "release": self.release,
            "changes": self.changes,
            "releases": [r.to_json() for r in self.releases],
            "stashes": [s.to_json() for s in self.stashes],
            "environments": list(self.environments),
            "production": self.production,
            "remote": self.remote,
            "upstream": self.upstream,
            "ahead": self.ahead,
            "behind": self.behind,
        }


# ---------------------------------------------------------------- git helpers


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _out(root: Path, *args: str) -> str:
    return str(_git(root, *args)).strip()


def _ok(root: Path, *args: str) -> bool:
    try:
        _git(root, *args)
    except GitError:
        return False
    return True


def _branch(root: Path) -> str | None:
    try:
        return _out(root, "symbolic-ref", "-q", "--short", "HEAD")
    except GitError:
        return None  # detached


def _exists(root: Path, ref: str) -> bool:
    return _ok(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")


def _count(root: Path, spec: str) -> int:
    return int(_out(root, "rev-list", "--count", spec))


def _ancestor(root: Path, commit: str, of: str) -> bool:
    return _ok(root, "merge-base", "--is-ancestor", commit, of)


def _remote(root: Path, rules: GitRules) -> str | None:
    return rules.remote if rules.remote in _out(root, "remote").split() else None


def _require_remote(root: Path, rules: GitRules) -> str:
    remote = _remote(root, rules)
    if remote is None:
        raise GitError(f"no remote {rules.remote!r}: add one with git remote add {rules.remote}")
    return remote


def _network(root: Path, *args: str) -> None:
    """A git command that talks to the remote: never prompts, gives up after a while."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if "GIT_SSH_COMMAND" not in env and not _ok(root, "config", "core.sshCommand"):
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=_NETWORK_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]}: no answer after {_NETWORK_TIMEOUT} s") from exc
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    if result.returncode != 0:
        raise GitError(f"git {args[0]}: {result.stderr.strip() or 'failed'}")


def _unmerged(root: Path) -> tuple[str, ...]:
    out = _out(root, "diff", "--name-only", "--diff-filter=U", "--relative")
    return tuple(sorted(filter(None, out.splitlines())))


def _tag_pattern(rules: GitRules) -> re.Pattern[str]:
    groups = {
        "{env}": r"(?P<env>[^/]+?)",
        "{release}": rf"(?P<release>{_NAME.pattern})",
        "{n}": r"(?P<n>[0-9]+)",
    }
    parts = re.split(r"(\{env\}|\{release\}|\{n\})", rules.tag_format)
    return re.compile("".join(groups.get(p, re.escape(p)) for p in parts))


def _tags(root: Path, rules: GitRules) -> dict[tuple[str, str], list[tuple[int, str, str]]]:
    """(release, env) -> [(n, tag, commit sha)] for every installation tag."""
    pattern = _tag_pattern(rules)
    fmt = _SEP.join(("%(refname:strip=2)", "%(objectname)", "%(*objectname)"))
    found: dict[tuple[str, str], list[tuple[int, str, str]]] = {}
    for line in _out(root, "for-each-ref", f"--format={fmt}", "refs/tags").splitlines():
        tag, sha, peeled = [*line.split(_SEP), "", ""][:3]
        match = pattern.fullmatch(tag)
        if match:
            key = (match["release"], match["env"])
            found.setdefault(key, []).append((int(match["n"]), tag, peeled or sha))
    return found


def _installations(
    root: Path, name: str, tip: str, envs: tuple[str, ...], tags: dict[Any, Any]
) -> tuple[Installation, ...]:
    result = []
    for env in envs:
        marks = tags.get((name, env))
        if marks:
            _, tag, sha = max(marks)
            result.append(Installation(env, tag, sha, _count(root, f"{sha}..{tip}")))
    return tuple(result)


def _leave(root: Path, stash_first: bool) -> str | None:
    """Make sure nothing uncommitted is left behind: refuse, or stash when asked."""
    changes = chain_changes(root)
    if not changes:
        return None
    if not stash_first:
        raise UncommittedChanges(
            f"{_plural(changes, 'uncommitted chain file')} on {_branch(root) or 'HEAD'}: "
            "commit, stash or discard them first",
            changes,
        )
    return _stash(root)


def _stash(root: Path) -> str:
    changes = chain_changes(root)
    if not changes:
        raise NothingToCommit("nothing to stash: the chain files have no change")
    subject = pending(root).message.splitlines()[0]
    paths = [p for p in _PATHS if (root / p).exists() or _out(root, "ls-files", "--", p)]
    _git(root, "stash", "push", "-q", "--include-untracked", "-m", subject, "--", *paths)
    return f"Stashed {_plural(changes, 'chain file')} of {_branch(root) or 'HEAD'} ({subject})"


def _stashes(root: Path) -> tuple[Stash, ...]:
    out = _out(root, "stash", "list", f"--format=%gd{_SEP}%gs")
    stashes = []
    for line in filter(None, out.splitlines()):
        ref, _, subject = line.partition(_SEP)
        match = _STASH.fullmatch(subject)
        stashes.append(Stash(ref, match[1], match[2]) if match else Stash(ref, None, subject))
    return tuple(stashes)


def _current_release(rules: GitRules, branch: str | None) -> str | None:
    if branch and branch.startswith(rules.release_prefix):
        name = branch[len(rules.release_prefix) :]
        return name if _NAME.fullmatch(name) else None
    return None


# ---------------------------------------------------------------- state


def workspace(repo: ChainRepo) -> Workspace:
    """The checked-out branch, whether it may be edited, every release with its installations."""
    root, rules = repo.root, repo.config.git_rules
    envs = repo.config.environments
    branch = _branch(root)
    head = _out(root, "rev-parse", "HEAD")
    remote = _remote(root, rules)
    trunk = rules.trunk if _exists(root, f"refs/heads/{rules.trunk}") else None
    tags = _tags(root, rules)
    local: dict[str, str] = {}
    remote_only: dict[str, str] = {}
    fmt = f"%(refname){_SEP}%(objectname)"
    listing = _out(root, "for-each-ref", f"--format={fmt}", "refs/heads", "refs/remotes")
    heads, remotes = "refs/heads/" + rules.release_prefix, f"refs/remotes/{remote}/"
    for line in listing.splitlines():
        ref, _, sha = line.partition(_SEP)
        if ref.startswith(heads):
            local[ref[len("refs/heads/") :]] = sha
        elif remote and ref.startswith(remotes + rules.release_prefix):
            remote_only[ref[len(remotes) :]] = sha
    releases = []
    for name in sorted({*local, *remote_only}):
        release = _current_release(rules, name)
        if release is None:
            continue
        tip = local.get(name) or remote_only[name]
        if name not in local and trunk and _ancestor(root, tip, trunk):
            continue  # closed: merged into the trunk, only its remote branch is left
        installed = _installations(root, release, tip, envs, tags)
        behind = _count(root, f"{tip}..{trunk}") if trunk else 0
        production = next((i for i in installed if i.env == rules.production), None)
        releases.append(
            Release(
                release, name, tip, name in local, name in remote_only,
                _count(root, f"{trunk}..{tip}") if trunk else 0, behind, installed,
                name in local and behind == 0 and production is not None
                and production.behind == 0,
            )
        )  # fmt: skip
    upstream, ahead, behind = None, 0, 0
    if branch and _ok(root, "rev-parse", "--verify", "--quiet", "@{u}"):
        upstream = _out(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        ahead, behind = (int(n) for n in _out(root, "rev-list", "--left-right", "--count",
                                              "HEAD...@{u}").split())  # fmt: skip
    reason = rules.refusal(branch)
    return Workspace(
        branch, head, rules.trunk, rules.release_prefix, reason is None, reason,
        _current_release(rules, branch), chain_changes(root), tuple(releases), _stashes(root),
        envs, rules.production, remote, upstream, ahead, behind,
    )  # fmt: skip


def ensure_editable(repo: ChainRepo) -> None:
    """Refuse to write on a protected branch or a detached HEAD; outside git anything goes."""
    if not _ok(repo.root, "rev-parse", "--is-inside-work-tree"):
        return
    reason = repo.config.git_rules.refusal(_branch(repo.root))
    if reason:
        raise ProtectedBranch(reason)


# ---------------------------------------------------------------- actions


def start_release(repo: ChainRepo, name: str, *, stash: bool = False) -> str:
    """Create ``<prefix><name>`` from the trunk and check it out."""
    root, rules = repo.root, repo.config.git_rules
    branch = rules.release_prefix + name
    if not _NAME.fullmatch(name) or not _ok(root, "check-ref-format", "--branch", branch):
        raise GitError(
            f"invalid release name {name!r}: letters, digits, '.', '_' and '-', not first"
        )
    if _exists(root, f"refs/heads/{branch}"):
        raise GitError(f"{branch} already exists: switch to it")
    if not _exists(root, f"refs/heads/{rules.trunk}"):
        raise GitError(f"the trunk branch {rules.trunk} does not exist")
    saved = _leave(root, stash)
    _git(root, "switch", "-q", "-c", branch, rules.trunk)
    done = f"Started {branch} from {rules.trunk}"
    return f"{saved}. {done}" if saved else done


def switch(repo: ChainRepo, branch: str, *, stash: bool = False) -> str:
    """Check out another branch, local or only on the remote (then tracked)."""
    root, rules = repo.root, repo.config.git_rules
    if branch == _branch(root):
        raise GitError(f"already on {branch}")
    remote = _remote(root, rules)
    local = _exists(root, f"refs/heads/{branch}")
    if not local and not (remote and _exists(root, f"refs/remotes/{remote}/{branch}")):
        raise GitError(f"unknown branch {branch!r}")
    saved = _leave(root, stash)
    if local:
        _git(root, "switch", "-q", branch)
    else:
        _git(root, "switch", "-q", "-c", branch, "--track", f"{remote}/{branch}")
    done = f"Switched to {branch}"
    return f"{saved}. {done}" if saved else done


def stash(repo: ChainRepo) -> str:
    """Put the uncommitted chain files aside (new files too)."""
    return _stash(repo.root)


def pop(repo: ChainRepo, ref: str) -> str:
    """Restore a stash on the checked-out branch and drop it; a conflict changes nothing."""
    root = repo.root
    ensure_editable(repo)
    found = next((s for s in _stashes(root) if s.ref == ref), None)
    if found is None:
        raise GitError(f"unknown stash {ref!r}")
    _leave(root, False)
    branch = _branch(root)
    try:
        _git(root, "stash", "apply", "-q", ref)
    except GitError as exc:
        paths = _unmerged(root)
        restore(root)
        raise MergeConflict(
            f"{ref} does not apply on {branch}: {', '.join(paths) or 'conflicting changes'} "
            "changed since; the stash is kept",
            paths,
        ) from exc
    _git(root, "stash", "drop", "-q", ref)
    return f"Restored {ref} on {branch} ({found.message})"


def _release_branch(repo: ChainRepo, release: str | None) -> tuple[str, str]:
    rules = repo.config.git_rules
    name = release or _current_release(rules, _branch(repo.root))
    if name is None:
        raise GitError("not on a release: switch to one or name it")
    branch = rules.release_prefix + name
    if not _exists(repo.root, f"refs/heads/{branch}"):
        raise GitError(f"unknown release {name!r}")
    return name, branch


def mark_installed(
    repo: ChainRepo, env: str, release: str | None = None, sha: str | None = None
) -> Installation:
    """Record that ``sha`` (default: the tip) of a release is installed in ``env``: a tag."""
    root, rules = repo.root, repo.config.git_rules
    name, branch = _release_branch(repo, release)
    if env not in repo.config.environments:
        known = ", ".join(repo.config.environments) or "none"
        raise UnknownEnvironment(f"unknown environment {env!r}; known: {known}")
    commit = full_sha(root, sha or branch)
    trunk = rules.trunk
    if commit == full_sha(root, trunk) and sha is None:
        raise GitError(f"{branch} has no commit of its own yet: commit the changes first")
    if not _ancestor(root, commit, branch) or _ancestor(root, commit, trunk):
        raise GitError(f"{commit[:7]} is not a commit of {branch}")
    marks = _tags(root, rules).get((name, env), [])
    if marks:
        _, last_tag, last_sha = max(marks)
        if last_sha == commit:
            raise GitError(f"{env} already has {branch} at {commit[:7]} ({last_tag})")
    number = max((n for n, _, _ in marks), default=0) + 1
    tag = rules.tag_format.format(env=env, release=name, n=number)
    if not _ok(root, "check-ref-format", f"refs/tags/{tag}"):
        raise GitError(f"invalid tag name {tag!r}: check git.tag_format in chain.json")
    _git(root, "tag", "-a", tag, commit, "-m", f"Installed {branch} in {env}")
    return Installation(env, tag, commit, _count(root, f"{commit}..{branch}"))


def _on_release(repo: ChainRepo) -> tuple[str, str]:
    """(name, branch) of the checked-out release, which has no uncommitted chain file."""
    name, branch = _release_branch(repo, None)
    ensure_editable(repo)
    _leave(repo.root, False)
    return name, branch


def update_from_trunk(repo: ChainRepo) -> str:
    """Merge the trunk into the checked-out release (what other releases put in production)."""
    root, trunk = repo.root, repo.config.git_rules.trunk
    ensure_editable(repo)
    branch = _branch(root) or "HEAD"
    _leave(root, False)
    missing = _count(root, f"HEAD..{trunk}")
    if not missing:
        raise GitError(f"{branch} already has every commit of {trunk}")
    try:
        _git(root, "merge", "-q", "--no-ff", "--no-edit", "-m", f"Merge {trunk} into {branch}",
             trunk)  # fmt: skip
    except GitError as exc:
        paths = _unmerged(root)
        _ok(root, "merge", "--abort")
        if not paths:
            raise
        raise MergeConflict(
            f"{trunk} does not merge into {branch}: {', '.join(paths)} changed on both; "
            "nothing was changed",
            paths,
        ) from exc
    return f"Merged {_plural(missing, 'commit')} of {trunk} into {branch}"


def close_release(repo: ChainRepo) -> str:
    """Merge the checked-out release into the trunk, once its last commit is in production."""
    root, rules = repo.root, repo.config.git_rules
    name, branch = _on_release(repo)
    trunk, production = rules.trunk, rules.production
    head = _out(root, "rev-parse", "HEAD")
    installed = _installations(root, name, head, repo.config.environments, _tags(root, rules))
    last = next((i for i in installed if i.env == production), None)
    if last is None or last.behind:
        raise GitError(
            f"the last commit of {branch} is not installed in {production}: install it and mark "
            "it as installed first"
        )
    missing = _count(root, f"HEAD..{trunk}")
    if missing:
        raise GitError(
            f"{trunk} has {_plural(missing, 'commit')} that {branch} does not have: update the "
            f"release from {trunk}, install it in {production} again, then close it"
        )
    base = _out(root, "rev-parse", trunk)
    with tempfile.TemporaryDirectory(prefix="ctmchain-close-") as tmp:
        note = Path(tmp) / "message.txt"
        note.write_text(
            f"Merge {branch} into {trunk}\n\nInstalled: {', '.join(i.tag for i in installed)}\n",
            encoding="utf-8",
            newline="\n",
        )
        merge = _out(root, "commit-tree", "HEAD^{tree}", "-p", base, "-p", head, "-F", str(note))
    _git(root, "update-ref", f"refs/heads/{trunk}", merge, base)
    _git(root, "switch", "-q", trunk)  # same tree: no file changes
    _git(root, "branch", "-q", "-d", branch)
    return f"Closed {branch}: merged into {trunk} ({merge[:7]})"


def push(repo: ChainRepo) -> str:
    """Push the checked-out branch and its installation tags; after closing, tidy the remote."""
    root, rules = repo.root, repo.config.git_rules
    remote = _require_remote(root, rules)
    branch = _branch(root)
    if branch is None:
        raise GitError("HEAD is detached: switch to a branch to push")
    _network(root, "push", "-q", "--follow-tags", "-u", remote, branch)
    deleted = []
    if branch == rules.trunk:
        state = workspace(repo)
        known = {r.branch for r in state.releases}
        prefix = f"refs/remotes/{remote}/{rules.release_prefix}"
        tags = _tags(root, rules)
        for line in _out(root, "for-each-ref", "--format=%(refname)", prefix).splitlines():
            name = line[len(f"refs/remotes/{remote}/") :]
            release = _current_release(rules, name)
            if release is None or name in known or _exists(root, f"refs/heads/{name}"):
                continue
            tip = _out(root, "rev-parse", line)
            marks = tags.get((release, rules.production), [])
            if _ancestor(root, tip, branch) and any(sha == tip for _, _, sha in marks):
                _network(root, "push", "-q", remote, "--delete", name)
                deleted.append(name)
    done = f"Pushed {branch} to {remote}"
    if deleted:
        done += f"; deleted the closed {', '.join(deleted)} on {remote}"
    return done


def _fast_forward(root: Path, branch: str, target: str, *, checked_out: bool) -> str | None:
    """Move ``branch`` to ``target`` when that only adds commits; None when already there."""
    new = _count(root, f"{branch}..{target}")
    if not new:
        return None
    if not _ancestor(root, branch, target):
        raise GitError(
            f"{branch} and {target} have diverged: merge or rebase them with git, then pull"
        )
    if checked_out:
        _git(root, "merge", "-q", "--ff-only", target)
    else:
        _git(root, "update-ref", f"refs/heads/{branch}", target, _out(root, "rev-parse", branch))
    return f"{branch}: fast-forwarded {_plural(new, 'commit')}"


def pull(repo: ChainRepo) -> str:
    """Fetch the remote, then fast-forward the checked-out branch and the trunk."""
    root, rules = repo.root, repo.config.git_rules
    remote = _require_remote(root, rules)
    _network(root, "fetch", "-q", "--prune", "--tags", remote)
    branch = _branch(root)
    done = [f"Fetched {remote}"]
    if branch and _ok(root, "rev-parse", "--verify", "--quiet", "@{u}"):
        upstream = _out(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        moved = _fast_forward(root, branch, upstream, checked_out=True)
        done.append(moved or f"{branch}: up to date")
    trunk, remote_trunk = rules.trunk, f"{remote}/{rules.trunk}"
    if (
        branch != trunk
        and _exists(root, f"refs/heads/{trunk}")
        and _exists(root, f"refs/remotes/{remote_trunk}")
    ):
        moved = _fast_forward(root, trunk, remote_trunk, checked_out=False)
        if moved:
            done.append(moved)
    return ". ".join(done)
