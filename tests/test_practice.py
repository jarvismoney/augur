"""Tests for the practice drills and question bank."""

import random

import pytest

from augur import calibration_bank as bank
from augur import practice


def test_bank_is_nonempty_and_well_formed():
    assert len(bank.NUMERIC) >= 20
    assert len(bank.BINARY) >= 20
    for q in bank.NUMERIC:
        assert q.prompt.strip()
        assert isinstance(q.answer, (int, float))
    for q in bank.BINARY:
        assert q.prompt.strip()
        assert isinstance(q.answer, bool)


def test_sample_is_seeded_and_bounded():
    a = practice.sample_numeric(5, rng=random.Random(1))
    b = practice.sample_numeric(5, rng=random.Random(1))
    assert [q.prompt for q in a] == [q.prompt for q in b]  # reproducible
    # Requesting more than exist just returns everything.
    everything = practice.sample_numeric(9999, rng=random.Random(1))
    assert len(everything) == len(bank.NUMERIC)


def test_score_interval_hit_and_order_normalisation():
    q = bank.NumericQuestion("q", answer=100)
    assert practice.score_interval(q, 90, 110).hit is True
    assert practice.score_interval(q, 110, 90).hit is True  # swapped bounds
    assert practice.score_interval(q, 200, 300).hit is False


def test_interval_report_coverage():
    q = bank.NumericQuestion("q", answer=100)
    results = [
        practice.score_interval(q, 90, 110),   # hit
        practice.score_interval(q, 90, 110),   # hit
        practice.score_interval(q, 0, 1),      # miss
    ]
    report = practice.interval_report(results, target=0.9)
    assert report.hits == 2
    assert report.n == 3
    assert report.coverage == pytest.approx(2 / 3)


def test_score_confidence_maps_probability():
    q_true = bank.BinaryQuestion("q", answer=True)
    q_false = bank.BinaryQuestion("q", answer=False)

    r = practice.score_confidence(q_true, said_true=True, confidence=0.8)
    assert r.prob_true == pytest.approx(0.8)
    assert r.correct is True
    assert r.pair == (0.8, 1)

    r2 = practice.score_confidence(q_false, said_true=True, confidence=0.9)
    assert r2.prob_true == pytest.approx(0.9)
    assert r2.correct is False
    assert r2.pair == (0.9, 0)

    # Saying "false, 70%" means P(true) = 0.30.
    r3 = practice.score_confidence(q_true, said_true=False, confidence=0.7)
    assert r3.prob_true == pytest.approx(0.3)
    assert r3.correct is False


def test_score_confidence_clamps_confidence():
    q = bank.BinaryQuestion("q", answer=True)
    assert practice.score_confidence(q, True, 0.2).confidence == pytest.approx(0.5)
    assert practice.score_confidence(q, True, 1.5).confidence == pytest.approx(1.0)


def test_confidence_report_returns_stats():
    q = bank.BinaryQuestion("q", answer=True)
    results = [practice.score_confidence(q, True, 0.8) for _ in range(5)]
    stats = practice.confidence_report(results)
    assert stats.n == 5
    assert 0 <= stats.brier <= 1
