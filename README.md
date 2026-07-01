# augur

**Log your forecasts. Resolve them. Find out how good your probabilities actually are.**

`augur` is a small terminal tool for keeping a *calibrated forecasting journal*
and for *training* your calibration. You write down predictions with a
probability ("70% chance this ships by Friday"), resolve them when the outcome
is known, and `augur` scores you with the same proper scoring rules that
professional forecasters use — Brier score, log score, and a reliability
diagram that shows, of all the times you said "70%", how often it actually
happened.

Calibration is a trainable skill (Tetlock's *Superforecasting*; Hubbard's *How
to Measure Anything*; the Good Judgment Project), and being well-calibrated
makes you measurably better at decisions. Most tools for this are web services.
`augur` is the opposite: **local, private, and dependency-free.**

- **Zero dependencies.** Pure Python standard library. Nothing to `pip install`
  but the tool itself. It runs anywhere Python 3.9+ runs.
- **Local & private.** Your journal is a single SQLite file that you own. No
  account, no network, no telemetry.
- **Two things in one.** A *journal* for real-life predictions, and a *practice
  range* with built-in drills so you can train calibration on demand.

```
$ augur score

Calibration report
  forecasts scored : 60
  brier score      : 0.156   (0 perfect · 0.25 = always 50%)
  brier skill      : +0.369   (vs. always guessing the base rate)
  log score        : 0.491 nats (0.708 bits)
  base rate        : 55% of statements came true
  reliability      : 0.0353  (calibration error, lower better)
  resolution       : 0.1243  (discrimination, higher better)
  confidence       : you felt 75.7% sure, were right 80.8% of the time — underconfident by 5.2%

100% │             ●
     │                 · ·
 80% │           ●   · ● ●
     │             ·
 60% │           ·
 40% │       · ●
     │   ●
 20% │   · ·
  0% │ ●   ●
     └────────────────────
      0   20  40  60  80
       forecast probability →  (● you, · ideal)
```

Points on the dotted diagonal mean you're perfectly calibrated. Points *below*
it mean the thing happened less often than you predicted (overconfident);
*above* means it happened more often (underconfident).

## Install

`augur` needs only Python 3.9+. Clone the repo and either run it in place or
install the `augur` command:

```bash
# run without installing
python -m augur --help

# or install the console script (still zero runtime dependencies)
pip install -e .
augur --help
```

## Quickstart

```bash
# record a forecast: probability can be 35, 35%, or 0.35
augur add "Bitcoin above \$150k by end of 2026" -p 35 --by 2026-12-31 --tags crypto macro

# see what's open
augur list

# something came true (or didn't)
augur resolve 1 no

# what needs resolving now?
augur due

# how am I doing?
augur score
augur score --tag crypto      # per-topic
augur trend                   # calibration over time

# warm up / train calibration any time
augur practice                    # 90% confidence-interval drill
augur practice --mode confidence  # true/false-with-confidence drill
```

Running `augur` with no arguments shows a small dashboard (counts, what's due,
your current Brier score).

## The two practice drills

Real forecasts take weeks or months to resolve, so `augur` ships with a
fact-checked trivia bank you can drill against immediately:

- **Interval drill** (`augur practice`) — for each question you give a range
  you're **90% sure** contains the answer. A well-calibrated person's 90%
  ranges contain the truth about 90% of the time. Almost everyone starts out
  far too narrow (overconfident); `augur` tells you your true hit rate.

- **Confidence drill** (`augur practice --mode confidence`) — for each
  statement you say true/false and how sure you are (50–100%). You get a full
  Brier score and calibration table for the session.

## What the numbers mean

| Metric | Meaning | Good value |
| --- | --- | --- |
| **Brier score** | Mean squared error of your probabilities | Low. `0` is perfect; `0.25` is what "always 50%" gets you |
| **Log score** | Surprise of the outcomes under your forecasts (nats/bits) | Low. Punishes confident mistakes harshly |
| **Brier skill** | Skill vs. always predicting the base rate | `> 0` means real skill; `1.0` is perfect |
| **Reliability** | Calibration error — do your 70%s happen 70% of the time? | Low |
| **Resolution** | Discrimination — do you push away from the base rate when you should? | High |
| **Overconfidence** | Mean confidence minus actual accuracy | Near `0` |

The Brier score decomposes exactly (Murphy 1973) into
`reliability − resolution + uncertainty`, so `augur` can tell you *why* your
score is what it is: bad calibration, or simply not discriminating between
likely and unlikely events.

## Commands

| Command | Does |
| --- | --- |
| `add "<statement>" -p <prob> [--by DATE] [--tags ...] [--note ...]` | Record a forecast |
| `list [--status ...] [--tag T] [--since DATE] [--due] [--json]` | List forecasts |
| `show <id> [--json]` | Show one forecast in detail |
| `resolve <id> yes\|no\|void [--at DATE] [--note ...]` | Resolve a forecast |
| `edit <id> [--prob ...] [--by ...] [--tags ...] [--note ...] [--statement ...]` | Edit a forecast (`--by ""` clears the deadline) |
| `rm <id> [-y]` | Delete a forecast |
| `due` | Open forecasts past their resolve-by date |
| `score [--tag T] [--since DATE] [--bins N] [--json]` | Calibration report + reliability diagram |
| `trend [--buckets N]` | Brier score over time |
| `practice [--mode interval\|confidence] [-n N] [--seed S]` | Calibration drills |
| `export [--format json\|csv] [-o FILE]` | Export your journal |
| `import <file.json>` | Import forecasts |
| `stats` | One-line summary |

Dates accept ISO (`2026-12-31`), keywords (`today`, `tomorrow`), and relative
offsets (`+7d`, `+2w`, `+3m`, `+1y`).

## Data & privacy

Your journal lives in a single SQLite file. By default that's
`$XDG_DATA_HOME/augur/augur.db` (usually `~/.local/share/augur/augur.db`).
Override it per-command with `--db /path/to.db` or globally with the `AUGUR_DB`
environment variable. Back it up, sync it, or `augur export` it — it's yours.

Colour output auto-detects a terminal and honours `NO_COLOR`; force it with
`--color` / `--no-color`.

## Development

```bash
python -m pytest        # 67 tests, no third-party deps required to run the tool
```

The scoring math is covered by tests that pin the Brier/log values and check
the Murphy decomposition identity exactly. The bundled trivia bank was
independently verified by a fan-out of web-searching fact-check agents before
shipping.

## License

MIT — see [LICENSE](LICENSE).
