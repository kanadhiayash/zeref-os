"""Append-only JSONL audit logger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiroe.lock import MemoryLock, atomic_append
from shiroe.memory import MemoryRoot


AUDIT_LOGS = {
    "memory_write": "writes.jsonl",
    "memory_read": "reads.jsonl",
    "route_decision": "routes.jsonl",
    "guard_failure": "guard_failures.jsonl",
    "redaction": "redactions.jsonl",
    "release_check": "releases.jsonl",
}


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: str
    status: str
    actor: str
    file: str
    memory_id: str | None
    guards_run: list[str]
    reason: str
    created_at: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLogger:
    def __init__(self, memory_root: MemoryRoot):
        self.memory_root = memory_root
        self.memory_dir = memory_root.root / "memory"
        self.audit_dir = self.memory_dir / "audit"

    @classmethod
    def from_root(cls, root: Path) -> "AuditLogger":
        return cls(MemoryRoot.from_path(root))

    def ensure(self) -> None:
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        for filename in AUDIT_LOGS.values():
            path = self.audit_dir / filename
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def append(
        self,
        *,
        event_type: str,
        status: str,
        reason: str,
        file: str = "",
        memory_id: str | None = None,
        guards_run: list[str] | None = None,
        actor: str = "shiroe",
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        self.ensure()
        created_at = _utc_now()
        event = AuditEvent(
            event_id=_event_id(created_at, event_type, memory_id, reason),
            event_type=event_type,
            status=status,
            actor=actor,
            file=file,
            memory_id=memory_id,
            guards_run=guards_run or [],
            reason=reason,
            created_at=created_at,
            payload=payload or {},
        )
        filename = AUDIT_LOGS.get(event_type, "guard_failures.jsonl")
        with MemoryLock(self.memory_dir):
            atomic_append(self.audit_dir / filename, json.dumps(event.to_dict(), sort_keys=True) + "\n")
        return event


def read_audit_events(root: Path, *, since: str = "") -> tuple[list[AuditEvent], list[str]]:
    logger = AuditLogger.from_root(root)
    logger.ensure()
    events: list[AuditEvent] = []
    corrupt: list[str] = []
    for filename in AUDIT_LOGS.values():
        path = logger.audit_dir / filename
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                event = AuditEvent(**data)
                if since and event.created_at[:10] < since:
                    continue
                events.append(event)
            except Exception:
                corrupt.append(f"{path}:{line_no}")
    events.sort(key=lambda event: event.created_at)
    return events, corrupt


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_id(created_at: str, event_type: str, memory_id: str | None, reason: str) -> str:
    digest = hashlib.sha256(f"{created_at}|{event_type}|{memory_id}|{reason}".encode("utf-8")).hexdigest()
    stamp = created_at[:10].replace("-", "_")
    return f"evt_{stamp}_{digest[:10]}"
