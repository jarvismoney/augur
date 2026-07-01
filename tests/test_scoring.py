"""Rigorous tests for the scoring and calibration math.

These pin down the numbers a user's calibration report depends on, including
the Murphy decomposition identity (Brier = reliability - resolution +
uncertainty), which must hold exactly when each bin holds a single forecast
value.
"""

import math

import pytest

from augur.scoring import (
    base_rate,
    brier_score,
    brier_skill_score,
    calibration_bins,
    compute_stats,
    confidence_accuracy,
    interval_coverage,
    interpret_coverage,
    log_score,
    murphy_decomposition,
    uncertainty,
)


def test_brier_known_values():
    assert brier_score([(1.0, 1), (0.0, 0)]) == pytest.approx(0.0)
    assert brier_score([(0.0, 1), (1.0, 0)]) == pytest.approx(1.0)
    assert brier_score([(0.5, 1), (0.5, 0)]) == pytest.approx(0.25)
    assert brier_score([(0.7, 1)]) == pytest.approx(0.09)


def test_brier_empty_raises():
    with pytest.raises(ValueError):
        brier_score([])


def test_log_score_half_is_ln2():
    assert log_score([(0.5, 1)]) == pytest.approx(math.log(2))
    assert log_score([(0.5, 1)], bits=True) == pytest.approx(1.0)


def test_log_score_clamps_certain_and_wrong():
    # 100% and wrong would be infinite surprise; clamping keeps it large-but-finite.
    value = log_score([(1.0, 0)])
    assert math.isfinite(value)
    assert value > 10


def test_base_rate_and_uncertainty():
    pairs = [(0.5, 1), (0.5, 1), (0.5, 0), (0.5, 0)]
    assert base_rate(pairs) == pytest.approx(0.5)
    assert uncertainty(pairs) == pytest.approx(0.25)


def test_brier_skill_perfect_and_degenerate():
    assert brier_skill_score([(1.0, 1), (0.0, 0)]) == pytest.approx(1.0)
    # All same outcome => uncertainty 0 => skill undefined (NaN).
    assert math.isnan(brier_skill_score([(0.9, 1), (0.8, 1)]))


def test_calibration_bins_counts_and_top_edge():
    pairs = [(0.05, 0), (0.15, 1), (1.0, 1)]
    bins = calibration_bins(pairs, n_bins=10)
    assert bins[0].count == 1
    assert bins[1].count == 1
    # A forecast of exactly 1.0 lands in the last bin, not out of range.
    assert bins[9].count == 1
    assert sum(b.count for b in bins) == 3


def test_calibration_bin_observed_and_mean():
    pairs = [(0.72, 1), (0.78, 0)]  # both in the 70-80% bin
    bins = calibration_bins(pairs, n_bins=10)
    b = bins[7]
    assert b.count == 2
    assert b.mean_pred == pytest.approx(0.75)
    assert b.observed == pytest.approx(0.5)


def _single_valued_dataset():
    """Forecasts take only values 0.1/0.3/0.7/0.9 -> one per decile bin, so the
    Murphy decomposition identity holds exactly."""
    pairs = []
    for prob, n, yes in [(0.1, 10, 2), (0.3, 10, 4), (0.7, 10, 8), (0.9, 10, 8)]:
        pairs += [(prob, 1)] * yes + [(prob, 0)] * (n - yes)
    return pairs


def test_murphy_decomposition_identity_exact():
    pairs = _single_valued_dataset()
    decomp = murphy_decomposition(pairs, n_bins=10)
    assert decomp.reconstructed_brier == pytest.approx(brier_score(pairs), abs=1e-9)


def test_murphy_parts_nonnegative():
    pairs = _single_valued_dataset()
    d = murphy_decomposition(pairs, n_bins=10)
    assert d.reliability >= 0
    assert d.resolution >= 0
    assert 0 <= d.uncertainty <= 0.25


def test_confidence_accuracy():
    # Said 80% (leaned yes) and it happened; said 90% (leaned no) and it didn't.
    conf, acc = confidence_accuracy([(0.8, 1), (0.1, 0)])
    assert conf == pytest.approx(0.85)
    assert acc == pytest.approx(1.0)
    # A 50% forecast counts as half a hit and 0.5 confidence.
    conf2, acc2 = confidence_accuracy([(0.5, 1)])
    assert conf2 == pytest.approx(0.5)
    assert acc2 == pytest.approx(0.5)


def test_compute_stats_bundle():
    pairs = _single_valued_dataset()
    stats = compute_stats(pairs, n_bins=10)
    assert stats.n == 40
    assert stats.brier == pytest.approx(brier_score(pairs))
    assert stats.base_rate == pytest.approx(base_rate(pairs))
    assert len(stats.bins) == 10
    # overconfidence is confidence minus accuracy
    assert stats.overconfidence == pytest.approx(stats.mean_confidence - stats.accuracy)


def test_interval_coverage_and_interpretation():
    hits = [True] * 9 + [False]
    assert interval_coverage(hits) == pytest.approx(0.9)
    assert "well calibrated" in interpret_coverage(0.9, 0.9, 20)
    assert "narrow" in interpret_coverage(0.4, 0.9, 20)
    # A tighter sample (larger n) makes a 10-point over-coverage significant.
    assert "wide" in interpret_coverage(1.0, 0.9, 100)
    assert "few" in interpret_coverage(0.0, 0.9, 2)
