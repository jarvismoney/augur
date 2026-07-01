"""Core domain types: predictions, outcomes, and tag helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Outcome(str, Enum):
    """The resolved state of a prediction.

    ``YES``/``NO`` are the scored outcomes (the statement happened / did not).
    ``VOID`` marks a prediction that can no longer be judged (question became
    moot, ambiguous, or was withdrawn); void predictions are excluded from all
    scoring. ``OPEN`` is the unresolved default.
    """

    OPEN = "open"
    YES = "yes"
    NO = "no"
    VOID = "void"

    @property
    def is_resolved(self) -> bool:
        return self is not Outcome.OPEN

    @property
    def is_scorable(self) -> bool:
        return self in (Outcome.YES, Outcome.NO)

    @property
    def label(self) -> str:
        return {
            Outcome.OPEN: "open",
            Outcome.YES: "YES",
            Outcome.NO: "NO",
            Outcome.VOID: "void",
        }[self]

    def as_binary(self) -> int:
        """Map a scorable outcome to 1 (YES) or 0 (NO)."""
        if self is Outcome.YES:
            return 1
        if self is Outcome.NO:
            return 0
        raise ValueError(f"{self} is not a scorable outcome")


def normalize_tags(tags) -> list[str]:
    """Clean, de-duplicate, and sort a collection of tags.

    Accepts either an iterable of strings or a single comma-separated string.
    Tags are lowercased and stripped of surrounding whitespace and '#'.
    """
    if tags is None:
        return []
    if isinstance(tags, str):
        parts = tags.replace(",", " ").split()
    else:
        parts: list[str] = []
        for item in tags:
            parts.extend(str(item).replace(",", " ").split())

    seen: dict[str, None] = {}
    for part in parts:
        clean = part.strip().lstrip("#").lower()
        if clean:
            seen.setdefault(clean, None)
    return sorted(seen)


@dataclass
class Prediction:
    """A single forecast and everything known about it.

    ``probability`` is P(statement resolves YES), stored as a float in [0, 1].
    """

    statement: str
    probability: float
    created_at: datetime
    id: int | None = None
    resolve_by: datetime | None = None
    resolved_at: datetime | None = None
    outcome: Outcome = Outcome.OPEN
    tags: list[str] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError(
                f"probability must be in [0, 1], got {self.probability!r}"
            )
        self.tags = normalize_tags(self.tags)

    @property
    def is_open(self) -> bool:
        return self.outcome is Outcome.OPEN

    def is_due(self, *, now: datetime | None = None) -> bool:
        """An open prediction whose resolve-by deadline has passed."""
        from .util import now_utc

        if not self.is_open or self.resolve_by is None:
            return False
        return self.resolve_by <= (now or now_utc())

    def brier(self) -> float | None:
        """Squared error of this single forecast, or None if not scorable."""
        if not self.outcome.is_scorable:
            return None
        o = self.outcome.as_binary()
        return (self.probability - o) ** 2
