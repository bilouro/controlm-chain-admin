"""Where the time of an operation goes: named phases and counters, collected only when asked.

The core marks its expensive steps with :func:`phase` and counts what it does with
:func:`count`; both cost next to nothing until somebody collects them (:func:`collect`), which
is what ``ctmchain diagnose`` does around one real comparison.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass
class Timings:
    """Seconds by phase (in the order they first ran), how often each ran, and the counters."""

    phases: dict[str, float] = field(default_factory=dict)
    calls: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    total: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 3),
            "phases": {name: round(seconds, 3) for name, seconds in self.phases.items()},
            "calls": dict(self.calls),
            "counts": dict(self.counts),
        }


_ACTIVE: ContextVar[Timings | None] = ContextVar("ctmchain_timings", default=None)


def active() -> bool:
    """Whether somebody is collecting: for a count that costs something to work out."""
    return _ACTIVE.get() is not None


def count(name: str, number: int = 1) -> None:
    """Add ``number`` to the counter ``name`` of the collection in progress, if any."""
    seen = _ACTIVE.get()
    if seen is not None:
        seen.counts[name] = seen.counts.get(name, 0) + number


@contextmanager
def phase(name: str) -> Iterator[None]:
    """Time the block as (one more run of) the phase ``name``. A phase inside another counts
    in both: the phases say where the time goes, they do not add up to the total."""
    seen = _ACTIVE.get()
    if seen is None:
        yield
        return
    started = perf_counter()
    seen.phases.setdefault(name, 0.0)
    try:
        yield
    finally:
        seen.phases[name] += perf_counter() - started
        seen.calls[name] = seen.calls.get(name, 0) + 1


@contextmanager
def collect() -> Iterator[Timings]:
    """Collect the phases and counters of everything the block runs."""
    seen = Timings()
    token = _ACTIVE.set(seen)
    started = perf_counter()
    try:
        yield seen
    finally:
        seen.total = perf_counter() - started
        _ACTIVE.reset(token)
