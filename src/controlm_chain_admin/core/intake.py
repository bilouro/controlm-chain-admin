"""Which environment an export is of: told by the letter its folder and job names carry.

(Until 0.4 this module also took an export into a repository that keeps every environment in
one tree, ``receive``; with one branch per environment an export is a ``refresh``.)
"""

from __future__ import annotations

import re
from collections import Counter

from controlm_chain_admin.core.model import XmlDocument
from controlm_chain_admin.core.ops import JOB_TAG, only_application
from controlm_chain_admin.core.repo import ChainRepo

_NAME_ATTRIBUTES = ("FOLDER_NAME", "JOBNAME")


def detect_env(repo: ChainRepo, document: XmlDocument) -> tuple[str | None, tuple[str, ...]]:
    """The environment whose letter every folder and job name carries, and the evidence."""
    rule = repo.config.letter_rule
    if not rule.enabled:
        return None, ("the letter rule is off: names do not tell the environment",)
    letters = repo.env_letters()
    by_letter = {letter: env for env, letter in letters.items()}
    prefixes = "|".join(re.escape(p) for p in sorted(rule.prefixes, key=len, reverse=True))
    pattern = re.compile(rf"([A-Z])(?:{prefixes})")
    counts: Counter[str] = Counter()
    for folder in only_application(document, repo.config.application).root.elements():
        for element in (folder, *folder.find_all(JOB_TAG)):
            for attribute in _NAME_ATTRIBUTES:
                match = pattern.match(element.get(attribute) or "")
                if match and match[1] in by_letter:
                    counts[by_letter[match[1]]] += 1
    if not counts:
        return None, ("no folder or job name carries an environment letter",)
    evidence = tuple(
        f"{n} folder and job names carry the letter {letters[env]} of {env}"
        for env, n in counts.most_common()
    )
    return (next(iter(counts)) if len(counts) == 1 else None), evidence
