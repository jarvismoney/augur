"""ASCII visualisations: reliability curve, calibration table, sparkline.

All charts are plain strings so they compose with the rest of the CLI output
and stay testable. Colour is applied through :mod:`augur.terminal` and degrades
to plain text when colour is disabled.
"""

from __future__ import annotations

from typing import Sequence

from . import terminal as t
from .scoring import Bin
from .util import format_probability

_MARK = "●"
_IDEAL = "·"
_SPARK = "▁▂▃▄▅▆▇█"


def reliability_curve(bins: Sequence[Bin], height: int = 11) -> str:
    """Render a 2-D calibration curve: forecast probability (x) vs observed
    frequency (y), with the ideal y=x diagonal drawn for reference.

    A perfectly calibrated forecaster's points sit on the diagonal. Points
    below it mean the event happened *less* often than you predicted
    (overconfident on the high end); points above mean it happened *more*
    often than you predicted.
    """
    n_bins = len(bins)
    if n_bins == 0:
        return "(no data)"

    grid = [[" "] * n_bins for _ in range(height)]

    def row_of(value: float) -> int:
        r = round((1 - value) * (height - 1))
        return max(0, min(height - 1, r))

    # Ideal diagonal first, so real points draw on top of it.
    for c, b in enumerate(bins):
        grid[row_of(b.midpoint)][c] = t.gray(_IDEAL)

    for c, b in enumerate(bins):
        if b.count == 0:
            continue
        marker = t.style(_MARK, _deviation_color(b))
        grid[row_of(b.observed)][c] = marker

    # Assemble with a y-axis on the left and an x-axis beneath.
    lines: list[str] = []
    cell = "  "  # each column is rendered 2 chars wide for readability
    for r in range(height):
        y = 1 - r / (height - 1)
        label = f"{int(round(y * 100)):>3d}% " if r % 2 == 0 else "     "
        lines.append(t.dim(label) + "│" + "".join(cell[0] + c for c in grid[r]))

    axis = "     └" + "─" * (n_bins * 2)
    ticks = "      " + "".join(
        f"{int(b.low * 100):<2d}"[:2] if i % 2 == 0 else "  "
        for i, b in enumerate(bins)
    )
    lines.append(axis)
    lines.append(ticks.rstrip())
    lines.append(t.dim("       forecast probability →  (● you, · ideal)"))
    return "\n".join(lines)


def _deviation_color(b: Bin) -> str:
    dev = abs(b.observed - b.mean_pred)
    if dev <= 0.05:
        return "green"
    if dev <= 0.15:
        return "yellow"
    return "red"


def calibration_table(bins: Sequence[Bin]) -> str:
    """A numeric companion to the curve: per-bin counts, forecast and outcome."""
    rows = [
        t.dim("  bucket      n   you say   happened   bar"),
    ]
    max_count = max((b.count for b in bins), default=0)
    for b in bins:
        if b.count == 0:
            continue
        label = f"{int(b.low * 100):>3d}-{int(b.high * 100):>3d}%"
        bar = _mini_bar(b.observed, b.mean_pred)
        count_bar = _count_bar(b.count, max_count)
        line = (
            f"  {label}  {b.count:>3d}   "
            f"{format_probability(b.mean_pred):>6}   "
            f"{format_probability(b.observed):>7}   {bar} {count_bar}"
        )
        rows.append(line)
    if len(rows) == 1:
        return "  (no scored forecasts yet)"
    return "\n".join(rows)


def _mini_bar(observed: float, predicted: float, width: int = 20) -> str:
    """A 0..100% track with the observed frequency filled and the forecast
    marked with a caret, so miscalibration is visible at a glance."""
    filled = int(round(observed * width))
    mark = min(width - 1, int(round(predicted * width)))
    cells = []
    for i in range(width):
        if i == mark:
            cells.append(t.bold("┃"))
        elif i < filled:
            cells.append(t.style("█", _bar_color(observed, predicted)))
        else:
            cells.append(t.gray("─"))
    return "".join(cells)


def _bar_color(observed: float, predicted: float) -> str:
    dev = abs(observed - predicted)
    if dev <= 0.05:
        return "green"
    if dev <= 0.15:
        return "yellow"
    return "red"


def _count_bar(count: int, max_count: int, width: int = 8) -> str:
    if max_count <= 0:
        return ""
    filled = max(1, int(round(count / max_count * width)))
    return t.dim("▪" * filled)


def sparkline(values: Sequence[float]) -> str:
    """Render a sequence of numbers as a compact unicode sparkline."""
    values = [v for v in values]
    if not values:
        return ""
    lo = min(values)
    hi = max(values)
    span = hi - lo
    out = []
    for v in values:
        if span == 0:
            idx = len(_SPARK) // 2
        else:
            idx = int((v - lo) / span * (len(_SPARK) - 1))
        out.append(_SPARK[idx])
    return "".join(out)


def hbar(fraction: float, width: int = 24, *, color: str | None = None) -> str:
    """A simple horizontal bar for a value in [0, 1]."""
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    bar = "█" * filled + t.gray("░" * (width - filled))
    return t.style(bar, color) if color else bar
