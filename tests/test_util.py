"""Tests for parsing and formatting helpers."""

from datetime import datetime, timezone

import pytest

from augur.util import (
    DateParseError,
    ProbabilityError,
    default_db_path,
    format_probability,
    humanize_delta,
    parse_date,
    parse_probability,
)

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("35", 0.35),
        ("35%", 0.35),
        ("0.35", 0.35),
        ("90", 0.90),
        ("100", 1.0),
        ("1", 1.0),
        ("0", 0.0),
        ("0.5", 0.5),
        (" 50 % ", 0.5),
    ],
)
def test_parse_probability_ok(text, expected):
    assert parse_probability(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["-1", "101", "abc", ""])
def test_parse_probability_errors(text):
    with pytest.raises(ProbabilityError):
        parse_probability(text)


def test_format_probability():
    assert format_probability(0.35) == "35%"
    assert format_probability(0.925) == "92.5%"
    assert format_probability(1.0) == "100%"


def test_parse_date_iso_anchors_to_end_of_day():
    d = parse_date("2026-12-31", now=NOW)
    assert (d.year, d.month, d.day) == (2026, 12, 31)
    assert (d.hour, d.minute, d.second) == (23, 59, 59)


def test_parse_date_relative_days():
    d = parse_date("+7d", now=NOW)
    assert d.day == 8 and d.month == 7
    assert d.hour == 23  # end of day


def test_parse_date_relative_months_and_years():
    assert parse_date("+1m", now=NOW).month == 8
    assert parse_date("+1y", now=NOW).year == 2027


def test_parse_date_keywords():
    assert parse_date("today", now=NOW) == NOW
    assert parse_date("tomorrow", now=NOW).day == 2
    assert parse_date("yesterday", now=NOW).day == 30


def test_parse_date_month_end_clamp():
    # Jan 31 + 1 month should clamp to Feb 28 (2026 is not a leap year).
    jan31 = datetime(2026, 1, 31, 12, tzinfo=timezone.utc)
    d = parse_date("+1m", now=jan31)
    assert (d.month, d.day) == (2, 28)


def test_parse_date_bad():
    with pytest.raises(DateParseError):
        parse_date("not-a-date", now=NOW)


def test_humanize_delta_future_and_past():
    future = datetime(2026, 7, 4, 12, tzinfo=timezone.utc)
    past = datetime(2026, 6, 28, 12, tzinfo=timezone.utc)
    assert "in" in humanize_delta(future, now=NOW)
    assert "ago" in humanize_delta(past, now=NOW)


def test_default_db_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("AUGUR_DB", str(target))
    assert default_db_path() == target
