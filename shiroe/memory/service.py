"""Single canonical service for memory records.

All accepted writes go through SQLite current state plus the hash-chained event
log. This module is the Phase 05 boundary that lets old flat atom/wiki writers
be retired without creating a second operational memory path.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Iterable

from shiroe.core.schema import EVIDENCE_GRADES
from shiroe.memory.models import MemoryEvent, MemoryRecord, MemoryRelation, MemoryWrite, SearchResult
from shiroe.storage.events import EventEnvelope, EventLog
from shiroe.storage.records import archive_record, supersede_record, write_record
from shiroe.storage.state import StateDB


class MemoryNotFoundError(KeyError):
    pass


class MemoryService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self._db = StateDB(self.root)
        self._conn = self._db.connect()
        self._db.migrate()
        self._log = EventLog(self.root, mirror_conn=self._conn)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "MemoryService":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def write(self, proposal: MemoryWrite) -> MemoryRecord:
        rejection_reason = _validate_write(proposal) or _verify_write(self.root, proposal)
        if rejection_reason:
            self._log.append(
                EventEnvelope(
                    event_type="memory.rejected",
                    actor=proposal.owner,
                    target=None,
                    payload={
                        "kind": proposal.kind,
                        "title": proposal.title,
                        "reason": rejection_reason,
                    },
                    privacy_class=_rejection_event_privacy_class(proposal.privacy_class),
                )
            )
            raise ValueError(rejection_reason)
        record_id = f"mem_{uuid.uuid4().hex[:16]}"
        sources = [
            {
                "id": f"src_{uuid.uuid4().hex[:16]}",
                "source_type": "user",
                "source_ref": source_ref,
                "provenance": "memory-service",
            }
            for source_ref in proposal.source_refs
        ]
        write_record(
            self._conn,
            self._log,
            id_=record_id,
            kind=proposal.kind,
            title=proposal.title,
            claim=proposal.claim,
            owner=proposal.owner,
            summary=proposal.summary,
            confidence=proposal.confidence,
            evidence_grade=proposal.evidence_grade,
            privacy_class=_event_privacy_class(proposal.privacy_class),
            authority=proposal.authority,
            scope=proposal.scope,
            valid_from=proposal.valid_from,
            valid_until=proposal.valid_until,
            tags_json=json.dumps(list(proposal.tags)),
            sources=sources,
        )
        return self.get(record_id)

    def get(self, record_id: str) -> MemoryRecord:
        row = self._conn.execute(
            """
            SELECT id, kind, title, claim, summary, status, confidence,
                   evidence_grade, privacy_class, authority, scope, valid_from,
                   valid_until, created_at, updated_at, owner, schema_version,
                   archived, tags_json
            FROM memory_records
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError(record_id)
        return self._record_from_row(row)

    def list(
        self,
        *,
        kinds: Iterable[str] | None = None,
        statuses: Iterable[str] = ("active",),
        include_archived: bool = False,
        limit: int | None = None,
    ) -> tuple[MemoryRecord, ...]:
        where: list[str] = []
        params: list[object] = []
        kind_values = tuple(kinds or ())
        status_values = tuple(statuses or ())
        if kind_values:
            where.append(f"kind IN ({','.join('?' for _ in kind_values)})")
            params.extend(kind_values)
        if status_values:
            where.append(f"status IN ({','.join('?' for _ in status_values)})")
            params.extend(status_values)
        if not include_archived:
            where.append("archived = 0")
        sql = (
            "SELECT id, kind, title, claim, summary, status, confidence, "
            "evidence_grade, privacy_class, authority, scope, valid_from, "
            "valid_until, created_at, updated_at, owner, schema_version, archived, tags_json "
            "FROM memory_records"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC, id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return tuple(self._record_from_row(row) for row in self._conn.execute(sql, params))

    def supersede(self, record_id: str, *, actor: str = "shiroe") -> MemoryRecord:
        supersede_record(self._conn, self._log, id_=record_id, actor=actor)
        return self.get(record_id)

    def archive(self, record_id: str, *, actor: str = "shiroe") -> MemoryRecord:
        archive_record(self._conn, self._log, id_=record_id, actor=actor)
        return self.get(record_id)

    def relations(self, record_id: str | None = None) -> tuple[MemoryRelation, ...]:
        params: tuple[str, ...] = ()
        sql = (
            "SELECT id, src_id, dst_id, kind, created_at, note "
            "FROM memory_relations"
        )
        if record_id is not None:
            sql += " WHERE src_id = ? OR dst_id = ?"
            params = (record_id, record_id)
        sql += " ORDER BY created_at ASC, id ASC"
        return tuple(MemoryRelation(*row) for row in self._conn.execute(sql, params))

    def history(self, record_id: str | None = None) -> tuple[MemoryEvent, ...]:
        params: tuple[str, ...] = ()
        sql = (
            "SELECT event_id, timestamp, event_type, actor, target, payload, "
            "privacy_class, hash FROM memory_events"
        )
        if record_id is not None:
            sql += " WHERE target = ?"
            params = (record_id,)
        sql += " ORDER BY timestamp ASC, event_id ASC"
        events = []
        for row in self._conn.execute(sql, params):
            events.append(
                MemoryEvent(
                    event_id=row[0],
                    timestamp=row[1],
                    event_type=row[2],
                    actor=row[3],
                    target=row[4],
                    payload=json.loads(row[5]),
                    privacy_class=row[6],
                    hash=row[7],
                )
            )
        return tuple(events)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        kinds: Iterable[str] | None = None,
        statuses: Iterable[str] = ("active",),
        as_of: str | None = None,
    ) -> SearchResult:
        from shiroe.memory.search import search_memory

        return search_memory(
            self.root,
            query,
            limit=limit,
            kinds=tuple(kinds) if kinds is not None else None,
            statuses=tuple(statuses),
            as_of=as_of,
        )

    def _record_from_row(self, row: sqlite3.Row | tuple[object, ...]) -> MemoryRecord:
        record_id = str(row[0])
        sources = tuple(
            str(src_row[0])
            for src_row in self._conn.execute(
                "SELECT source_ref FROM memory_sources WHERE memory_id = ? ORDER BY id ASC",
                (record_id,),
            )
        )
        return MemoryRecord(
            id=record_id,
            kind=str(row[1]),
            title=str(row[2]),
            claim=str(row[3]),
            summary=str(row[4] or ""),
            status=str(row[5]),
            confidence=str(row[6]),
            evidence_grade=str(row[7]),
            privacy_class=str(row[8]),
            authority=float(row[9]),
            scope=str(row[10]),
            valid_from=row[11],
            valid_until=row[12],
            created_at=str(row[13]),
            updated_at=str(row[14]),
            owner=str(row[15]),
            schema_version=int(row[16]),
            archived=bool(row[17]),
            source_refs=sources,
            tags=tuple(json.loads(row[18] or "[]")),
        )


def _event_privacy_class(value: str) -> str:
    """Map legacy memory privacy labels to event-log labels."""
    return {
        "public-safe": "public",
        "private": "confidential",
        "local-only": "restricted",
        "unknown": "internal",
    }.get(value, value)


def _rejection_event_privacy_class(value: str) -> str:
    """Safe event-log label for a rejection notice.

    A write blocked for a `secret`/`do_not_store` class must still be logged,
    but that class is not a valid event-log label. Fall back to the most
    protective allowed class so recording the refusal never itself fails.
    """
    mapped = _event_privacy_class(value)
    return mapped if mapped in {"public", "internal", "confidential", "restricted"} else "restricted"


def _verify_write(root: Path, proposal: MemoryWrite) -> str | None:
    """Run the canonical VerificationEngine before persistence.

    This is the single write boundary: direct Python callers get the same
    privacy/credential/claim/contradiction gate the CLI wrapper applied.
    The engine reads existing memory via the read path (`MemoryService.list`),
    so it never recurses back into `write`.
    """
    from shiroe.verification import VerificationEngine

    report = VerificationEngine(root).verify_memory_write(proposal)
    if report.status.value != "block":
        return None
    messages = [
        finding.message
        for check in report.checks
        for finding in check.findings
        if finding.severity.value == "block"
    ]
    return "; ".join(messages) or "verification blocked memory write"


def _validate_write(proposal: MemoryWrite) -> str | None:
    if not proposal.source_refs:
        return "source_refs required"
    if not proposal.kind.strip():
        return "kind required"
    if not proposal.title.strip():
        return "title required"
    if not proposal.claim.strip():
        return "claim required"
    if proposal.evidence_grade not in EVIDENCE_GRADES:
        return "evidence_grade must be one of: A, B, C, D, F"
    return None
