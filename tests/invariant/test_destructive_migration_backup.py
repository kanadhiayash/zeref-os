from __future__ import annotations

import sqlite3
import types
from pathlib import Path

from shiroe.storage.state import StateDB


def _integrity_check(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def test_destructive_migration_creates_verifiable_backup(tmp_path, monkeypatch):
    with StateDB(tmp_path) as db:
        db.connect().execute("CREATE TABLE preexisting_state(id TEXT)")

    module = types.SimpleNamespace(DESTRUCTIVE=True, up=lambda conn: conn.execute("CREATE TABLE destructive_probe(id TEXT)"))
    import shiroe.migrations as migrations

    monkeypatch.setattr(migrations, "_discover", lambda: [(3, "synthetic_destructive")])
    monkeypatch.setattr(migrations.importlib, "import_module", lambda name: module)

    StateDB(tmp_path).migrate()

    backups = list((tmp_path / "memory" / "state" / "backups").glob("shiroe.sqlite.*.bak"))
    assert backups
    assert _integrity_check(backups[0]) == "ok"
