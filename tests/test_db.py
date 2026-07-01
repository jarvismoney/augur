"""Tests for the SQLite storage layer."""

from datetime import timedelta

import pytest

from augur.db import Database
from augur.models import Outcome, Prediction
from augur.util import now_utc


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "t.db")
    yield database
    database.close()


def _pred(statement="s", prob=0.5, **kw):
    return Prediction(statement=statement, probability=prob, created_at=now_utc(), **kw)


def test_add_assigns_id_and_get_roundtrips(db):
    p = db.add(_pred("hello", 0.7, tags=["a", "b"], note="why"))
    assert p.id is not None
    fetched = db.get(p.id)
    assert fetched.statement == "hello"
    assert fetched.probability == pytest.approx(0.7)
    assert fetched.tags == ["a", "b"]
    assert fetched.note == "why"


def test_update_persists_changes(db):
    p = db.add(_pred())
    p.statement = "changed"
    p.probability = 0.9
    p.tags = ["x"]
    db.update(p)
    assert db.get(p.id).statement == "changed"
    assert db.get(p.id).probability == pytest.approx(0.9)
    assert db.get(p.id).tags == ["x"]


def test_delete(db):
    p = db.add(_pred())
    assert db.delete(p.id) is True
    assert db.get(p.id) is None
    assert db.delete(9999) is False


def test_resolve_sets_outcome_and_timestamp(db):
    p = db.add(_pred(prob=0.8))
    resolved = db.resolve(p.id, Outcome.YES)
    assert resolved.outcome is Outcome.YES
    assert resolved.resolved_at is not None
    assert db.resolve(9999, Outcome.YES) is None


def test_list_status_filters(db):
    a = db.add(_pred("open one"))
    b = db.add(_pred("yes one"))
    c = db.add(_pred("void one"))
    db.resolve(b.id, Outcome.YES)
    db.resolve(c.id, Outcome.VOID)

    assert {p.id for p in db.list(status="open")} == {a.id}
    assert {p.id for p in db.list(status="resolved")} == {b.id, c.id}
    assert {p.id for p in db.list(status="scored")} == {b.id}
    assert {p.id for p in db.list(status="void")} == {c.id}
    assert len(db.list(status="all")) == 3


def test_list_tag_filter_requires_all_tags(db):
    db.add(_pred("both", tags=["crypto", "macro"]))
    db.add(_pred("one", tags=["crypto"]))
    assert len(db.list(tag="crypto")) == 2
    assert len(db.list(tag="crypto macro")) == 1


def test_list_since_and_due(db):
    old = _pred("old")
    old.created_at = now_utc() - timedelta(days=10)
    db.add(old)
    recent = db.add(_pred("recent"))
    since = now_utc() - timedelta(days=1)
    ids = {p.id for p in db.list(since=since)}
    assert recent.id in ids and old.id not in ids

    overdue = _pred("overdue")
    overdue.resolve_by = now_utc() - timedelta(days=1)
    db.add(overdue)
    due = db.list(status="open", due_only=True)
    assert all(p.is_due() for p in due)
    assert any(p.statement == "overdue" for p in due)


def test_counts(db):
    db.add(_pred())
    y = db.add(_pred())
    db.resolve(y.id, Outcome.YES)
    counts = db.counts()
    assert counts["total"] == 2
    assert counts["open"] == 1
    assert counts["yes"] == 1


def test_scorable_is_chronological(db):
    first = _pred("first", prob=0.6)
    first.created_at = now_utc() - timedelta(days=5)
    a = db.add(first)
    b = db.add(_pred("second", prob=0.7))
    db.resolve(a.id, Outcome.YES)
    db.resolve(b.id, Outcome.NO)
    scorable = db.scorable()
    assert [p.id for p in scorable] == [a.id, b.id]


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "m.db"
    d1 = Database(path)
    d1.add(_pred("persist"))
    d1.close()
    # Re-opening runs _migrate again; it must not error or lose data.
    d2 = Database(path)
    assert len(d2.list()) == 1
    assert d2.conn.execute("PRAGMA user_version").fetchone()[0] == 1
    d2.close()


def test_record_and_read_practice(db):
    rows = [{
        "session": "s1", "mode": "interval", "created_at": now_utc().isoformat(),
        "confidence": None, "correct": None, "ci_low": 1.0, "ci_high": 2.0,
        "truth": 1.5, "hit": 1,
    }]
    db.record_practice(rows)
    stored = db.practice_rows(mode="interval")
    assert len(stored) == 1
    assert stored[0]["hit"] == 1
