"""Command-line interface for augur.

Sub-commands:
    add        record a new forecast
    list/ls    show forecasts (open, resolved, filtered)
    show       show one forecast in detail
    resolve    mark a forecast yes / no / void
    edit       change a forecast's fields
    rm         delete a forecast
    due        forecasts past their resolve-by date and still open
    score      Brier score, calibration curve and diagnostics
    trend      how your Brier score has moved over time
    practice   calibration drills against a bundled trivia bank
    export     dump forecasts to JSON or CSV
    import     load forecasts from JSON
    stats      one-line summary of the journal
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import random
import sys
from datetime import datetime
from typing import Optional

from . import __version__
from . import calibration_bank as bank
from . import charts
from . import practice as practice_mod
from . import terminal as t
from .db import Database
from .models import Outcome, Prediction, normalize_tags
from .scoring import compute_stats, pairs_from_predictions
from .util import (
    DateParseError,
    ProbabilityError,
    format_probability,
    from_iso,
    humanize_delta,
    now_utc,
    parse_date,
    parse_probability,
    to_iso,
    default_db_path,
)


# ---------------------------------------------------------------------------
# small output helpers
# ---------------------------------------------------------------------------


def _eprint(*args) -> None:
    print(*args, file=sys.stderr)


def _brier_color(value: float) -> str:
    if value <= 0.10:
        return "green"
    if value <= 0.25:
        return "yellow"
    return "red"


def _outcome_badge(p: Prediction) -> str:
    if p.outcome is Outcome.YES:
        return t.green("YES")
    if p.outcome is Outcome.NO:
        return t.red("NO")
    if p.outcome is Outcome.VOID:
        return t.gray("void")
    if p.is_due():
        return t.red("due")
    return t.yellow("open")


def _fmt_prediction_line(p: Prediction) -> str:
    pid = t.bold(f"#{p.id}")
    prob = t.cyan(f"[{format_probability(p.probability)}]")
    badge = _outcome_badge(p)
    tags = t.dim("  " + " ".join(f"#{tag}" for tag in p.tags)) if p.tags else ""
    when = ""
    if p.outcome is Outcome.OPEN and p.resolve_by is not None:
        when = t.dim(f"  · {humanize_delta(p.resolve_by)}")
    elif p.outcome.is_scorable:
        b = p.brier()
        when = "  · " + t.style(f"brier {b:.2f}", _brier_color(b))
    statement = p.statement
    return f"{pid} {prob} {badge}  {statement}{tags}{when}"


def _prediction_to_dict(p: Prediction) -> dict:
    return {
        "id": p.id,
        "statement": p.statement,
        "probability": p.probability,
        "created_at": to_iso(p.created_at),
        "resolve_by": to_iso(p.resolve_by) if p.resolve_by else None,
        "resolved_at": to_iso(p.resolved_at) if p.resolved_at else None,
        "outcome": p.outcome.value,
        "tags": p.tags,
        "note": p.note,
    }


def _prediction_from_dict(d: dict) -> Prediction:
    return Prediction(
        id=d.get("id"),
        statement=d["statement"],
        probability=float(d["probability"]),
        created_at=from_iso(d["created_at"]) if d.get("created_at") else now_utc(),
        resolve_by=from_iso(d["resolve_by"]) if d.get("resolve_by") else None,
        resolved_at=from_iso(d["resolved_at"]) if d.get("resolved_at") else None,
        outcome=Outcome(d.get("outcome", "open")),
        tags=normalize_tags(d.get("tags")),
        note=d.get("note", "") or "",
    )


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_add(args, db: Database) -> int:
    try:
        prob = parse_probability(args.prob)
    except ProbabilityError as exc:
        _eprint(t.red(f"error: {exc}"))
        return 2

    resolve_by = None
    if args.by:
        try:
            resolve_by = parse_date(args.by)
        except DateParseError as exc:
            _eprint(t.red(f"error: {exc}"))
            return 2

    statement = args.statement.strip()
    if not statement:
        _eprint(t.red("error: statement cannot be empty"))
        return 2

    pred = Prediction(
        statement=statement,
        probability=prob,
        created_at=now_utc(),
        resolve_by=resolve_by,
        tags=normalize_tags(args.tags),
        note=args.note or "",
    )
    db.add(pred)
    print(t.green(f"✓ recorded #{pred.id}") + f"  {_fmt_prediction_line(pred)}")
    if prob in (0.0, 1.0):
        _eprint(
            t.yellow(
                "note: 0% and 100% are absolute certainty — a single surprise "
                "makes your log score infinite. Consider 1%/99%."
            )
        )
    return 0


def cmd_list(args, db: Database) -> int:
    since = _parse_optional_date(args.since)
    if since is None and args.since:
        return 2
    preds = db.list(
        status=args.status,
        tag=args.tag,
        since=since,
        due_only=args.due,
        newest_first=not args.oldest,
    )
    if args.json:
        print(json.dumps([_prediction_to_dict(p) for p in preds], indent=2))
        return 0
    if not preds:
        print(t.dim("no forecasts match."))
        return 0
    for p in preds:
        print(_fmt_prediction_line(p))
    print(t.dim(f"\n{len(preds)} forecast(s)."))
    return 0


def cmd_show(args, db: Database) -> int:
    p = db.get(args.id)
    if p is None:
        _eprint(t.red(f"error: no forecast #{args.id}"))
        return 1
    if args.json:
        print(json.dumps(_prediction_to_dict(p), indent=2))
        return 0
    print(t.bold(f"#{p.id}") + f"  {p.statement}")
    print(f"  probability : {t.cyan(format_probability(p.probability))}  "
          f"(P this resolves YES)")
    print(f"  status      : {_outcome_badge(p)}")
    print(f"  created     : {_local(p.created_at)}  ({humanize_delta(p.created_at)})")
    if p.resolve_by:
        print(f"  resolve by  : {_local(p.resolve_by)}  ({humanize_delta(p.resolve_by)})")
    if p.resolved_at:
        print(f"  resolved    : {_local(p.resolved_at)}  ({humanize_delta(p.resolved_at)})")
    if p.outcome.is_scorable:
        b = p.brier()
        print(f"  brier       : {t.style(f'{b:.3f}', _brier_color(b))}")
    if p.tags:
        print(f"  tags        : {' '.join('#' + tag for tag in p.tags)}")
    if p.note:
        print(f"  note        : {p.note}")
    return 0


def cmd_resolve(args, db: Database) -> int:
    outcome = _parse_outcome(args.outcome)
    if outcome is None:
        _eprint(t.red(f"error: outcome must be yes/no/void, got {args.outcome!r}"))
        return 2
    resolved_at = None
    if args.at:
        try:
            resolved_at = parse_date(args.at)
        except DateParseError as exc:
            _eprint(t.red(f"error: {exc}"))
            return 2
    p = db.resolve(args.id, outcome, resolved_at=resolved_at, note=args.note)
    if p is None:
        _eprint(t.red(f"error: no forecast #{args.id}"))
        return 1
    print(t.green("✓ resolved") + f"  {_fmt_prediction_line(p)}")
    if p.outcome.is_scorable:
        b = p.brier()
        verdict = (
            "you were confident and right" if b <= 0.09
            else "reasonable" if b <= 0.25
            else "a confident miss — worth reflecting on"
        )
        print(t.dim(f"  brier {b:.3f} — {verdict}"))
    return 0


def cmd_edit(args, db: Database) -> int:
    p = db.get(args.id)
    if p is None:
        _eprint(t.red(f"error: no forecast #{args.id}"))
        return 1
    if args.statement is not None:
        p.statement = args.statement.strip()
    if args.prob is not None:
        try:
            p.probability = parse_probability(args.prob)
        except ProbabilityError as exc:
            _eprint(t.red(f"error: {exc}"))
            return 2
    if args.by is not None:
        if args.by == "":
            p.resolve_by = None
        else:
            try:
                p.resolve_by = parse_date(args.by)
            except DateParseError as exc:
                _eprint(t.red(f"error: {exc}"))
                return 2
    if args.tags is not None:
        p.tags = normalize_tags(args.tags)
    if args.note is not None:
        p.note = args.note
    # Re-validate probability bounds via the dataclass invariant.
    if not 0.0 <= p.probability <= 1.0:
        _eprint(t.red("error: probability out of range"))
        return 2
    db.update(p)
    print(t.green("✓ updated") + f"  {_fmt_prediction_line(p)}")
    return 0


def cmd_rm(args, db: Database) -> int:
    p = db.get(args.id)
    if p is None:
        _eprint(t.red(f"error: no forecast #{args.id}"))
        return 1
    if not args.yes:
        print(_fmt_prediction_line(p))
        reply = _read_line(t.yellow("delete this forecast? [y/N] "))
        if reply.strip().lower() not in ("y", "yes"):
            print("cancelled.")
            return 0
    db.delete(args.id)
    print(t.green(f"✓ deleted #{args.id}"))
    return 0


def cmd_due(args, db: Database) -> int:
    preds = db.list(status="open", due_only=True, newest_first=False)
    if not preds:
        print(t.green("nothing due — you're all caught up."))
        return 0
    print(t.bold(f"{len(preds)} forecast(s) due for resolution:\n"))
    for p in preds:
        print(_fmt_prediction_line(p))
    print(t.dim(f"\nresolve with:  augur resolve <id> yes|no|void"))
    return 0


def cmd_score(args, db: Database) -> int:
    if args.bins < 1:
        _eprint(t.red("error: --bins must be >= 1"))
        return 2
    since = _parse_optional_date(args.since)
    if since is None and args.since:
        return 2
    preds = db.scorable(tag=args.tag, since=since)
    pairs = pairs_from_predictions(preds)
    if not pairs:
        print(t.dim("no resolved (yes/no) forecasts to score yet."))
        print(t.dim("record some with `augur add`, resolve them with `augur resolve`,"))
        print(t.dim("or warm up with `augur practice`."))
        return 0

    stats = compute_stats(pairs, n_bins=args.bins)
    if args.json:
        print(json.dumps(_stats_to_dict(stats), indent=2))
        return 0

    _print_stats(stats, title=_score_title(args))
    print()
    print(charts.reliability_curve(stats.bins))
    print()
    print(charts.calibration_table(stats.bins))
    return 0


def cmd_trend(args, db: Database) -> int:
    if args.bins < 1:
        _eprint(t.red("error: --bins must be >= 1"))
        return 2
    preds = [p for p in db.scorable() if p.resolved_at is not None]
    preds.sort(key=lambda p: p.resolved_at or p.created_at)
    if len(preds) < 4:
        print(t.dim("need at least 4 resolved forecasts to show a trend."))
        return 0

    buckets = max(2, min(args.buckets, len(preds)))
    size = math.ceil(len(preds) / buckets)
    chunks = [preds[i:i + size] for i in range(0, len(preds), size)]
    briers = []
    for chunk in chunks:
        pairs = pairs_from_predictions(chunk)
        briers.append(compute_stats(pairs, n_bins=args.bins).brier if pairs else 0.0)

    print(t.heading("Brier score over time")
          + t.dim("  (lower is better — bars falling = improving)"))
    print("  " + charts.sparkline(briers) + "   "
          + " ".join(t.style(f"{b:.2f}", _brier_color(b)) for b in briers))
    overall = compute_stats(pairs_from_predictions(preds), n_bins=args.bins)
    print(t.dim(f"\n  overall brier {overall.brier:.3f} over {len(preds)} forecasts"))
    first, last = briers[0], briers[-1]
    if last < first - 0.02:
        print(t.green("  improving — recent forecasts are better calibrated"))
    elif last > first + 0.02:
        print(t.yellow("  trending worse — recent forecasts are less accurate"))
    else:
        print(t.dim("  roughly steady"))
    return 0


def cmd_practice(args, db: Database) -> int:
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    mode = args.mode
    if mode == practice_mod.INTERVAL:
        return _practice_interval(args, db, rng)
    return _practice_confidence(args, db, rng)


def cmd_export(args, db: Database) -> int:
    preds = db.list(status="all", newest_first=False)
    if args.format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["id", "statement", "probability", "created_at", "resolve_by",
             "resolved_at", "outcome", "tags", "note"]
        )
        for p in preds:
            writer.writerow([
                p.id, p.statement, p.probability, to_iso(p.created_at),
                to_iso(p.resolve_by) if p.resolve_by else "",
                to_iso(p.resolved_at) if p.resolved_at else "",
                p.outcome.value, " ".join(p.tags), p.note,
            ])
        payload = out.getvalue()
    else:
        payload = json.dumps([_prediction_to_dict(p) for p in preds], indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload)
        print(t.green(f"✓ exported {len(preds)} forecast(s) to {args.output}"))
    else:
        sys.stdout.write(payload)
        if not payload.endswith("\n"):
            sys.stdout.write("\n")
    return 0


def cmd_import(args, db: Database) -> int:
    try:
        with open(args.file, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        _eprint(t.red(f"error: {exc}"))
        return 1
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _eprint(t.red(f"error: invalid JSON: {exc}"))
        return 1
    if not isinstance(data, list):
        _eprint(t.red("error: expected a JSON array of forecasts"))
        return 1

    added = 0
    for entry in data:
        if not isinstance(entry, dict):
            _eprint(t.yellow("skipping malformed entry: not a JSON object"))
            continue
        try:
            pred = _prediction_from_dict(entry)
        except (KeyError, ValueError, TypeError) as exc:
            _eprint(t.yellow(f"skipping malformed entry: {exc}"))
            continue
        pred.id = None  # let the DB assign fresh ids
        db.add(pred)
        added += 1
    print(t.green(f"✓ imported {added} forecast(s)"))
    return 0


def cmd_stats(args, db: Database) -> int:
    counts = db.counts()
    preds = db.scorable()
    pairs = pairs_from_predictions(preds)
    parts = [
        f"{t.bold(str(counts['total']))} forecasts",
        f"{t.yellow(str(counts.get('open', 0)))} open",
    ]
    if counts.get("due"):
        parts.append(t.red(f"{counts['due']} due"))
    parts.append(f"{counts.get('yes', 0) + counts.get('no', 0)} scored")
    if pairs:
        stats = compute_stats(pairs)
        parts.append("brier " + t.style(f"{stats.brier:.3f}", _brier_color(stats.brier)))
    print(t.dim(" · ").join(parts))
    return 0


def cmd_dashboard(args, db: Database) -> int:
    """Default view when no sub-command is given."""
    n_num, n_bin = bank.counts()
    print(t.heading("augur") + t.dim(f"  v{__version__} — calibration trainer & forecasting journal"))
    print()
    cmd_stats(args, db)
    due = db.list(status="open", due_only=True)
    if due:
        print(t.red(f"\n{len(due)} forecast(s) due — run `augur due`"))
    print(t.dim("\ncommands: add · list · resolve · due · score · trend · practice"))
    print(t.dim(f"warm up anytime: `augur practice` ({n_num} numeric, {n_bin} true/false questions)"))
    return 0


# ---------------------------------------------------------------------------
# practice loops (interactive)
# ---------------------------------------------------------------------------


def _practice_interval(args, db: Database, rng: random.Random) -> int:
    questions = practice_mod.sample_numeric(args.n, rng=rng)
    if not questions:
        _eprint(t.red("no numeric questions available"))
        return 1
    print(t.heading("Interval calibration drill"))
    print(t.dim(
        "For each question give a range you are 90% sure contains the answer.\n"
        "Enter low and high (e.g. `1500 2000`). Blank line or 'q' to stop.\n"
    ))
    results = []
    for i, q in enumerate(questions, 1):
        unit = f" ({q.unit})" if q.unit else ""
        raw = _read_line(f"{t.bold(f'{i}.')} {q.prompt}{unit}\n   90% range: ")
        if raw.strip().lower() in ("q", "quit", ""):
            break
        parsed = _parse_two_numbers(raw)
        if parsed is None:
            print(t.yellow("   (enter two numbers, e.g. `10 20`)"))
            continue
        low, high = parsed
        res = practice_mod.score_interval(q, low, high)
        results.append(res)
        mark = t.green("✓ contained") if res.hit else t.red("✗ missed")
        print(f"   answer: {t.bold(_fmt_number(q.answer))}{unit}  {mark}\n")

    if not results:
        print(t.dim("no answers recorded."))
        return 0
    report = practice_mod.interval_report(results, target=practice_mod.DEFAULT_TARGET)
    print(t.heading("Result"))
    pct = format_probability(report.coverage)
    color = "green" if "well calibrated" in report.verdict else "yellow"
    print(f"  your 90% ranges contained the truth {t.bold(pct)} of the time "
          f"({report.hits}/{report.n})")
    print("  " + t.style(report.verdict, color))
    if not args.no_save:
        _save_interval(db, results)
    return 0


def _practice_confidence(args, db: Database, rng: random.Random) -> int:
    questions = practice_mod.sample_binary(args.n, rng=rng)
    if not questions:
        _eprint(t.red("no true/false questions available"))
        return 1
    print(t.heading("Confidence calibration drill"))
    print(t.dim(
        "Say whether each statement is true or false, and how sure you are.\n"
        "Answer like `t 80` (true, 80% sure) or `f 60`. Blank line or 'q' to stop.\n"
    ))
    results = []
    for i, q in enumerate(questions, 1):
        raw = _read_line(f"{t.bold(f'{i}.')} {q.prompt}\n   t/f + confidence: ")
        low = raw.strip().lower()
        if low in ("q", "quit", ""):
            break
        parsed = _parse_tf_confidence(low)
        if parsed is None:
            print(t.yellow("   (answer like `t 80` or `f 55`)"))
            continue
        said_true, conf = parsed
        res = practice_mod.score_confidence(q, said_true, conf)
        results.append(res)
        truth = t.green("TRUE") if q.answer else t.red("FALSE")
        mark = t.green("✓") if res.correct else t.red("✗")
        print(f"   actually {truth}  {mark}\n")

    if not results:
        print(t.dim("no answers recorded."))
        return 0
    stats = practice_mod.confidence_report(results)
    print(t.heading("Result"))
    _print_stats(stats, title=None)
    print()
    print(charts.calibration_table(stats.bins))
    if not args.no_save:
        _save_confidence(db, results)
    return 0


def _save_interval(db: Database, results) -> None:
    session = to_iso(now_utc())
    rows = [{
        "session": session, "mode": practice_mod.INTERVAL,
        "created_at": to_iso(now_utc()), "confidence": None, "correct": None,
        "ci_low": r.low, "ci_high": r.high, "truth": float(r.question.answer),
        "hit": 1 if r.hit else 0,
    } for r in results]
    db.record_practice(rows)


def _save_confidence(db: Database, results) -> None:
    session = to_iso(now_utc())
    rows = [{
        "session": session, "mode": practice_mod.CONFIDENCE,
        "created_at": to_iso(now_utc()), "confidence": r.confidence,
        "correct": 1 if r.correct else 0, "ci_low": None, "ci_high": None,
        "truth": 1.0 if r.question.answer else 0.0, "hit": 1 if r.correct else 0,
    } for r in results]
    db.record_practice(rows)


# ---------------------------------------------------------------------------
# stats printing
# ---------------------------------------------------------------------------


def _score_title(args) -> str:
    bits = []
    if args.tag:
        bits.append(f"#{args.tag}")
    if args.since:
        bits.append(f"since {args.since}")
    suffix = f" ({', '.join(bits)})" if bits else ""
    return f"Calibration report{suffix}"


def _print_stats(stats, title: Optional[str]) -> None:
    if title:
        print(t.heading(title))
    b = stats.brier
    print(f"  forecasts scored : {t.bold(str(stats.n))}")
    print(f"  brier score      : {t.style(f'{b:.3f}', _brier_color(b))}   "
          + t.dim("(0 perfect · 0.25 = always 50%)"))
    skill = stats.brier_skill
    if not math.isnan(skill):
        sc = "green" if skill > 0 else "red"
        print(f"  brier skill      : {t.style(f'{skill:+.3f}', sc)}   "
              + t.dim("(vs. always guessing the base rate)"))
    print(f"  log score        : {stats.log_score:.3f} nats "
          + t.dim(f"({stats.log_score_bits:.3f} bits)"))
    print(f"  base rate        : {format_probability(stats.base_rate)} "
          + t.dim("of statements came true"))
    print(f"  reliability      : {stats.reliability:.4f}  " + t.dim("(calibration error, lower better)"))
    print(f"  resolution       : {stats.resolution:.4f}  " + t.dim("(discrimination, higher better)"))
    oc = stats.overconfidence
    if abs(oc) < 0.03:
        verdict = t.green("well-matched")
    elif oc > 0:
        verdict = t.yellow(f"overconfident by {format_probability(oc)}")
    else:
        verdict = t.yellow(f"underconfident by {format_probability(-oc)}")
    print(f"  confidence       : you felt {format_probability(stats.mean_confidence)} sure, "
          f"were right {format_probability(stats.accuracy)} of the time — {verdict}")


def _stats_to_dict(stats) -> dict:
    return {
        "n": stats.n,
        "brier": stats.brier,
        "brier_skill": None if math.isnan(stats.brier_skill) else stats.brier_skill,
        "log_score_nats": stats.log_score,
        "log_score_bits": stats.log_score_bits,
        "base_rate": stats.base_rate,
        "reliability": stats.reliability,
        "resolution": stats.resolution,
        "uncertainty": stats.uncertainty,
        "mean_confidence": stats.mean_confidence,
        "accuracy": stats.accuracy,
        "overconfidence": stats.overconfidence,
        "bins": [
            {
                "low": b.low, "high": b.high, "count": b.count,
                "mean_pred": b.mean_pred if b.count else None,
                "observed": b.observed if b.count else None,
            }
            for b in stats.bins
        ],
    }


# ---------------------------------------------------------------------------
# parsing helpers
# ---------------------------------------------------------------------------


def _parse_outcome(text: str) -> Optional[Outcome]:
    key = text.strip().lower()
    mapping = {
        "yes": Outcome.YES, "y": Outcome.YES, "true": Outcome.YES, "1": Outcome.YES,
        "no": Outcome.NO, "n": Outcome.NO, "false": Outcome.NO, "0": Outcome.NO,
        "void": Outcome.VOID, "v": Outcome.VOID, "cancel": Outcome.VOID,
    }
    return mapping.get(key)


def _parse_optional_date(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return parse_date(text)
    except DateParseError as exc:
        _eprint(t.red(f"error: {exc}"))
        return None


def _parse_two_numbers(text: str):
    parts = text.replace(",", " ").replace("..", " ").split()
    nums = []
    for part in parts:
        try:
            nums.append(float(part))
        except ValueError:
            continue
    if len(nums) < 2:
        return None
    return nums[0], nums[1]


def _parse_tf_confidence(text: str):
    parts = text.replace("%", "").split()
    if not parts:
        return None
    head = parts[0]
    if head in ("t", "true", "y", "yes"):
        said_true = True
    elif head in ("f", "false", "n", "no"):
        said_true = False
    else:
        return None
    conf = 0.75
    if len(parts) >= 2:
        try:
            value = float(parts[1])
        except ValueError:
            return None
        conf = value / 100 if value > 1 else value
    return said_true, conf


def _fmt_number(x: float) -> str:
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.2f}"


def _local(dt: datetime) -> str:
    """Render a UTC datetime in the local timezone, human friendly."""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _read_line(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


# ---------------------------------------------------------------------------
# argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="augur",
        description="Log forecasts, resolve them, and train your calibration.",
    )
    parser.add_argument("--version", action="version", version=f"augur {__version__}")
    parser.add_argument("--db", help="path to the database file (default: XDG data dir)")
    color = parser.add_mutually_exclusive_group()
    color.add_argument("--color", dest="color", action="store_true", default=None,
                       help="force colour output")
    color.add_argument("--no-color", dest="color", action="store_false",
                       help="disable colour output")

    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="record a new forecast")
    p_add.add_argument("statement", help="what you are forecasting (quote it)")
    p_add.add_argument("-p", "--prob", required=True,
                       help="probability it happens: 70, 70%%, or 0.7")
    p_add.add_argument("--by", "--deadline", dest="by", help="resolve-by date (e.g. 2026-12-31, +30d)")
    p_add.add_argument("--tags", nargs="*", help="tags for grouping")
    p_add.add_argument("--note", help="rationale or notes")
    p_add.set_defaults(func=cmd_add)

    for name in ("list", "ls"):
        p_list = sub.add_parser(name, help="list forecasts")
        p_list.add_argument("--status", default="all",
                            choices=["all", "open", "resolved", "scored", "yes", "no", "void"])
        p_list.add_argument("--tag", help="only forecasts with this tag")
        p_list.add_argument("--since", help="only forecasts created since this date")
        p_list.add_argument("--due", action="store_true", help="only overdue open forecasts")
        p_list.add_argument("--oldest", action="store_true", help="oldest first")
        p_list.add_argument("--json", action="store_true", help="machine-readable output")
        p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show one forecast")
    p_show.add_argument("id", type=int)
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_res = sub.add_parser("resolve", help="resolve a forecast")
    p_res.add_argument("id", type=int)
    p_res.add_argument("outcome", help="yes | no | void")
    p_res.add_argument("--at", help="resolution date (default: now)")
    p_res.add_argument("--note", help="update the note when resolving")
    p_res.set_defaults(func=cmd_resolve)

    p_edit = sub.add_parser("edit", help="edit a forecast")
    p_edit.add_argument("id", type=int)
    p_edit.add_argument("--statement")
    p_edit.add_argument("-p", "--prob")
    p_edit.add_argument("--by", help="new resolve-by date, or empty string to clear")
    p_edit.add_argument("--tags", nargs="*")
    p_edit.add_argument("--note")
    p_edit.set_defaults(func=cmd_edit)

    p_rm = sub.add_parser("rm", help="delete a forecast")
    p_rm.add_argument("id", type=int)
    p_rm.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    p_rm.set_defaults(func=cmd_rm)

    p_due = sub.add_parser("due", help="show overdue open forecasts")
    p_due.set_defaults(func=cmd_due)

    p_score = sub.add_parser("score", help="calibration report")
    p_score.add_argument("--tag", help="restrict to a tag")
    p_score.add_argument("--since", help="restrict to forecasts created since a date")
    p_score.add_argument("--bins", type=int, default=10, help="number of calibration bins")
    p_score.add_argument("--json", action="store_true")
    p_score.set_defaults(func=cmd_score)

    p_trend = sub.add_parser("trend", help="Brier score over time")
    p_trend.add_argument("--buckets", type=int, default=6, help="number of time buckets")
    p_trend.add_argument("--bins", type=int, default=10)
    p_trend.set_defaults(func=cmd_trend)

    p_prac = sub.add_parser("practice", help="calibration drills")
    p_prac.add_argument("--mode", choices=[practice_mod.INTERVAL, practice_mod.CONFIDENCE],
                        default=practice_mod.INTERVAL,
                        help="interval (90%% ranges) or confidence (true/false)")
    p_prac.add_argument("-n", type=int, default=10, help="number of questions")
    p_prac.add_argument("--seed", type=int, help="fix the random seed (reproducible set)")
    p_prac.add_argument("--no-save", action="store_true", help="don't record results")
    p_prac.set_defaults(func=cmd_practice)

    p_exp = sub.add_parser("export", help="export forecasts")
    p_exp.add_argument("--format", choices=["json", "csv"], default="json")
    p_exp.add_argument("-o", "--output", help="write to a file instead of stdout")
    p_exp.set_defaults(func=cmd_export)

    p_imp = sub.add_parser("import", help="import forecasts from JSON")
    p_imp.add_argument("file")
    p_imp.set_defaults(func=cmd_import)

    p_stats = sub.add_parser("stats", help="one-line summary")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    t.set_color(args.color)

    db_path = args.db or default_db_path()
    db = Database(db_path)
    try:
        if not getattr(args, "command", None):
            return cmd_dashboard(args, db)
        return args.func(args, db)
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
