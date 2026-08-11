"""m0006 — non-authorizing approval advice records."""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approval_advice (
            id TEXT PRIMARY KEY,
            approval_id TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            rationale TEXT NOT NULL,
            risks_json TEXT NOT NULL,
            evidence_gaps_json TEXT NOT NULL,
            conditions_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(approval_id) REFERENCES approval_requests(id)
        );
        CREATE INDEX IF NOT EXISTS ix_approval_advice_approval
            ON approval_advice(approval_id);
        """
    )
