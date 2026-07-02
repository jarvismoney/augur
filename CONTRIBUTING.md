# Contributing

Thanks for your interest! `augur` is a small, focused tool; contributions are
welcome within its philosophy:

- **Zero runtime dependencies.** Standard library only — PRs adding runtime
  deps will be declined, however good the library.
- **Local & private.** No network calls, no telemetry, ever.
- **Plain English first.** Anything user-facing leads with the takeaway, not
  the statistics; call-outs must be gated on statistical significance.

## Dev setup

```bash
pip install -e ".[dev]"
python -m pytest
```

Tests are required for behavior changes. The suite is fast; run it before
pushing. CI covers Python 3.9–3.13 on Linux, macOS and Windows.

## Question bank contributions

New calibration questions are welcome and easy to add
(`src/augur/calibration_bank.py`). Every fact must be stable (or pinned to a
year in the prompt), unambiguous, and verifiable — include a terse `source`
note. Numeric answers should be exact or explicitly rounded in the prompt.

## Contact

Open an [issue](https://github.com/jarvismoney/augur/issues) for bugs,
questions, or ideas.
