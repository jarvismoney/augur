"""Integration tests driving the CLI through main()."""

import json

import pytest

from augur.cli import main


@pytest.fixture()
def dbfile(tmp_path):
    return str(tmp_path / "c.db")


def run(dbfile, *args):
    """Invoke the CLI with colour disabled and a temp database."""
    return main(["--db", dbfile, "--no-color", *args])


def test_add_and_list(dbfile, capsys):
    assert run(dbfile, "add", "Will it rain", "-p", "70", "--tags", "weather") == 0
    assert "recorded" in capsys.readouterr().out
    assert run(dbfile, "list") == 0
    out = capsys.readouterr().out
    assert "Will it rain" in out
    assert "#weather" in out


def test_add_rejects_bad_probability(dbfile, capsys):
    assert run(dbfile, "add", "bad", "-p", "150") == 2
    assert "error" in capsys.readouterr().err


def test_resolve_then_score(dbfile, capsys):
    for i in range(6):
        run(dbfile, "add", f"claim {i}", "-p", "80")
    capsys.readouterr()
    for i in range(1, 7):
        # resolve most YES so an 80% forecaster looks roughly calibrated
        run(dbfile, "resolve", str(i), "yes" if i <= 5 else "no")
    capsys.readouterr()
    assert run(dbfile, "score") == 0
    out = capsys.readouterr().out
    assert "brier score" in out
    assert "forecasts scored" in out


def test_score_json_is_parseable(dbfile, capsys):
    run(dbfile, "add", "x", "-p", "60")
    run(dbfile, "resolve", "1", "yes")
    capsys.readouterr()
    assert run(dbfile, "score", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["n"] == 1
    assert "brier" in data


def test_show_missing_returns_1(dbfile, capsys):
    assert run(dbfile, "show", "42") == 1
    assert "no forecast" in capsys.readouterr().err


def test_stats_and_dashboard(dbfile, capsys):
    run(dbfile, "add", "x", "-p", "50")
    capsys.readouterr()
    assert run(dbfile, "stats") == 0
    assert "forecast" in capsys.readouterr().out
    # No sub-command => dashboard.
    assert main(["--db", dbfile, "--no-color"]) == 0
    assert "augur" in capsys.readouterr().out


def test_export_import_roundtrip(dbfile, tmp_path, capsys):
    run(dbfile, "add", "alpha", "-p", "70", "--tags", "a")
    run(dbfile, "add", "beta", "-p", "20", "--tags", "b")
    run(dbfile, "resolve", "1", "yes")
    export_path = str(tmp_path / "out.json")
    capsys.readouterr()
    assert run(dbfile, "export", "-o", export_path) == 0

    other = str(tmp_path / "other.db")
    assert run(other, "import", export_path) == 0
    assert "imported 2" in capsys.readouterr().out

    assert run(other, "list", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert {d["statement"] for d in data} == {"alpha", "beta"}
    # The resolved YES forecast survives the round trip.
    assert any(d["outcome"] == "yes" for d in data)


def test_edit_updates_fields(dbfile, capsys):
    run(dbfile, "add", "orig", "-p", "50")
    capsys.readouterr()
    assert run(dbfile, "edit", "1", "--prob", "90", "--statement", "new") == 0
    capsys.readouterr()
    assert run(dbfile, "show", "1", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["statement"] == "new"
    assert data["probability"] == pytest.approx(0.9)


def test_score_json_has_insight(dbfile, capsys):
    run(dbfile, "add", "x", "-p", "60")
    run(dbfile, "resolve", "1", "yes")
    capsys.readouterr()
    assert run(dbfile, "score", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert "insight" in data
    assert data["insight"]["tone"] in ("good", "warn", "info")
    assert data["insight"]["headline"]


def test_score_leads_with_plain_english(dbfile, capsys):
    run(dbfile, "add", "x", "-p", "60")
    run(dbfile, "resolve", "1", "yes")
    capsys.readouterr()
    assert run(dbfile, "score") == 0
    # Few forecasts => a friendly "warming up" verdict, not just a wall of stats.
    assert "warming up" in capsys.readouterr().out.lower()


def test_confidence_pair_reconstruction():
    from augur.cli import _confidence_pair_from_row
    assert _confidence_pair_from_row({"truth": 1.0, "correct": 1, "confidence": 0.8}) == (0.8, 1)
    assert _confidence_pair_from_row({"truth": 0.0, "correct": 0, "confidence": 0.8}) == (0.8, 0)
    p, o = _confidence_pair_from_row({"truth": 0.0, "correct": 1, "confidence": 0.9})
    assert (round(p, 6), o) == (0.1, 0)


def test_practice_progress_nudge(dbfile, capsys, monkeypatch):
    from augur.db import Database
    from augur.util import now_utc, to_iso

    db = Database(dbfile)
    db.record_practice([
        {"session": "s", "mode": "interval", "created_at": to_iso(now_utc()),
         "confidence": None, "correct": None, "ci_low": 0, "ci_high": 1,
         "truth": 1, "hit": 1 if i < 3 else 0}
        for i in range(6)
    ])
    db.close()

    answers = iter(["0 1000", "q"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert run(dbfile, "practice", "--mode", "interval", "-n", "2", "--seed", "1", "--no-save") == 0
    assert "earlier answers" in capsys.readouterr().out


def test_import_skips_malformed_entries(dbfile, tmp_path, capsys):
    # Regression: a non-object element used to crash import with a traceback.
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([
        "not an object",
        42,
        None,
        {"statement": "good one", "probability": 0.7},
    ]))
    assert run(dbfile, "import", str(bad)) == 0
    out = capsys.readouterr()
    assert "imported 1" in out.out
    assert "skipping malformed" in out.err


def test_score_rejects_nonpositive_bins(dbfile, capsys):
    run(dbfile, "add", "x", "-p", "60")
    run(dbfile, "resolve", "1", "yes")
    capsys.readouterr()
    assert run(dbfile, "score", "--bins", "0") == 2
    assert "bins" in capsys.readouterr().err
    assert run(dbfile, "trend", "--bins", "-1") == 2


def test_practice_no_save_with_seed(dbfile, capsys, monkeypatch):
    # Feed answers via a fake input() so the interactive loop is exercised.
    answers = iter(["1900 2000", "q"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert run(dbfile, "practice", "--mode", "interval", "-n", "3", "--seed", "1", "--no-save") == 0
    out = capsys.readouterr().out
    assert "Interval calibration drill" in out
