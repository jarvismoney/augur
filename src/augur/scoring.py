"""Proper scoring rules and calibration diagnostics.

This is the analytical heart of augur. Given a set of (forecast, outcome)
pairs -- where ``forecast`` is the probability you assigned to an event and
``outcome`` is 1 if it happened and 0 if it did not -- these functions tell you
how good your probabilities actually were.

Key ideas:

* **Brier score** -- mean squared error of your probabilities. Lower is
  better; 0 is perfect, 0.25 is what you get by always saying 50%.
* **Log score** -- the "surprise" (in nats or bits) of the outcomes under your
  forecasts. Punishes confident mistakes harshly.
* **Calibration** -- of all the times you said "70%", did it happen ~70% of the
  time? Shown as a reliability table / diagram.
* **Murphy decomposition** -- splits the Brier score into
  ``reliability - resolution + uncertainty`` so you can see whether your error
  comes from being mis-calibrated (reliability) or from not discriminating
  between likely and unlikely events (resolution).

References: Brier (1950); Murphy (1973), "A New Vector Partition of the
Probability Score"; Tetlock & Gardner, *Superforecasting* (2015).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .models import Outcome, Prediction

# Clamp probabilities away from 0 and 1 so the log score stays finite. A
# forecaster who says "100%" and is wrong has, in principle, taken infinite
# surprise; we cap it rather than blow up.
_EPS = 1e-9

Pair = tuple[float, int]


def pairs_from_predictions(predictions: Iterable[Prediction]) -> list[Pair]:
    """Extract (probability, binary-outcome) pairs from scorable predictions."""
    pairs: list[Pair] = []
    for p in predictions:
        if p.outcome.is_scorable:
            pairs.append((p.probability, p.outcome.as_binary()))
    return pairs


# ---------------------------------------------------------------------------
# Scalar scores
# ---------------------------------------------------------------------------


def brier_score(pairs: Sequence[Pair]) -> float:
    """Mean squared error of the forecasts. Range [0, 1]; lower is better."""
    if not pairs:
        raise ValueError("cannot score an empty set of predictions")
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def log_score(pairs: Sequence[Pair], *, bits: bool = False) -> float:
    """Mean logarithmic (ignorance) score. Lower is better.

    Returned in nats by default, or in bits when ``bits=True``. A perfect,
    perfectly-confident forecaster scores 0; always saying 50% scores ln 2
    (1 bit).
    """
    if not pairs:
        raise ValueError("cannot score an empty set of predictions")
    total = 0.0
    for p, o in pairs:
        p = min(max(p, _EPS), 1 - _EPS)
        total += -math.log(p if o == 1 else 1 - p)
    mean = total / len(pairs)
    return mean / math.log(2) if bits else mean


def base_rate(pairs: Sequence[Pair]) -> float:
    """The observed frequency of YES outcomes (the 'climatology')."""
    if not pairs:
        raise ValueError("empty")
    return sum(o for _, o in pairs) / len(pairs)


def brier_skill_score(pairs: Sequence[Pair]) -> float:
    """Skill relative to always forecasting the base rate.

    1.0 is perfect, 0.0 means "no better than always predicting the base rate",
    negative means "worse than that". Undefined (NaN) when every outcome is the
    same, since the base-rate reference is then already perfect.
    """
    unc = uncertainty(pairs)
    if unc == 0:
        return float("nan")
    return 1 - brier_score(pairs) / unc


def uncertainty(pairs: Sequence[Pair]) -> float:
    """Irreducible difficulty of the questions: base_rate * (1 - base_rate)."""
    br = base_rate(pairs)
    return br * (1 - br)


# ---------------------------------------------------------------------------
# Two-alternative confidence vs. accuracy
# ---------------------------------------------------------------------------


def confidence_accuracy(pairs: Sequence[Pair]) -> tuple[float, float]:
    """Mean confidence and mean accuracy in the two-alternative sense.

    Confidence is ``max(p, 1 - p)`` (how sure you were of the side you leaned
    toward). A forecast counts as accurate if you leaned toward the side that
    happened; a 50% forecast counts as half a hit. The gap between mean
    confidence and mean accuracy is the classic over/under-confidence measure:
    "you said 80% but were right 65% of the time".
    """
    if not pairs:
        raise ValueError("empty")
    conf_total = 0.0
    hit_total = 0.0
    for p, o in pairs:
        conf_total += max(p, 1 - p)
        if p == 0.5:
            hit_total += 0.5
        elif (p > 0.5 and o == 1) or (p < 0.5 and o == 0):
            hit_total += 1.0
    n = len(pairs)
    return conf_total / n, hit_total / n


# ---------------------------------------------------------------------------
# Calibration binning + reliability diagram data
# ---------------------------------------------------------------------------


@dataclass
class Bin:
    """One bucket of a reliability diagram."""

    low: float
    high: float
    count: int
    sum_pred: float
    sum_outcome: float

    @property
    def mean_pred(self) -> float:
        """Average forecast in this bin (falls back to the bin midpoint)."""
        if self.count == 0:
            return (self.low + self.high) / 2
        return self.sum_pred / self.count

    @property
    def observed(self) -> float:
        """Observed YES frequency in this bin (0 if empty)."""
        if self.count == 0:
            return 0.0
        return self.sum_outcome / self.count

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2


def calibration_bins(pairs: Sequence[Pair], n_bins: int = 10) -> list[Bin]:
    """Partition forecasts into ``n_bins`` equal-width probability buckets.

    A forecast of exactly 1.0 lands in the top bin. Empty bins are retained so
    the diagram keeps a consistent x-axis.
    """
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    width = 1.0 / n_bins
    bins = [
        Bin(low=i * width, high=(i + 1) * width, count=0, sum_pred=0.0,
            sum_outcome=0.0)
        for i in range(n_bins)
    ]
    for p, o in pairs:
        idx = min(int(p / width), n_bins - 1)
        b = bins[idx]
        b.count += 1
        b.sum_pred += p
        b.sum_outcome += o
    return bins


# ---------------------------------------------------------------------------
# Murphy decomposition
# ---------------------------------------------------------------------------


@dataclass
class Decomposition:
    reliability: float
    resolution: float
    uncertainty: float

    @property
    def reconstructed_brier(self) -> float:
        """Brier as rebuilt from the parts: REL - RES + UNC."""
        return self.reliability - self.resolution + self.uncertainty


def murphy_decomposition(pairs: Sequence[Pair], n_bins: int = 10) -> Decomposition:
    """Decompose the Brier score into reliability, resolution and uncertainty.

    Uses the calibration-refinement partition with each bin represented by its
    *mean forecast*. The identity ``Brier = reliability - resolution +
    uncertainty`` holds exactly when every forecast within a bin is identical
    (as in the test suite) and is a close approximation otherwise.

    * reliability (lower is better): mean squared gap between your forecasts and
      the outcomes that actually followed them -- pure miscalibration.
    * resolution (higher is better): how far your bins' outcome rates spread
      away from the base rate -- your ability to tell likely from unlikely.
    * uncertainty: base_rate * (1 - base_rate), fixed by the questions.
    """
    if not pairs:
        raise ValueError("empty")
    n = len(pairs)
    o_bar = base_rate(pairs)
    bins = calibration_bins(pairs, n_bins)

    reliability = 0.0
    resolution = 0.0
    for b in bins:
        if b.count == 0:
            continue
        reliability += b.count * (b.mean_pred - b.observed) ** 2
        resolution += b.count * (b.observed - o_bar) ** 2
    reliability /= n
    resolution /= n
    return Decomposition(
        reliability=reliability,
        resolution=resolution,
        uncertainty=o_bar * (1 - o_bar),
    )


# ---------------------------------------------------------------------------
# Bundled statistics
# ---------------------------------------------------------------------------


@dataclass
class Stats:
    """Everything the ``score`` command needs, computed in one pass."""

    n: int
    base_rate: float
    brier: float
    brier_skill: float
    log_score: float
    log_score_bits: float
    reliability: float
    resolution: float
    uncertainty: float
    mean_confidence: float
    accuracy: float
    bins: list[Bin]

    @property
    def overconfidence(self) -> float:
        """Positive => overconfident, negative => underconfident."""
        return self.mean_confidence - self.accuracy


def compute_stats(pairs: Sequence[Pair], n_bins: int = 10) -> Stats:
    """Compute the full statistics bundle for a set of forecasts."""
    if not pairs:
        raise ValueError("cannot compute stats on an empty set of predictions")
    decomp = murphy_decomposition(pairs, n_bins)
    conf, acc = confidence_accuracy(pairs)
    return Stats(
        n=len(pairs),
        base_rate=base_rate(pairs),
        brier=brier_score(pairs),
        brier_skill=brier_skill_score(pairs),
        log_score=log_score(pairs),
        log_score_bits=log_score(pairs, bits=True),
        reliability=decomp.reliability,
        resolution=decomp.resolution,
        uncertainty=decomp.uncertainty,
        mean_confidence=conf,
        accuracy=acc,
        bins=calibration_bins(pairs, n_bins),
    )


# ---------------------------------------------------------------------------
# Interval calibration (for the numeric practice drill)
# ---------------------------------------------------------------------------


def interval_coverage(hits: Sequence[bool]) -> float:
    """Fraction of confidence intervals that actually contained the truth."""
    if not hits:
        raise ValueError("empty")
    return sum(1 for h in hits if h) / len(hits)


def interpret_coverage(observed: float, target: float, n: int) -> str:
    """Human-readable verdict on interval calibration.

    A well-calibrated forecaster's X% intervals contain the truth about X% of
    the time. Consistently containing it *less* often means the intervals are
    too narrow (overconfident) -- the usual human failing.
    """
    gap = observed - target
    if n < 5:
        return "too few answers to judge calibration yet"
    if abs(gap) <= 0.5 / math.sqrt(n) + 0.03:
        return "well calibrated — nicely done"
    if gap < 0:
        return "intervals too narrow (overconfident) — widen your ranges"
    return "intervals too wide (underconfident) — you can be bolder"
