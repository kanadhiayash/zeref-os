"""
Event-sourced writes to ``memory_records``.

ADR-0001 splits canonical current state (SQLite) from canonical history (JSONL).
Before this module the split was one-directional: ``memory_records`` was written
only by ``storage/importer.py``, and nothing emitted a ``memory.*`` event, so a
replay rebuilt ``memory_events`` and left canonical state empty. The log was a
write-only audit trail and SQLite was the only copy of the truth -- exactly the
single point of failure the split exists to remove.

Every mutation here does both halves in one call: append to the log, then apply
to the table. Ordering matters. The event is appended *first* so that a crash
between the two leaves a durable record that can be replayed forward; the
reverse order would lose the write outright. ``EventLog.append`` fsyncs and
commits its own mirror row, so the event is on disk before the row is touched.

``apply_event`` is the single place that turns an event into table state, and
both the live write path and the replay path go through it. Two code paths that
each interpret events their own way is how a replay silently stops matching the
state it is supposed to reproduce.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from shiroe.storage.events import EventEnvelope, EventLog


SCHEMA_VERSION = 2

# Defaults for fields the writer does not supply. Kept here rather than inline
# in the INSERT so that replay and live writes cannot drift apart.
_RECORD_DEFAULTS: dict[str, object] = {
    "summary": "",
    "status": "active",
    "confidence": "unknown",
    "evidence_grade": "unknown",
    "privacy_class": "internal",
    "authority": 0.0,
    "scope": "project",
    "valid_from": None,
    "valid_until": None,
    "archived": 0,
    "tags_json": "[]",
}

_RECORD_FIELDS = (
    "id", "kind", "title", "claim", "summary", "status", "confidence",
    "evidence_grade", "privacy_class", "authority", "scope", "valid_from",
    "valid_until", "created_at", "updated_at", "owner", "schema_version",
    "archived", "tags_json",
)


# The NOT NULL record columns that carry no default. A payload missing any of
# them is not describing a record, whatever its event type says.
_REQUIRED_PAYLOAD_FIELDS = (
    "id", "kind", "title", "claim", "owner", "created_at", "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_record(
    conn: sqlite3.Connection,
    log: EventLog,
    *,
    id_: str,
    kind: str,
    title: str,
    claim: str,
    owner: str,
    timestamp: str | None = None,
    **fields: object,
) -> dict:
    """Record a memory write in the log, then apply it to current state.

    `timestamp` lets a caller supply the authored time; omitted, the event
    carries wall-clock now. It is written into the payload rather than read back
    off the envelope, so replay produces identical rows without reinterpreting
    envelope metadata as record data.
    """
    sources = fields.pop("sources", None)
    unknown = set(fields) - set(_RECORD_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown record field(s): {sorted(unknown)}")

    stamp = timestamp or _now()
    payload = {
        **_RECORD_DEFAULTS,
        **fields,
        "id": id_,
        "kind": kind,
        "title": title,
        "claim": claim,
        "owner": owner,
        "created_at": stamp,
        "updated_at": stamp,
        "schema_version": SCHEMA_VERSION,
    }
    if sources:
        # Provenance travels with the record. memory_sources carries a foreign
        # key to memory_records, so a replay that rebuilt records without their
        # sources would either orphan them or fail on the constraint.
        payload["sources"] = list(sources)

    env = log.append(EventEnvelope(
        event_type="memory.written",
        actor=owner,
        target=id_,
        payload=payload,
        privacy_class=str(payload["privacy_class"]),
    ))
    apply_event(conn, env)
    conn.commit()
    return env


def supersede_record(
    conn: sqlite3.Connection,
    log: EventLog,
    *,
    id_: str,
    actor: str,
    timestamp: str | None = None,
) -> dict:
    """Mark a record superseded. The row stays; only its status moves."""
    env = log.append(EventEnvelope(
        event_type="memory.superseded",
        actor=actor,
        target=id_,
        payload={"id": id_, "updated_at": timestamp or _now()},
    ))
    apply_event(conn, env)
    conn.commit()
    return env


def archive_record(
    conn: sqlite3.Connection,
    log: EventLog,
    *,
    id_: str,
    actor: str,
    timestamp: str | None = None,
) -> dict:
    """Archive a record. Archived rows are excluded from the generated views."""
    env = log.append(EventEnvelope(
        event_type="memory.archived",
        actor=actor,
        target=id_,
        payload={"id": id_, "updated_at": timestamp or _now()},
    ))
    apply_event(conn, env)
    conn.commit()
    return env


def apply_event(conn: sqlite3.Connection, env: dict) -> bool:
    """
    Fold one event into ``memory_records``. True if it applied.

    The only interpreter of memory events, shared by the live write path and by
    replay. Unrecognised events are not an error: the log also carries
    capability, run, adapter and policy events, none of which describe canonical
    memory state.
    """
    payload = env.get("payload") or {}
    kind = env.get("event_type")

    if kind == "memory.written":
        # `memory.written` predates this module: the type was whitelisted while
        # its payload shape never was, so existing logs carry events with
        # arbitrary payloads under it. A replay must survive those rather than
        # abort on the first one, which would make older logs unreplayable.
        # Recognise only genuinely record-shaped payloads; skip the rest.
        if any(payload.get(name) is None for name in _REQUIRED_PAYLOAD_FIELDS):
            return False
        values = [payload.get(name) for name in _RECORD_FIELDS]
        placeholders = ", ".join("?" * len(_RECORD_FIELDS))
        conn.execute(
            f"INSERT OR REPLACE INTO memory_records ({', '.join(_RECORD_FIELDS)}) "
            f"VALUES ({placeholders})",
            values,
        )
        for source in payload.get("sources") or ():
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_sources
                    (id, memory_id, source_type, source_ref, source_digest,
                     observed_at, retrieved_at, provenance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source["id"], payload["id"], source["source_type"],
                    source["source_ref"], source.get("source_digest"),
                    source.get("observed_at"), source.get("retrieved_at"),
                    source.get("provenance", "unknown"),
                ),
            )
        return True

    if kind in ("memory.superseded", "memory.archived"):
        status = "superseded" if kind == "memory.superseded" else "archived"
        archived = 1 if kind == "memory.archived" else 0
        conn.execute(
            "UPDATE memory_records SET status = ?, archived = ?, updated_at = ? "
            "WHERE id = ?",
            (status, archived, payload.get("updated_at") or env.get("timestamp"),
             payload.get("id") or env.get("target")),
        )
        return True

    return False
