"""m0002 — run-level ownership + state versioning (SHR-060/061).

Two supervisors on the same ``run_id`` must not both commit to the
canonical store. This migration adds:

- ``team_runs.owner_token``  — nullable claim held by the current
  supervisor. Cleared on terminal states so resume can re-claim.
- ``team_runs.state_version`` — monotonic counter bumped on every
  state transition. Supervisors CAS on it so a lost update surfaces
  deterministically at commit time, not later at reconciliation.

Additive; no data rewrite.
"""

from __future__ import annotations

import sqlite3


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def up(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, "team_runs", "owner_token"):
        conn.execute("ALTER TABLE team_runs ADD COLUMN owner_token TEXT")
    if not _has_column(conn, "team_runs", "state_version"):
        conn.execute(
            "ALTER TABLE team_runs ADD COLUMN state_version INTEGER NOT NULL "
            "DEFAULT 0"
        )
