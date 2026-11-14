"""The steps of a preview, kept by its ``preview_id``.

An assistant that runs one command per tool (``python -m ctmadmin_service``) previews a change
in one command and applies it in another: the second gives the id alone, and the steps come
back from here. The id is still the fingerprint of the change, checked again when it is
applied, so a repository that moved meanwhile refuses it. They are kept in the git directory
(nothing shows in the working tree), only the last :data:`KEEP`.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.errors import ChainError

#: previews kept at most: the oldest go
KEEP = 50
DIRECTORY = "ctmchain-previews"
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _directory(root: Path) -> Path:
    """Inside the git directory of ``root``; without git, in the temporary directory, by
    repository."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--absolute-git-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # no git on this machine
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()) / DIRECTORY
    named = sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / DIRECTORY / named


def _path(root: Path, preview_id: str) -> Path:
    if not _ID.fullmatch(preview_id):
        raise ChainError(f"{preview_id!r} is not a preview id: give the one preview returned")
    return _directory(root) / f"{preview_id}.json"


def remember(root: Path, preview_id: str, steps: Sequence[Mapping[str, Any]]) -> None:
    """Keep the steps previewed as ``preview_id``; the oldest beyond :data:`KEEP` go."""
    path = _path(root, preview_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(steps), ensure_ascii=False), "utf-8")
    kept = sorted(path.parent.glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for old in kept[KEEP:]:
        old.unlink(missing_ok=True)


def recall(root: Path, preview_id: str) -> list[dict[str, Any]]:
    """The steps previewed as ``preview_id``."""
    path = _path(root, preview_id)
    try:
        steps = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ChainError(
            f"no preview {preview_id} here (too old, or of another repository): preview again"
        ) from exc
    return list(steps)
