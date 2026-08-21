"""H3.2: canonical replay equivalence over a 10,000-event fixture.

Seeds a deterministic mix of memory writes, supersedes, and archives,
captures the canonical state digest, then wipes the SQLite state and
replays from the JSONL event log using the supported recovery path
(``EventLog.replay_into``). Asserts the rebuilt state matches
event-for-event.

Complements ``tests/test_replay_views.py`` which covers small-scale
view round-trip; this file validates scale and canonical digest.
Marked slow so a fast-loop can skip it; the default suite still runs
it because pytest.ini addopts does not deselect the marker.
"""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from shiroe.storage import EventLog, StateDB
from shiroe.storage.records import archive_record, supersede_record, write_record


TOTAL_WRITES = 8000
TOTAL_SUPERSEDES = 1500
TOTAL_ARCHIVES = 500
TOTAL_EVENTS = TOTAL_WRITES + TOTAL_SUPERSEDES + TOTAL_ARCHIVES  # 10,000


def _open(tmp_path):
    (tmp_path / "REDACT.md").write_text("# minimal\n", encoding="utf-8")
    db = StateDB(tmp_path)
    db.migrate()
    conn = db.connect()
    log = EventLog(tmp_path, redact_md=tmp_path / "REDACT.md", mirror_conn=conn)
    return conn, log


def _seed_ten_thousand_events(tmp_path):
    conn, log = _open(tmp_path)
    ids: list[str] = []

    for i in range(TOTAL_WRITES):
        rid = f"mem_{i:06d}"
        ids.append(rid)
        write_record(
            conn, log,
            id_=rid,
            kind="fact",
            title=f"fact {i}",
            claim=f"claim {i}",
            owner="shiroe-runtime",
            timestamp=f"2026-01-01T00:00:{i % 60:02d}",
        )

    for j, rid in enumerate(ids[: TOTAL_SUPERSEDES * 5 : 5]):
        supersede_record(conn, log, id_=rid, actor="shiroe-runtime",
                         timestamp=f"2026-01-02T00:00:{j % 60:02d}")

    for k, rid in enumerate(ids[-TOTAL_ARCHIVES:]):
        archive_record(conn, log, id_=rid, actor="shiroe-runtime",
                       timestamp=f"2026-01-03T00:00:{k % 60:02d}")

    return conn


def _canonical_state_digest(conn: sqlite3.Connection) -> tuple[str, int, int]:
    """Return (sha256 hex, memory_records count, memory_events count)."""
    records = conn.execute(
        "SELECT id, kind, title, claim, owner, status, archived, updated_at, created_at "
        "FROM memory_records ORDER BY id"
    ).fetchall()
    events_count = conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
    h = hashlib.sha256()
    for row in records:
        h.update(repr(row).encode("utf-8"))
    return h.hexdigest(), len(records), int(events_count)


@pytest.mark.slow
def test_replay_reproduces_canonical_state_over_ten_thousand_events(tmp_path):
    conn = _seed_ten_thousand_events(tmp_path)

    before_digest, before_rec_count, before_evt_count = _canonical_state_digest(conn)
    assert before_rec_count == TOTAL_WRITES
    assert before_evt_count == TOTAL_EVENTS

    log = EventLog(
        tmp_path,
        redact_md=tmp_path / "REDACT.md",
        mirror_conn=conn,
    )
    replayed = log.replay_into(conn)["replayed"]
    assert replayed == TOTAL_EVENTS

    after_digest, after_rec_count, after_evt_count = _canonical_state_digest(conn)
    assert after_digest == before_digest
    assert after_rec_count == before_rec_count
    assert after_evt_count == before_evt_count

    superseded = conn.execute(
        "SELECT COUNT(*) FROM memory_records WHERE status='superseded'"
    ).fetchone()[0]
    archived = conn.execute(
        "SELECT COUNT(*) FROM memory_records WHERE archived=1"
    ).fetchone()[0]
    assert superseded == TOTAL_SUPERSEDES
    assert archived == TOTAL_ARCHIVES


@pytest.mark.slow
def test_hash_chain_verifies_over_ten_thousand_events(tmp_path):
    _seed_ten_thousand_events(tmp_path)
    log = EventLog(
        tmp_path,
        redact_md=tmp_path / "REDACT.md",
        mirror_conn=None,
    )
    log.verify_chain()  # must not raise
