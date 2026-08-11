"""m0005 — persist canonical memory tags."""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_records)")}
    if "tags_json" not in columns:
        conn.execute("ALTER TABLE memory_records ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'")
