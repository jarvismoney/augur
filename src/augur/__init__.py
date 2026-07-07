"""augur — a terminal calibration trainer and forecasting journal.

Log predictions with a probability, resolve them when the outcome is known,
and get honest feedback on how well-calibrated your beliefs actually are.

Everything runs locally with zero third-party dependencies: the whole tool is
built on the Python standard library, and your data lives in a single SQLite
file that you own.
"""

__version__ = "0.3.0"
__all__ = ["__version__"]
