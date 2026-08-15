"""
Canonical state must be reconstructable from the append-only log.

ADR-0001 makes SQLite the canonical *current state* and JSONL the canonical
*history*. That pairing only means something if the history can actually rebuild
the state: if it cannot, the JSONL log is a write-only audit trail and SQLite is
the sole copy of the truth, which is the single-point-of-failure the split was
introduced to remove.

The gate is deliberately destructive: delete the database, replay the log,
regenerate the views, and compare both the canonical records and the view
digests against what was there before.

Two things had to change for this to be provable at all, and each has its own
test below so a regression names itself:

* `memory_records` was written only by the importer and emitted no event, so a
  replay rebuilt `memory_events` and left canonical state empty.
* Views stamped `datetime.now()` into their header, so two renders of identical
  state never agreed byte for byte and no digest comparison was possible.
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

from shiroe.storage import views as views_mod
from shiroe.storage.events import EventLog
from shiroe.storage.records import supersede_record, write_record
from shiroe.storage.state import StateDB


RECORDS = [
    dict(id_="rec_alpha", kind="decision", title="Adopt SQLite as current state",
         claim="SQLite holds current state.", summary="ADR-0001."),
    dict(id_="rec_beta", kind="risk", title="Replay is unproven",
         claim="History that cannot rebuild state is not history.", summary=""),
    dict(id_="rec_gamma", kind="context", title="Views are generated",
         claim="Markdown views are derived projections.", summary="Never canonical."),
]

RECORD_COLUMNS = (
    "id, kind, title, claim, summary, status, confidence, evidence_grade, "
    "privacy_class, authority, scope, valid_from, valid_until, owner, "
    "schema_version, archived"
)


def _seed(root: Path) -> StateDB:
    """A store carrying records written through the event-sourced path."""
    db = StateDB(root)
    db.migrate()
    conn = db.connect()
    log = EventLog(root, mirror_conn=conn)
    for rec in RECORDS:
        write_record(conn, log, owner="tests", **rec)
    return db


def _records(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        f"SELECT {RECORD_COLUMNS} FROM memory_records ORDER BY id"
    ).fetchall()


def _view_digests(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "memory" / "views").glob("*.md"))
    }


def test_views_are_byte_stable_across_renders(tmp_path: Path) -> None:
    """Identical state must render identical bytes, or nothing can be compared.

    The header carried `datetime.now()`, so every render differed and any run
    that regenerated views left the worktree dirty.
    """
    db = _seed(tmp_path)
    conn = db.connect()

    views_mod.render_all(tmp_path, conn)
    first = _view_digests(tmp_path)
    views_mod.render_all(tmp_path, conn)
    second = _view_digests(tmp_path)

    assert first, "no views were written; this test would pass vacuously"
    assert first == second, "two renders of unchanged state disagree"


def test_state_survives_deleting_the_database(tmp_path: Path) -> None:
    """The gate: delete SQLite, replay JSONL, and compare records and views."""
    db = _seed(tmp_path)
    conn = db.connect()
    before_records = _records(conn)
    views_mod.render_all(tmp_path, conn)
    before_views = _view_digests(tmp_path)
    assert before_records, "fixture wrote no records; the test would pass vacuously"
    db.close()

    db_path = tmp_path / "memory" / "state" / "shiroe.sqlite"
    assert db_path.exists()
    db_path.unlink()
    for extra in ("-wal", "-shm"):
        Path(str(db_path) + extra).unlink(missing_ok=True)

    rebuilt = StateDB(tmp_path)
    rebuilt.migrate()
    conn2 = rebuilt.connect()
    assert _records(conn2) == [], "a fresh database should start empty"

    EventLog(tmp_path, mirror_conn=conn2).replay_into(conn2)

    assert _records(conn2) == before_records, (
        "canonical records were not reconstructed from the event log"
    )

    views_mod.render_all(tmp_path, conn2)
    assert _view_digests(tmp_path) == before_views, (
        "views regenerated from replayed state differ from the originals"
    )


def test_replay_survives_pre_existing_non_record_payloads(tmp_path: Path) -> None:
    """`memory.written` predates the record schema and older logs prove it.

    The event type was whitelisted while its payload shape never was, so logs
    already exist carrying arbitrary payloads under it. Aborting on the first
    one would make every older log unreplayable, so they are skipped instead --
    and a record written after one must still land.
    """
    from shiroe.storage.events import EventEnvelope

    db = StateDB(tmp_path)
    db.migrate()
    conn = db.connect()
    log = EventLog(tmp_path, mirror_conn=conn)

    log.append(EventEnvelope(event_type="memory.written", actor="legacy",
                             payload={"k": "v"}))
    write_record(conn, log, owner="tests", id_="rec_after", kind="decision",
                 title="Written after a legacy event", claim="Still applied.")
    expected = _records(conn)
    db.close()

    (tmp_path / "memory" / "state" / "shiroe.sqlite").unlink()
    rebuilt = StateDB(tmp_path)
    rebuilt.migrate()
    conn2 = rebuilt.connect()
    replayed = EventLog(tmp_path, mirror_conn=conn2).replay_into(conn2)

    assert replayed == 2, "both events should be replayed, even the skipped one"
    assert _records(conn2) == expected


def test_replayed_log_still_verifies(tmp_path: Path) -> None:
    """Replay must not require trusting the log: the hash chain is checked too."""
    _seed(tmp_path)
    EventLog(tmp_path).verify_chain()


def test_superseding_a_record_replays_to_the_same_end_state(tmp_path: Path) -> None:
    """Replay is ordered: a later supersede must still win after a rebuild."""
    db = StateDB(tmp_path)
    db.migrate()
    conn = db.connect()
    log = EventLog(tmp_path, mirror_conn=conn)

    write_record(conn, log, owner="tests", id_="rec_x", kind="decision",
                 title="Original", claim="First claim.", summary="")
    supersede_record(conn, log, actor="tests", id_="rec_x")
    before = _records(conn)
    assert before[0][5] == "superseded", "fixture did not actually supersede"
    db.close()

    (tmp_path / "memory" / "state" / "shiroe.sqlite").unlink()
    rebuilt = StateDB(tmp_path)
    rebuilt.migrate()
    conn2 = rebuilt.connect()
    EventLog(tmp_path, mirror_conn=conn2).replay_into(conn2)

    assert _records(conn2) == before, "supersede did not survive replay"
