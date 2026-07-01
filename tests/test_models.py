"""Tests for domain models."""

from datetime import datetime, timedelta, timezone

import pytest

from augur.models import Outcome, Prediction, normalize_tags

NOW = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)


def test_outcome_properties():
    assert Outcome.OPEN.is_resolved is False
    assert Outcome.YES.is_resolved is True
    assert Outcome.YES.is_scorable is True
    assert Outcome.VOID.is_scorable is False
    assert Outcome.YES.as_binary() == 1
    assert Outcome.NO.as_binary() == 0
    with pytest.raises(ValueError):
        Outcome.VOID.as_binary()


def test_normalize_tags_dedupes_and_sorts():
    assert normalize_tags("Crypto, macro #crypto") == ["crypto", "macro"]
    assert normalize_tags(["A", "b", "a"]) == ["a", "b"]
    assert normalize_tags(None) == []
    assert normalize_tags("") == []


def test_prediction_validates_probability():
    with pytest.raises(ValueError):
        Prediction(statement="x", probability=1.5, created_at=NOW)
    with pytest.raises(ValueError):
        Prediction(statement="x", probability=-0.1, created_at=NOW)


def test_prediction_brier_only_for_scorable():
    p = Prediction(statement="x", probability=0.8, created_at=NOW, outcome=Outcome.YES)
    assert p.brier() == pytest.approx((0.8 - 1) ** 2)
    p2 = Prediction(statement="x", probability=0.8, created_at=NOW)
    assert p2.brier() is None


def test_prediction_is_due():
    past = NOW - timedelta(days=1)
    future = NOW + timedelta(days=1)
    overdue = Prediction(statement="x", probability=0.5, created_at=NOW, resolve_by=past)
    pending = Prediction(statement="x", probability=0.5, created_at=NOW, resolve_by=future)
    assert overdue.is_due(now=NOW) is True
    assert pending.is_due(now=NOW) is False
    # Resolved predictions are never "due".
    overdue.outcome = Outcome.YES
    assert overdue.is_due(now=NOW) is False
