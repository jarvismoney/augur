"""Calibration practice drills.

Two drills, both classics of the calibration-training literature:

* **Interval drill** (numeric): for each question you give a 90% confidence
  interval -- a low/high range you're 90% sure contains the true answer. A
  well-calibrated person's 90% intervals contain the truth ~90% of the time.
  Most people's contain it far less: the intervals are too narrow. (Hubbard,
  *How to Measure Anything*.)

* **Confidence drill** (binary): for each statement you say true/false and how
  sure you are (50-100%). This is scored with the Brier score and the usual
  calibration diagnostics.

The scoring here is deliberately pure (no I/O), so the CLI owns all prompting
and printing and these functions stay unit-testable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Sequence

from . import calibration_bank as bank
from .scoring import Pair, compute_stats, interpret_coverage

INTERVAL = "interval"
CONFIDENCE = "confidence"
DEFAULT_TARGET = 0.9


# ---------------------------------------------------------------------------
# Question selection
# ---------------------------------------------------------------------------


def sample_numeric(n: int, *, rng: Optional[random.Random] = None):
    rng = rng or random.Random()
    n = min(n, len(bank.NUMERIC))
    return rng.sample(bank.NUMERIC, n)


def sample_binary(n: int, *, rng: Optional[random.Random] = None):
    rng = rng or random.Random()
    n = min(n, len(bank.BINARY))
    return rng.sample(bank.BINARY, n)


# ---------------------------------------------------------------------------
# Interval drill
# ---------------------------------------------------------------------------


@dataclass
class IntervalResult:
    question: bank.NumericQuestion
    low: float
    high: float
    hit: bool

    @property
    def width(self) -> float:
        return self.high - self.low


def score_interval(question: bank.NumericQuestion, low: float, high: float) -> IntervalResult:
    """Judge one interval answer. Order of low/high is normalised for the user."""
    if low > high:
        low, high = high, low
    hit = low <= question.answer <= high
    return IntervalResult(question=question, low=low, high=high, hit=hit)


@dataclass
class IntervalReport:
    n: int
    hits: int
    coverage: float
    target: float
    verdict: str


def interval_report(results: Sequence[IntervalResult], target: float = DEFAULT_TARGET) -> IntervalReport:
    n = len(results)
    hits = sum(1 for r in results if r.hit)
    coverage = hits / n if n else 0.0
    verdict = interpret_coverage(coverage, target, n)
    return IntervalReport(n=n, hits=hits, coverage=coverage, target=target, verdict=verdict)


# ---------------------------------------------------------------------------
# Confidence drill
# ---------------------------------------------------------------------------


@dataclass
class ConfidenceResult:
    question: bank.BinaryQuestion
    said_true: bool
    confidence: float  # in [0.5, 1.0]
    prob_true: float   # probability assigned to the statement being TRUE, [0,1]
    correct: bool

    @property
    def pair(self) -> Pair:
        """(forecast, outcome) for scoring: P(true) vs actual truth."""
        return (self.prob_true, 1 if self.question.answer else 0)


def score_confidence(question: bank.BinaryQuestion, said_true: bool, confidence: float) -> ConfidenceResult:
    """Judge one true/false-with-confidence answer.

    ``confidence`` is how sure the user is of their *chosen* side, in [0.5, 1].
    It is converted to a probability that the *statement* is true.
    """
    confidence = min(max(confidence, 0.5), 1.0)
    prob_true = confidence if said_true else 1 - confidence
    correct = said_true == question.answer
    return ConfidenceResult(
        question=question,
        said_true=said_true,
        confidence=confidence,
        prob_true=prob_true,
        correct=correct,
    )


def confidence_report(results: Sequence[ConfidenceResult], n_bins: int = 5):
    """Full calibration stats for a confidence drill (reuses core scoring)."""
    pairs = [r.pair for r in results]
    return compute_stats(pairs, n_bins=n_bins)
