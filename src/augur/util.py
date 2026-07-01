"""Small standalone helpers: dates, paths, and probability parsing.

Kept dependency-free and side-effect-free so the rest of the package (and the
tests) can rely on them without pulling in the database or CLI layers.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def default_db_path() -> Path:
    """Return the default location of the augur database.

    Honours ``AUGUR_DB`` for an explicit override, otherwise follows the XDG
    Base Directory spec (``XDG_DATA_HOME`` or ``~/.local/share``). The parent
    directory is *not* created here; that is the storage layer's job.
    """
    override = os.environ.get("AUGUR_DB")
    if override:
        return Path(override).expanduser()

    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "augur" / "augur.db"


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def now_utc() -> datetime:
    """Timezone-aware current time in UTC."""
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """Serialize a datetime to an ISO-8601 UTC string (seconds precision)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def from_iso(s: str) -> datetime:
    """Parse an ISO-8601 string back into a timezone-aware UTC datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class DateParseError(ValueError):
    """Raised when a user-supplied date string cannot be understood."""


def parse_date(text: str, *, now: datetime | None = None) -> datetime:
    """Parse a human-friendly date/deadline into a UTC datetime.

    Accepts:
      * ISO dates and datetimes: ``2026-12-31``, ``2026-12-31T09:00``
      * ``today`` / ``tomorrow`` / ``yesterday``
      * relative offsets: ``+7d``, ``+2w``, ``+3m``, ``+1y`` (also ``-`` for past)

    A bare date is anchored to the *end* of that day (23:59:59 UTC) so a
    "resolve by 2026-12-31" deadline includes all of the 31st.
    """
    now = now or now_utc()
    raw = text.strip().lower()
    if not raw:
        raise DateParseError("empty date")

    if raw in ("today", "now"):
        return now
    if raw == "tomorrow":
        return _end_of_day(now + timedelta(days=1))
    if raw == "yesterday":
        return _end_of_day(now - timedelta(days=1))

    if raw[0] in "+-" and len(raw) >= 3:
        sign = 1 if raw[0] == "+" else -1
        unit = raw[-1]
        try:
            amount = int(raw[1:-1])
        except ValueError as exc:
            raise DateParseError(f"cannot parse relative date {text!r}") from exc
        amount *= sign
        if unit == "d":
            return _end_of_day(now + timedelta(days=amount))
        if unit == "w":
            return _end_of_day(now + timedelta(weeks=amount))
        if unit == "m":
            return _end_of_day(_add_months(now, amount))
        if unit == "y":
            return _end_of_day(_add_months(now, amount * 12))
        raise DateParseError(f"unknown relative unit {unit!r} in {text!r}")

    # Fall back to ISO parsing. Bare dates get anchored to end-of-day.
    try:
        parsed = datetime.fromisoformat(text.strip())
    except ValueError as exc:
        raise DateParseError(
            f"cannot parse date {text!r}; try YYYY-MM-DD, 'tomorrow', or '+7d'"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    # If the caller gave only a date (no time component), anchor to end of day.
    if len(text.strip()) <= 10:
        parsed = _end_of_day(parsed)
    return parsed


def _end_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    """Add calendar months, clamping the day to the target month's length."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, _days_in_month(year, month))
    return dt.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def humanize_delta(dt: datetime, *, now: datetime | None = None) -> str:
    """Render a datetime relative to now, e.g. ``in 3d`` or ``5d ago``."""
    now = now or now_utc()
    delta = dt - now
    seconds = delta.total_seconds()
    future = seconds >= 0
    seconds = abs(seconds)

    if seconds < 90:
        label = "just now" if not future else "now"
        return label
    minutes = seconds / 60
    if minutes < 90:
        value, unit = round(minutes), "m"
    elif minutes < 60 * 36:
        value, unit = round(minutes / 60), "h"
    elif minutes < 60 * 24 * 21:
        value, unit = round(minutes / (60 * 24)), "d"
    elif minutes < 60 * 24 * 365:
        value, unit = round(minutes / (60 * 24 * 7)), "w"
    else:
        value, unit = round(minutes / (60 * 24 * 365), 1), "y"

    return f"in {value}{unit}" if future else f"{value}{unit} ago"


# ---------------------------------------------------------------------------
# Probabilities
# ---------------------------------------------------------------------------


class ProbabilityError(ValueError):
    """Raised when a probability string is malformed or out of range."""


def parse_probability(text: str) -> float:
    """Parse a probability given as a percent or a fraction.

    ``"35"`` and ``"35%"`` -> 0.35, ``"0.35"`` -> 0.35, ``"90"`` -> 0.90.
    Values in ``(1, 100]`` are treated as percentages; ``[0, 1]`` as fractions.
    A leading ``%`` or trailing ``%`` is stripped either way.
    """
    raw = text.strip().rstrip("%").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ProbabilityError(f"not a number: {text!r}") from exc

    if value < 0:
        raise ProbabilityError("probability cannot be negative")
    if value > 100:
        raise ProbabilityError("probability cannot exceed 100%")
    if value > 1:
        value /= 100.0
    return value


def format_probability(p: float) -> str:
    """Render a probability in [0,1] as a compact percentage string."""
    pct = p * 100
    if abs(pct - round(pct)) < 1e-9:
        return f"{round(pct)}%"
    return f"{pct:.1f}%"
