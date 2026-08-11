"""StateDB — thin SQLite wrapper for the vNext canonical state DB.

Path convention: ``<root>/memory/state/shiroe.sqlite`` — a separate file from
the v1 store (:data:`shiroe.compat.legacy_identity.LEGACY_V1_STATE_DB_NAME`)
so v1 consumers are untouched during the migration window.
"""

from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path

from shiroe.compat.legacy_identity import LEGACY_VNEXT_STATE_DB_NAME
from shiroe.migrations import current_version, migrate


DB_RELPATH = Path("memory") / "state" / "shiroe.sqlite"
# Pre-rebrand filename. This is canonical state, not a cache, so an existing
# project's database is renamed into place on first open -- leaving it behind
# would present as total memory loss rather than as a rename.
_LEGACY_DB_RELPATH = Path("memory") / "state" / LEGACY_VNEXT_STATE_DB_NAME


class StateDB:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.path = self.root / DB_RELPATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._adopt_legacy_db()
        self._conn: sqlite3.Connection | None = None

    def _adopt_legacy_db(self) -> None:
        """Rename a pre-rebrand database into place, once.

        Only when the new path does not exist: if both are present the new
        one is authoritative and the old is left untouched for the operator
        to inspect rather than silently overwritten.
        """
        legacy = self.root / _LEGACY_DB_RELPATH
        if self.path.exists() or not legacy.exists():
            return
        warnings.warn(
            f"{LEGACY_VNEXT_STATE_DB_NAME} is deprecated; renaming it to "
            f"{self.path.name} (see docs/DEPRECATIONS.md, removal in 4.0.0).",
            DeprecationWarning,
            stacklevel=3,
        )
        legacy.rename(self.path)
        for suffix in ("-wal", "-shm"):
            side = legacy.with_name(legacy.name + suffix)
            if side.exists():
                side.rename(self.path.with_name(self.path.name + suffix))

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, timeout=5.0)
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA busy_timeout = 5000")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def migrate(self, *, target_version: int | None = None) -> list[str]:
        conn = self.connect()
        return migrate(conn, target_version=target_version)

    def schema_version(self) -> int:
        return current_version(self.connect())

    def tables(self) -> list[str]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]

    def __enter__(self) -> "StateDB":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
