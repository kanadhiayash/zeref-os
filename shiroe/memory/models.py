"""Canonical memory service models.

These dataclasses describe the SQLite-backed vNext memory boundary. They are
intentionally small and transport-friendly so CLI, recall, verification, and
handoff can share one shape without reintroducing atom-store records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MemoryWrite:
    kind: str
    title: str
    claim: str
    source_refs: tuple[str, ...]
    summary: str = ""
    confidence: str = "unknown"
    evidence_grade: str = "unknown"
    privacy_class: str = "internal"
    authority: float = 0.0
    scope: str = "project"
    valid_from: str | None = None
    valid_until: str | None = None
    owner: str = "memory-keeper"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    kind: str
    title: str
    claim: str
    summary: str
    status: str
    confidence: str
    evidence_grade: str
    privacy_class: str
    authority: float
    scope: str
    valid_from: str | None
    valid_until: str | None
    created_at: str
    updated_at: str
    owner: str
    schema_version: int
    archived: bool
    source_refs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryRelation:
    id: str
    src_id: str
    dst_id: str
    kind: str
    created_at: str
    note: str | None = None


@dataclass(frozen=True)
class MemoryEvent:
    event_id: str
    timestamp: str
    event_type: str
    actor: str
    target: str | None
    payload: dict[str, Any]
    privacy_class: str
    hash: str


@dataclass(frozen=True)
class SearchHit:
    record: MemoryRecord
    score: int
    why: str


@dataclass(frozen=True)
class SearchResult:
    query: str
    tokens: tuple[str, ...]
    hits: tuple[SearchHit, ...]
    abstained: bool
    source: str = "sqlite"


@dataclass(frozen=True)
class RecallResult:
    query: str
    hits: tuple[SearchHit, ...]
    evidence_refs: tuple[str, ...] = ()
    open_contradictions: tuple[MemoryRecord, ...] = ()

    @property
    def abstained(self) -> bool:
        return not self.hits
