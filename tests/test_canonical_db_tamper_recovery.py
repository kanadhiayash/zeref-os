"""
Wave 10 (2/3): tampering the SQLite mirror must not survive as canonical state.

ADR-0001 makes SQLite a rebuildable *projection* of the append-only JSONL
event log; the log is canonical. This is the companion adversarial case to
`tests/test_replay_views.py::test_state_survives_deleting_the_database`,
which proves the mirror can be *deleted* and rebuilt. Here the mirror is not
deleted -- it is corrupted in place (an `UPDATE` that never goes through
`EventLog.append`, exactly what a direct SQLite edit or a compromised
process with file access could do), and the same rebuild path
(`shiroe state rebuild`'s `EventLog.replay_into`) is exercised to confirm it
overwrites the tampered row from the log rather than trusting it.

Note on `shiroe state verify`: it only walks the JSONL hash chain
(`EventLog.verify_chain`) and is silent on this class of tamper, because the
mutation never touches the JSONL file it inspects -- only the SQLite mirror.
The protection against mirror tampering is the rebuild path, not verify, so
that is what this file exercises and asserts against.
"""

from __future__ import annotations

from pathlib import Path

from shiroe.storage import views as views_mod
from shiroe.storage.events import EventLog
from shiroe.storage.records import write_record
from shiroe.storage.state import StateDB


def _seed_one(root: Path) -> tuple[StateDB, dict]:
    db = StateDB(root)
    db.migrate()
    conn = db.connect()
    log = EventLog(root, mirror_conn=conn)
    env = write_record(
        conn, log, owner="tests",
        id_="rec_tamper", kind="decision",
        title="Canonical title", claim="Canonical claim from the event log.",
        summary="",
    )
    return db, env


def _row(conn) -> tuple:
    return conn.execute(
        "SELECT id, title, claim FROM memory_records WHERE id=?", ("rec_tamper",)
    ).fetchone()


def test_tampered_mirror_row_is_overwritten_by_rebuild(tmp_path: Path) -> None:
    """A direct SQLite mutation is not canonical and does not survive a rebuild."""
    db, _env = _seed_one(tmp_path)
    conn = db.connect()
    canonical = _row(conn)
    assert canonical == ("rec_tamper", "Canonical title", "Canonical claim from the event log.")

    # Tamper the mirror directly -- bypassing EventLog.append entirely, the
    # same shape of attack as an out-of-band edit to shiroe.sqlite.
    conn.execute(
        "UPDATE memory_records SET title=?, claim=? WHERE id=?",
        ("TAMPERED title", "TAMPERED claim injected outside the event log", "rec_tamper"),
    )
    conn.commit()
    tampered = _row(conn)
    assert tampered != canonical, "fixture failed to tamper the mirror; test would be vacuous"

    # This is what `shiroe state rebuild` does: replay the canonical JSONL
    # log back into the mirror connection.
    EventLog(tmp_path, mirror_conn=conn).replay_into(conn)

    rebuilt = _row(conn)
    assert rebuilt == canonical, (
        "tampered mirror row survived a rebuild from the canonical event log: "
        f"{rebuilt!r}"
    )
    assert "TAMPERED" not in rebuilt[1] and "TAMPERED" not in rebuilt[2]


def test_tampered_mirror_does_not_leak_into_rendered_views_after_rebuild(tmp_path: Path) -> None:
    """The generated-views projection must reflect the rebuilt state, not the tamper."""
    db, _env = _seed_one(tmp_path)
    conn = db.connect()

    conn.execute(
        "UPDATE memory_records SET title=?, claim=? WHERE id=?",
        ("TAMPERED title", "TAMPERED claim injected outside the event log", "rec_tamper"),
    )
    conn.commit()

    views_mod.render_all(tmp_path, conn)
    tampered_view = (tmp_path / "memory" / "views" / "decisions.md").read_text(encoding="utf-8")
    assert "TAMPERED" in tampered_view, "fixture failed to tamper before rendering; test would be vacuous"

    EventLog(tmp_path, mirror_conn=conn).replay_into(conn)
    views_mod.render_all(tmp_path, conn)

    rebuilt_view = (tmp_path / "memory" / "views" / "decisions.md").read_text(encoding="utf-8")
    assert "TAMPERED" not in rebuilt_view, "tampered content survived into the rebuilt view"
    assert "Canonical claim from the event log." in rebuilt_view


def test_state_verify_is_silent_on_mirror_only_tamper_documenting_the_boundary(tmp_path: Path) -> None:
    """Documents why `state verify` is not the mirror-tamper protection.

    `verify_chain` only inspects the JSONL log; it never reads
    `memory_records`. A mirror-only tamper therefore leaves it passing, which
    is why the rebuild-based tests above are the actual protective behavior
    for this adversarial case, not `state verify`.
    """
    db, _env = _seed_one(tmp_path)
    conn = db.connect()
    conn.execute(
        "UPDATE memory_records SET title=?, claim=? WHERE id=?",
        ("TAMPERED title", "TAMPERED claim", "rec_tamper"),
    )
    conn.commit()

    # Must not raise: the tamper is invisible to the hash-chain check by
    # construction, since it never touched the JSONL file.
    EventLog(tmp_path, mirror_conn=conn).verify_chain()

    # The tamper is still sitting in the mirror at this point -- verify did
    # not, and structurally cannot, clean it up.
    assert _row(conn)[1] == "TAMPERED title"
