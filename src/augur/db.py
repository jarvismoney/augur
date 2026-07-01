"""SQLite persistence for predictions and practice results.

The database is a single file you own. Schema changes are handled by a tiny
forward-only migration list keyed off ``PRAGMA user_version`` so upgrading the
tool never loses data.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .models import Outcome, Prediction, normalize_tags
from .util import from_iso, now_utc, to_iso

SCHEMA_VERSION = 1

# Forward-only migrations. Index i upgrades a database from user_version i to
# i + 1. Never edit an existing entry once released; append a new one instead.
_MIGRATIONS: list[str] = [
    # 0 -> 1: initial schema
    """
    CREATE TABLE predictions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        statement   TEXT    NOT NULL,
        probability REAL    NOT NULL,
        created_at  TEXT    NOT NULL,
        resolve_by  TEXT,
        resolved_at TEXT,
        outcome     TEXT    NOT NULL DEFAULT 'open',
        tags        TEXT    NOT NULL DEFAULT '',
        note        TEXT    NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_predictions_outcome ON predictions(outcome);
    CREATE INDEX idx_predictions_resolve_by ON predictions(resolve_by);

    CREATE TABLE practice_results (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        session      TEXT    NOT NULL,
        mode         TEXT    NOT NULL,
        created_at   TEXT    NOT NULL,
        confidence   REAL,
        correct      INTEGER,
        ci_low       REAL,
        ci_high      REAL,
        truth        REAL,
        hit          INTEGER
    );
    """,
]


class Database:
    """A thin, well-typed wrapper around a SQLite connection."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # -- lifecycle ---------------------------------------------------------

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        while version < SCHEMA_VERSION:
            self.conn.executescript(_MIGRATIONS[version])
            version += 1
            self.conn.execute(f"PRAGMA user_version = {version}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- row mapping -------------------------------------------------------

    @staticmethod
    def _row_to_prediction(row: sqlite3.Row) -> Prediction:
        return Prediction(
            id=row["id"],
            statement=row["statement"],
            probability=row["probability"],
            created_at=from_iso(row["created_at"]),
            resolve_by=from_iso(row["resolve_by"]) if row["resolve_by"] else None,
            resolved_at=from_iso(row["resolved_at"]) if row["resolved_at"] else None,
            outcome=Outcome(row["outcome"]),
            tags=normalize_tags(row["tags"]),
            note=row["note"] or "",
        )

    # -- create / update ---------------------------------------------------

    def add(self, prediction: Prediction) -> Prediction:
        """Insert a prediction and return it with its assigned id."""
        cur = self.conn.execute(
            """
            INSERT INTO predictions
                (statement, probability, created_at, resolve_by,
                 resolved_at, outcome, tags, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction.statement,
                prediction.probability,
                to_iso(prediction.created_at),
                to_iso(prediction.resolve_by) if prediction.resolve_by else None,
                to_iso(prediction.resolved_at) if prediction.resolved_at else None,
                prediction.outcome.value,
                ",".join(prediction.tags),
                prediction.note,
            ),
        )
        self.conn.commit()
        prediction.id = int(cur.lastrowid)
        return prediction

    def update(self, prediction: Prediction) -> None:
        """Persist all mutable fields of an existing prediction."""
        if prediction.id is None:
            raise ValueError("cannot update a prediction without an id")
        self.conn.execute(
            """
            UPDATE predictions
               SET statement = ?, probability = ?, resolve_by = ?,
                   resolved_at = ?, outcome = ?, tags = ?, note = ?
             WHERE id = ?
            """,
            (
                prediction.statement,
                prediction.probability,
                to_iso(prediction.resolve_by) if prediction.resolve_by else None,
                to_iso(prediction.resolved_at) if prediction.resolved_at else None,
                prediction.outcome.value,
                ",".join(prediction.tags),
                prediction.note,
                prediction.id,
            ),
        )
        self.conn.commit()

    def delete(self, prediction_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM predictions WHERE id = ?", (prediction_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # -- read --------------------------------------------------------------

    def get(self, prediction_id: int) -> Optional[Prediction]:
        row = self.conn.execute(
            "SELECT * FROM predictions WHERE id = ?", (prediction_id,)
        ).fetchone()
        return self._row_to_prediction(row) if row else None

    def list(
        self,
        *,
        status: str = "all",
        tag: Optional[str] = None,
        since: Optional[datetime] = None,
        due_only: bool = False,
        newest_first: bool = True,
    ) -> list[Prediction]:
        """Query predictions with common filters applied.

        ``status`` is one of ``all``, ``open``, ``resolved``, ``scored``,
        ``yes``, ``no``, ``void``.
        """
        clauses: list[str] = []
        params: list[object] = []

        if status == "open":
            clauses.append("outcome = 'open'")
        elif status == "resolved":
            clauses.append("outcome != 'open'")
        elif status == "scored":
            clauses.append("outcome IN ('yes', 'no')")
        elif status in ("yes", "no", "void"):
            clauses.append("outcome = ?")
            params.append(status)
        elif status != "all":
            raise ValueError(f"unknown status filter: {status!r}")

        if since is not None:
            clauses.append("created_at >= ?")
            params.append(to_iso(since))

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "DESC" if newest_first else "ASC"
        rows = self.conn.execute(
            f"SELECT * FROM predictions{where} ORDER BY id {order}", params
        ).fetchall()

        results = [self._row_to_prediction(r) for r in rows]

        # Tag and due filters are applied in Python: tags are stored normalized
        # so an exact word match is clearer here than a fragile SQL LIKE.
        if tag:
            wanted = normalize_tags(tag)
            results = [p for p in results if all(t in p.tags for t in wanted)]
        if due_only:
            results = [p for p in results if p.is_due()]
        return results

    def resolve(
        self,
        prediction_id: int,
        outcome: Outcome,
        *,
        resolved_at: Optional[datetime] = None,
        note: Optional[str] = None,
    ) -> Optional[Prediction]:
        """Resolve a prediction to an outcome; returns the updated record."""
        prediction = self.get(prediction_id)
        if prediction is None:
            return None
        prediction.outcome = outcome
        prediction.resolved_at = (
            resolved_at if outcome.is_resolved else None
        ) or (now_utc() if outcome.is_resolved else None)
        if note is not None:
            prediction.note = note
        self.update(prediction)
        return prediction

    def scorable(
        self, *, tag: Optional[str] = None, since: Optional[datetime] = None
    ) -> list[Prediction]:
        """All resolved-and-scorable predictions, oldest first (for scoring)."""
        return self.list(
            status="scored", tag=tag, since=since, newest_first=False
        )

    def counts(self) -> dict[str, int]:
        """Return a summary of how many predictions are in each state."""
        rows = self.conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM predictions GROUP BY outcome"
        ).fetchall()
        counts = {row["outcome"]: row["n"] for row in rows}
        counts["total"] = sum(counts.values())
        counts.setdefault("open", 0)
        due = sum(1 for p in self.list(status="open") if p.is_due())
        counts["due"] = due
        return counts

    # -- practice ----------------------------------------------------------

    def record_practice(self, rows: Iterable[dict]) -> None:
        self.conn.executemany(
            """
            INSERT INTO practice_results
                (session, mode, created_at, confidence, correct,
                 ci_low, ci_high, truth, hit)
            VALUES
                (:session, :mode, :created_at, :confidence, :correct,
                 :ci_low, :ci_high, :truth, :hit)
            """,
            list(rows),
        )
        self.conn.commit()

    def practice_rows(self, *, mode: Optional[str] = None) -> list[sqlite3.Row]:
        if mode:
            return self.conn.execute(
                "SELECT * FROM practice_results WHERE mode = ? ORDER BY id",
                (mode,),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM practice_results ORDER BY id"
        ).fetchall()
