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
    summarize,
    uncertainty,
    wilson_interval,
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


def test_calibration_bins_exact_deciles_place_correctly():
    # Regression: 0.7/0.1 == 6.999... so a naive int() truncation put exact
    # decile forecasts one bin too low. Each p = i/10 must land in bin i.
    for i in range(1, 10):
        p = i / 10
        bins = calibration_bins([(p, 1)], n_bins=10)
        placed = [k for k, b in enumerate(bins) if b.count]
        assert placed == [i], f"p={p} placed in {placed}, expected [{i}]"
    # And with 5 bins, 0.6 belongs in bin 3 = [0.6, 0.8), not [0.4, 0.6).
    bins5 = calibration_bins([(0.6, 1)], n_bins=5)
    assert [k for k, b in enumerate(bins5) if b.count] == [3]


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


def test_wilson_interval_bounds_and_width():
    lo, hi = wilson_interval(5, 10)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    # Empty -> maximal ignorance.
    assert wilson_interval(0, 0) == (0.0, 1.0)
    # All successes: high pinned near 1, low well below 1.
    lo2, hi2 = wilson_interval(10, 10)
    assert hi2 == pytest.approx(1.0, abs=1e-3)
    assert lo2 < 1.0
    # Less data => wider interval.
    small = wilson_interval(1, 2)
    big = wilson_interval(50, 100)
    assert (small[1] - small[0]) > (big[1] - big[0])


def test_bin_significance_requires_enough_data():
    # 1/2 observed with a 0.9 forecast: suggestive but too little data.
    bins = calibration_bins([(0.9, 1), (0.9, 0)], n_bins=10)
    assert bins[9].is_significant() is False
    # 0/10 observed against a 0.9 forecast: clearly, significantly miscalibrated.
    bins2 = calibration_bins([(0.9, 0)] * 10, n_bins=10)
    assert bins2[9].is_significant() is True


def test_summarize_small_sample():
    stats = compute_stats([(0.7, 1), (0.3, 0)], n_bins=10)
    insight = summarize(stats, min_n=10)
    assert insight.tone == "info"
    assert "warming up" in insight.headline.lower()


def test_summarize_overconfident():
    pairs = [(0.9, 1)] * 10 + [(0.9, 0)] * 10  # felt 90%, right 50%
    insight = summarize(compute_stats(pairs, n_bins=10))
    assert insight.tone == "warn"
    assert "overconfident" in insight.headline.lower()
    assert insight.takeaways  # has at least one concrete takeaway


def test_summarize_underconfident():
    pairs = [(0.6, 1)] * 20  # hedged at 60% but always right
    insight = summarize(compute_stats(pairs, n_bins=10))
    assert insight.tone == "warn"
    assert "underconfident" in insight.headline.lower()


def test_summarize_well_calibrated():
    pairs = [(0.7, 1)] * 7 + [(0.7, 0)] * 3  # 70% forecasts happen 70%
    insight = summarize(compute_stats(pairs, n_bins=10))
    assert insight.tone == "good"
    assert "calibrated" in insight.headline.lower()
    assert len(insight.takeaways) <= 2


def test_summarize_mixed_direction_is_not_contradictory():
    # Underconfident on average, but a significant *over*confident high-prob bin.
    # The verdict must not simply say "be bolder" while flagging overconfidence.
    pairs = [(0.55, 1)] * 20 + [(0.90, 0)] * 8
    insight = summarize(compute_stats(pairs, n_bins=10))
    h = insight.headline.lower()
    assert "in places" in h and "overconfident" in h
    assert insight.headline != "You lean underconfident — you know more than you let on."


def test_summarize_weak_area_phrasing_unambiguous_for_low_bins():
    # Events in a 0-10% bin all happened: must read as "happened", not
    # "came true" (which would sound like vindication).
    pairs = [(0.05, 1)] * 12 + [(0.5, 1), (0.5, 0)] * 4
    insight = summarize(compute_stats(pairs, n_bins=10))
    joined = " ".join(insight.takeaways).lower()
    assert "came true" not in joined
    assert "happened" in joined


def test_interval_coverage_and_interpretation():
    hits = [True] * 9 + [False]
    assert interval_coverage(hits) == pytest.approx(0.9)
    assert "well calibrated" in interpret_coverage(0.9, 0.9, 20)
    assert "narrow" in interpret_coverage(0.4, 0.9, 20)
    # A tighter sample (larger n) makes a 10-point over-coverage significant.
    assert "wide" in interpret_coverage(1.0, 0.9, 100)
    assert "few" in interpret_coverage(0.0, 0.9, 2)
