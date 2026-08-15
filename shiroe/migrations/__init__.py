"""Versioned SQLite migration runner (stdlib only, vNext ADR-0001).

Contract:
- Each migration is a module ``m####_slug`` under this package, exposing
  ``up(conn: sqlite3.Connection) -> None``.
- ``schema_version`` table records applied numbers with a UTC timestamp.
- ``migrate()`` applies pending migrations in numeric order, transactionally,
  idempotently (double-apply is a no-op).
- Migrations that drop or rewrite prior tables declare ``DESTRUCTIVE = True``;
  the runner creates and verifies one SQLite backup before applying the first
  pending destructive migration.

Used by :class:`shiroe.storage.state.StateDB`.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_MIGRATION_RE = re.compile(r"^m(\d{4})_[a-z0-9_]+$")


def _discover() -> list[tuple[int, str]]:
    """Return (number, module_name) pairs for every migration in the package,
    sorted by number ascending."""
    found: list[tuple[int, str]] = []
    pkg_path = Path(__file__).parent
    for info in pkgutil.iter_modules([str(pkg_path)]):
        m = _MIGRATION_RE.match(info.name)
        if m:
            found.append((int(m.group(1)), info.name))
    found.sort()
    return found


def _ensure_schema_version(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            number INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _applied(conn: sqlite3.Connection) -> set[int]:
    _ensure_schema_version(conn)
    return {row[0] for row in conn.execute("SELECT number FROM schema_version")}


def _has_preexisting_state(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table'
          AND name NOT IN ('schema_version', 'sqlite_sequence')
        LIMIT 1
        """
    ).fetchone()
    return rows is not None


def migrate(conn: sqlite3.Connection, *, target_version: int | None = None) -> list[str]:
    """Apply all pending migrations on ``conn``. Returns names applied."""
    had_preexisting_state = _has_preexisting_state(conn)
    applied = _applied(conn)
    should_backup_destructive = bool(applied) or had_preexisting_state
    ran: list[str] = []
    backed_up = False
    for number, name in _discover():
        if target_version is not None and number > target_version:
            continue
        if number in applied:
            continue
        module = importlib.import_module(f"{__name__}.{name}")
        if getattr(module, "DESTRUCTIVE", False) and should_backup_destructive and not backed_up:
            _backup_database(conn)
            backed_up = True
        with conn:  # implicit transaction
            module.up(conn)
            conn.execute(
                "INSERT INTO schema_version(number, name, applied_at) VALUES (?, ?, ?)",
                (number, name, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
        ran.append(name)
    return ran


def _backup_database(conn: sqlite3.Connection) -> Path:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None or not row[2]:
        raise RuntimeError("cannot back up destructive migration for in-memory database")
    source = Path(row[2])
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{source.name}.{stamp}.bak"
    backup = sqlite3.connect(target)
    try:
        conn.backup(backup)
        integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        backup.close()
    if integrity != "ok":
        target.unlink(missing_ok=True)
        raise RuntimeError(f"destructive migration backup failed integrity check: {integrity}")
    return target


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_schema_version(conn)
    row = conn.execute("SELECT COALESCE(MAX(number), 0) FROM schema_version").fetchone()
    return int(row[0])


def latest_version() -> int:
    discovered = _discover()
    return discovered[-1][0] if discovered else 0
