# Changelog

All notable changes to augur are documented here. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
semantic versioning.

## [0.2.0]

Focus: make the calibration report *understandable*, not just accurate.

### Added
- **Plain-English verdict.** `augur score` now leads with a one-line read of
  your calibration plus one or two specific, actionable takeaways (e.g. "You
  lean overconfident — your 70–80% forecasts came true 30% of the time"),
  before the detailed metrics. The verdict is also included in `score --json`.
- **Statistically honest call-outs.** Region and topic call-outs only fire when
  the deviation is significant (Wilson score intervals), so the tool never
  scolds you over a handful of lucky or unlucky guesses.
- **Weakest-topic hint.** When you have several well-populated tags and one is
  clearly worse than your average, the report names it — otherwise it stays
  quiet.
- **Practice progress nudge.** After a practice drill, a single line compares
  today's result to your history ("across 40 earlier answers your 90% ranges
  held 55%; today 80%"), using data augur already stored. No new command.
- **Help examples.** `augur --help` now ends with a short example workflow.

### Fixed
- **Calibration binning.** Exact-decile forecasts (e.g. `0.7`) were placed one
  bucket too low because `int(0.7 / 0.1)` truncates `6.999…`. This corrupted
  both the reliability diagram and the Murphy decomposition. Now bins with a
  rounding-safe index.
- **`import`** no longer crashes on a JSON array containing non-object elements;
  malformed entries are skipped with a warning.
- **`score` / `trend`** now reject `--bins <= 0` with a friendly message and
  exit code 2 instead of a traceback.
- **`reliability_curve`** no longer divides by zero when asked for a height of 1.

## [0.1.0]

Initial release.

- Log probabilistic forecasts, resolve them (yes/no/void), and score yourself.
- Proper scoring rules: Brier score, log/ignorance score, Brier skill score.
- Calibration diagnostics: reliability diagram, calibration table, and the
  Murphy reliability/resolution/uncertainty decomposition.
- Two calibration practice drills (90% interval, true/false-with-confidence)
  over a bundled, independently fact-checked trivia bank.
- Commands: `add`, `list`/`ls`, `show`, `resolve`, `edit`, `rm`, `due`,
  `score`, `trend`, `practice`, `export`, `import`, `stats`.
- Zero third-party runtime dependencies; data stored in a single SQLite file.
