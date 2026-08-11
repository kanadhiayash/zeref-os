"""
privacy-audit: allow-file "State-schema module documents SQL column names + example event payloads as schema; no user data."

Structured local state for Shiroe Memory Core.

Markdown remains the human-auditable project memory. This module owns the
machine-readable local state used for retrieval and explainable recall.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiroe.compat.legacy_identity import LEGACY_V1_STATE_DB_NAME
from shiroe.core.schema import MemoryCard, create_memory_card
from shiroe.lock import MemoryLock, atomic_append, atomic_write
from shiroe.memory import MEMORY_LAYERS, MemoryRoot, STATE_SCHEMA
from shiroe.privacy import scrub


VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_AUTHORITY = {"canonical", "confirmed", "inferred", "unknown"}
VIEW_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("decision", "decisions.md", "Decisions"),
    ("risk", "risks.md", "Risks"),
    ("assumption", "assumptions.md", "Assumptions"),
    ("unknown", "unknowns.md", "Unknowns"),
    ("project-profile", "project-profile.md", "Project Profile"),
    ("operating-profile", "operating-profile.md", "Operating Profile"),
)


@dataclass(frozen=True)
class MemoryItem:
    id: int
    kind: str
    title: str
    body: str
    entity: str
    tags: list[str]
    layer: str
    source_ref: str
    confidence: str
    authority: str
    created_at: str
    updated_at: str
    why_returned: str = ""


@dataclass(frozen=True)
class MemoryEvent:
    ts: str
    event: str
    item_id: int | None
    payload: dict[str, Any]
    hash: str


class MemoryStore:
    """SQLite-backed local state store under memory/state/."""

    def __init__(self, memory_root: MemoryRoot):
        self.memory_root = memory_root
        self.layout = memory_root.layout

    @classmethod
    def from_root(cls, root: Path) -> "MemoryStore":
        return cls(MemoryRoot.from_path(root))

    @classmethod
    def discover(cls, start: Path | None = None) -> "MemoryStore":
        return cls(MemoryRoot.discover(start=start))

    def ensure(self) -> None:
        self.layout.state_dir.mkdir(parents=True, exist_ok=True)
        self.layout.state_schema.write_text(
            json.dumps(STATE_SCHEMA, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if not self.layout.state_events.exists():
            self.layout.state_events.write_text("", encoding="utf-8")

        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    entity TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    layer TEXT NOT NULL DEFAULT 'L1',
                    source_ref TEXT NOT NULL DEFAULT '',
                    confidence TEXT NOT NULL DEFAULT 'medium',
                    authority TEXT NOT NULL DEFAULT 'unknown',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS memory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    event TEXT NOT NULL,
                    item_id INTEGER,
                    payload TEXT NOT NULL,
                    hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_cards (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    evidence_grade TEXT NOT NULL,
                    source_refs TEXT NOT NULL,
                    privacy_class TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    valid_from TEXT,
                    valid_until TEXT,
                    supersedes TEXT NOT NULL DEFAULT '[]',
                    superseded_by TEXT,
                    tags TEXT NOT NULL DEFAULT '[]',
                    owner TEXT NOT NULL DEFAULT 'shiroe'
                );
                """
            )
            _ensure_column(conn, "memory_items", "layer", "TEXT NOT NULL DEFAULT 'L1'")

    def add(
        self,
        *,
        kind: str,
        title: str,
        body: str,
        entity: str = "",
        tags: list[str] | None = None,
        layer: str = "L1",
        source_ref: str = "",
        confidence: str = "medium",
        authority: str = "unknown",
    ) -> MemoryItem:
        self.ensure()
        layer = _validated(layer, set(MEMORY_LAYERS), "layer")
        confidence = _validated(confidence, VALID_CONFIDENCE, "confidence")
        authority = _validated(authority, VALID_AUTHORITY, "authority")
        tags = [t.strip() for t in (tags or []) if t.strip()]
        redact = self.memory_root.root / "REDACT.md"
        title_s = scrub(title, redact, provenance="memory/add/title")[0]
        body_s = scrub(body, redact, provenance="memory/add/body")[0]
        entity_s = scrub(entity, redact, provenance="memory/add/entity")[0]
        source_s = scrub(source_ref, redact, provenance="memory/add/source_ref")[0]
        tags_s = [scrub(tag, redact, provenance="memory/add/tag")[0] for tag in tags]
        now = _utc_now()

        with MemoryLock(self.layout.memory_dir):
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO memory_items(
                        kind, title, body, entity, tags, layer, source_ref,
                        confidence, authority, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        kind,
                        title_s,
                        body_s,
                        entity_s,
                        json.dumps(tags_s),
                        layer,
                        source_s,
                        confidence,
                        authority,
                        now,
                        now,
                    ),
                )
                item_id = int(cur.lastrowid)
                event = self._record_event(
                    conn,
                    event="memory-add",
                    item_id=item_id,
                    payload={"kind": kind, "layer": layer, "title": title_s},
                )
                conn.commit()
                atomic_append(self.layout.state_events, json.dumps(asdict(event), sort_keys=True) + "\n")

        item = self.get(item_id)
        if item is None:
            raise RuntimeError(f"memory item {item_id} was not readable after insert")
        return item

    def add_card(
        self,
        *,
        type: str,
        title: str,
        claim: str,
        privacy_class: str,
        evidence_grade: str,
        source_refs: list[str] | None = None,
        confidence: str = "medium",
        status: str = "active",
        valid_from: str | None = None,
        valid_until: str | None = None,
        supersedes: list[str] | None = None,
        superseded_by: str | None = None,
        tags: list[str] | None = None,
        owner: str = "shiroe",
    ) -> MemoryCard:
        self.ensure()
        redact = self.memory_root.root / "REDACT.md"
        title_s = scrub(title, redact, provenance="memory-card/title")[0]
        claim_s = scrub(claim, redact, provenance="memory-card/claim")[0]
        refs_s = [scrub(ref, redact, provenance="memory-card/source_ref")[0] for ref in (source_refs or [])]
        tags_s = [scrub(tag, redact, provenance="memory-card/tag")[0] for tag in (tags or [])]

        with MemoryLock(self.layout.memory_dir):
            with self._connect() as conn:
                card = create_memory_card(
                    type=type,
                    title=title_s,
                    claim=claim_s,
                    privacy_class=privacy_class,
                    evidence_grade=evidence_grade,
                    source_refs=refs_s,
                    confidence=confidence,
                    status=status,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    supersedes=supersedes or [],
                    superseded_by=superseded_by,
                    tags=tags_s,
                    owner=owner,
                    counter=self._next_card_counter(conn),
                )
                self._insert_card(conn, card)
                event = self._record_event(
                    conn,
                    event="memory-card-add",
                    item_id=None,
                    payload={"id": card.id, "type": card.type, "status": card.status},
                )
                conn.commit()
                atomic_append(self.layout.state_events, json.dumps(asdict(event), sort_keys=True) + "\n")
        return card

    def get_card(self, memory_id: str) -> MemoryCard | None:
        self.ensure()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_cards WHERE id=?", (memory_id,)).fetchone()
        return _card_from_row(row) if row else None

    def list_cards(self, *, type: str = "", status: str = "", limit: int = 200) -> list[MemoryCard]:
        self.ensure()
        params: list[Any] = []
        sql = "SELECT * FROM memory_cards WHERE 1=1"
        if type:
            sql += " AND type=?"
            params.append(type)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [card for row in rows if (card := _card_from_row(row))]

    def archive_card(self, memory_id: str) -> MemoryCard:
        return self._update_card_status(memory_id, status="archived")

    def supersede_card(self, old_id: str, new_id: str) -> tuple[MemoryCard, MemoryCard]:
        self.ensure()
        old = self.get_card(old_id)
        new = self.get_card(new_id)
        if old is None:
            raise KeyError(f"memory card {old_id} not found")
        if new is None:
            raise KeyError(f"memory card {new_id} not found")
        old_data = old.to_dict()
        old_data["status"] = "superseded"
        old_data["superseded_by"] = new_id
        old_data["updated_at"] = _utc_now()
        new_data = new.to_dict()
        new_supersedes = list(dict.fromkeys([*new.supersedes, old_id]))
        new_data["supersedes"] = new_supersedes
        new_data["updated_at"] = _utc_now()
        old_card = MemoryCard.from_dict(old_data)
        new_card = MemoryCard.from_dict(new_data)
        with MemoryLock(self.layout.memory_dir):
            with self._connect() as conn:
                self._replace_card(conn, old_card)
                self._replace_card(conn, new_card)
                event = self._record_event(
                    conn,
                    event="memory-card-supersede",
                    item_id=None,
                    payload={"old_id": old_id, "new_id": new_id},
                )
                conn.commit()
                atomic_append(self.layout.state_events, json.dumps(asdict(event), sort_keys=True) + "\n")
        return old_card, new_card

    def update(
        self,
        item_id: int,
        *,
        kind: str | None = None,
        title: str | None = None,
        body: str | None = None,
        entity: str | None = None,
        tags: list[str] | None = None,
        layer: str | None = None,
        source_ref: str | None = None,
        confidence: str | None = None,
        authority: str | None = None,
    ) -> MemoryItem:
        self.ensure()
        current = self.get(item_id)
        if current is None:
            raise KeyError(f"memory item {item_id} not found")

        redact = self.memory_root.root / "REDACT.md"
        next_values = {
            "kind": kind if kind is not None else current.kind,
            "title": scrub(title, redact, provenance="memory/update/title")[0] if title is not None else current.title,
            "body": scrub(body, redact, provenance="memory/update/body")[0] if body is not None else current.body,
            "entity": scrub(entity, redact, provenance="memory/update/entity")[0] if entity is not None else current.entity,
            "tags": [scrub(tag, redact, provenance="memory/update/tag")[0] for tag in tags] if tags is not None else current.tags,
            "layer": _validated(layer, set(MEMORY_LAYERS), "layer") if layer is not None else current.layer,
            "source_ref": scrub(source_ref, redact, provenance="memory/update/source_ref")[0] if source_ref is not None else current.source_ref,
            "confidence": _validated(confidence, VALID_CONFIDENCE, "confidence") if confidence is not None else current.confidence,
            "authority": _validated(authority, VALID_AUTHORITY, "authority") if authority is not None else current.authority,
            "updated_at": _utc_now(),
        }

        with MemoryLock(self.layout.memory_dir):
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE memory_items
                    SET kind=?, title=?, body=?, entity=?, tags=?, layer=?, source_ref=?,
                        confidence=?, authority=?, updated_at=?
                    WHERE id=? AND archived=0
                    """,
                    (
                        next_values["kind"],
                        next_values["title"],
                        next_values["body"],
                        next_values["entity"],
                        json.dumps(next_values["tags"]),
                        next_values["layer"],
                        next_values["source_ref"],
                        next_values["confidence"],
                        next_values["authority"],
                        next_values["updated_at"],
                        item_id,
                    ),
                )
                event = self._record_event(
                    conn,
                    event="memory-update",
                    item_id=item_id,
                    payload={"changed": _changed_fields(current, next_values)},
                )
                conn.commit()
                atomic_append(self.layout.state_events, json.dumps(asdict(event), sort_keys=True) + "\n")

        updated = self.get(item_id)
        if updated is None:
            raise RuntimeError(f"memory item {item_id} was not readable after update")
        return updated

    def get(self, item_id: int) -> MemoryItem | None:
        self.ensure()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_items WHERE id=? AND archived=0",
                (item_id,),
            ).fetchone()
        return _item_from_row(row) if row else None

    def search(
        self,
        query: str,
        *,
        entity: str = "",
        kind: str = "",
        layer: str = "",
        limit: int = 10,
    ) -> list[MemoryItem]:
        self.ensure()
        params: list[Any] = []
        tokens = _query_tokens(query)

        sql = "SELECT mi.* FROM memory_items mi WHERE mi.archived=0"

        if entity:
            sql += " AND mi.entity LIKE ?"
            params.append(f"%{entity}%")
        if kind:
            sql += " AND mi.kind=?"
            params.append(kind)
        if layer:
            layer = _validated(layer, set(MEMORY_LAYERS), "layer")
            sql += " AND mi.layer=?"
            params.append(layer)

        sql += " ORDER BY mi.updated_at DESC, mi.id DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        scored: list[tuple[int, str, int, MemoryItem]] = []
        for row in rows:
            item = _item_from_row(row)
            if not item:
                continue
            score = _legacy_overlap_score(tokens, item)
            if tokens and score <= 0:
                continue
            scored.append((score, item.updated_at, item.id, _with_reason(item, query=query, entity=entity, kind=kind, layer=layer)))
        scored.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))
        return [entry[3] for entry in scored[:limit]]

    def history(self, item_id: int | None = None, limit: int = 20) -> list[MemoryEvent]:
        self.ensure()
        params: list[Any] = []
        sql = "SELECT ts, event, item_id, payload, hash FROM memory_events"
        if item_id is not None:
            sql += " WHERE item_id=?"
            params.append(item_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            MemoryEvent(
                ts=row["ts"],
                event=row["event"],
                item_id=row["item_id"],
                payload=json.loads(row["payload"]),
                hash=row["hash"],
            )
            for row in rows
        ]

    def record_event(
        self,
        *,
        event: str,
        payload: dict[str, Any],
        item_id: int | None = None,
    ) -> MemoryEvent:
        self.ensure()
        with MemoryLock(self.layout.memory_dir):
            with self._connect() as conn:
                record = self._record_event(conn, event=event, item_id=item_id, payload=payload)
                conn.commit()
                atomic_append(self.layout.state_events, json.dumps(asdict(record), sort_keys=True) + "\n")
        return record

    def explain(self, item_id: int, query: str = "") -> MemoryItem:
        item = self.get(item_id)
        if item is None:
            raise KeyError(f"memory item {item_id} not found")
        return _with_reason(item, query=query, entity="", kind="", layer="")

    def generate_views(self) -> dict[str, str]:
        self.ensure()
        views_dir = self.layout.memory_dir / "views"
        views_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, str] = {}

        with MemoryLock(self.layout.memory_dir):
            for kind, filename, title in VIEW_DEFINITIONS:
                items = self.list_items(kind=kind)
                path = views_dir / filename
                atomic_write(path, _render_view(title=title, kind=kind, items=items))
                written[filename] = str(path)

            with self._connect() as conn:
                event = self._record_event(
                    conn,
                    event="memory-views-generated",
                    item_id=None,
                    payload={"files": sorted(written)},
                )
                conn.commit()
                atomic_append(self.layout.state_events, json.dumps(asdict(event), sort_keys=True) + "\n")

        return written

    def list_items(self, *, kind: str = "", layer: str = "", limit: int = 500) -> list[MemoryItem]:
        self.ensure()
        params: list[Any] = []
        sql = "SELECT * FROM memory_items WHERE archived=0"
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        if layer:
            layer = _validated(layer, set(MEMORY_LAYERS), "layer")
            sql += " AND layer=?"
            params.append(layer)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [item for row in rows if (item := _item_from_row(row))]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.layout.state_db))
        conn.row_factory = sqlite3.Row
        return conn

    def _next_card_counter(self, conn: sqlite3.Connection) -> int:
        today = datetime.now(timezone.utc).strftime("mem_%Y_%m_%d_%")
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM memory_cards WHERE id LIKE ?",
            (today,),
        ).fetchone()
        return int(row["count"]) + 1

    def _insert_card(self, conn: sqlite3.Connection, card: MemoryCard) -> None:
        conn.execute(
            """
            INSERT INTO memory_cards(
                id, type, title, claim, status, confidence, evidence_grade,
                source_refs, privacy_class, created_at, updated_at, valid_from,
                valid_until, supersedes, superseded_by, tags, owner
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _card_params(card),
        )

    def _replace_card(self, conn: sqlite3.Connection, card: MemoryCard) -> None:
        conn.execute(
            """
            REPLACE INTO memory_cards(
                id, type, title, claim, status, confidence, evidence_grade,
                source_refs, privacy_class, created_at, updated_at, valid_from,
                valid_until, supersedes, superseded_by, tags, owner
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _card_params(card),
        )

    def _update_card_status(self, memory_id: str, *, status: str) -> MemoryCard:
        card = self.get_card(memory_id)
        if card is None:
            raise KeyError(f"memory card {memory_id} not found")
        data = card.to_dict()
        data["status"] = status
        data["updated_at"] = _utc_now()
        updated = MemoryCard.from_dict(data)
        with MemoryLock(self.layout.memory_dir):
            with self._connect() as conn:
                self._replace_card(conn, updated)
                event = self._record_event(
                    conn,
                    event=f"memory-card-{status}",
                    item_id=None,
                    payload={"id": updated.id, "status": updated.status},
                )
                conn.commit()
                atomic_append(self.layout.state_events, json.dumps(asdict(event), sort_keys=True) + "\n")
        return updated

    def _record_event(
        self,
        conn: sqlite3.Connection,
        *,
        event: str,
        item_id: int | None,
        payload: dict[str, Any],
    ) -> MemoryEvent:
        ts = _utc_now()
        compact_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = "sha256:" + hashlib.sha256(
            f"{ts}|{event}|{item_id}|{compact_payload}".encode("utf-8")
        ).hexdigest()
        record = MemoryEvent(ts=ts, event=event, item_id=item_id, payload=payload, hash=digest)
        conn.execute(
            "INSERT INTO memory_events(ts, event, item_id, payload, hash) VALUES (?, ?, ?, ?, ?)",
            (record.ts, record.event, record.item_id, compact_payload, record.hash),
        )
        return record


def item_to_dict(item: MemoryItem) -> dict[str, Any]:
    return asdict(item)


def event_to_dict(event: MemoryEvent) -> dict[str, Any]:
    return asdict(event)


def card_to_dict(card: MemoryCard) -> dict[str, Any]:
    return card.to_dict()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validated(value: str, allowed: set[str], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return value


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _query_tokens(query: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", query).lower()
    return tuple(dict.fromkeys(re.findall(r"\w+", normalized, flags=re.UNICODE)))


def _legacy_overlap_score(tokens: tuple[str, ...], item: MemoryItem) -> int:
    if not tokens:
        return 0
    haystack = " ".join([item.title, item.body, item.entity, " ".join(item.tags)])
    item_tokens = set(_query_tokens(haystack))
    return len(set(tokens) & item_tokens)


def _item_from_row(row: sqlite3.Row | None) -> MemoryItem | None:
    if row is None:
        return None
    return MemoryItem(
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        body=row["body"],
        entity=row["entity"],
        tags=json.loads(row["tags"] or "[]"),
        layer=row["layer"],
        source_ref=row["source_ref"],
        confidence=row["confidence"],
        authority=row["authority"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _card_from_row(row: sqlite3.Row | None) -> MemoryCard | None:
    if row is None:
        return None
    return MemoryCard(
        id=row["id"],
        type=row["type"],
        title=row["title"],
        claim=row["claim"],
        status=row["status"],
        confidence=row["confidence"],
        evidence_grade=row["evidence_grade"],
        source_refs=json.loads(row["source_refs"] or "[]"),
        privacy_class=row["privacy_class"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
        supersedes=json.loads(row["supersedes"] or "[]"),
        superseded_by=row["superseded_by"],
        tags=json.loads(row["tags"] or "[]"),
        owner=row["owner"],
    )


def _card_params(card: MemoryCard) -> tuple:
    return (
        card.id,
        card.type,
        card.title,
        card.claim,
        card.status,
        card.confidence,
        card.evidence_grade,
        json.dumps(card.source_refs),
        card.privacy_class,
        card.created_at,
        card.updated_at,
        card.valid_from,
        card.valid_until,
        json.dumps(card.supersedes),
        card.superseded_by,
        json.dumps(card.tags),
        card.owner,
    )


def _with_reason(item: MemoryItem, *, query: str, entity: str, kind: str, layer: str) -> MemoryItem:
    reasons: list[str] = []
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_./:-]+", query)]
    haystack = " ".join([item.title, item.body, item.entity, " ".join(item.tags)]).lower()
    matched = [token for token in tokens if token in haystack]
    if matched:
        reasons.append("matched_terms=" + ",".join(matched[:6]))
    elif query:
        reasons.append("token_overlap_match")
    else:
        reasons.append("latest_items")
    if entity:
        reasons.append(f"entity_filter={entity}")
    if kind:
        reasons.append(f"kind_filter={kind}")
    if layer:
        reasons.append(f"layer_filter={layer}")
    reasons.append(f"layer={item.layer}")
    if item.source_ref:
        reasons.append(f"source_ref={item.source_ref}")
    reasons.append(f"confidence={item.confidence}")
    reasons.append(f"authority={item.authority}")
    return MemoryItem(**{**asdict(item), "why_returned": "; ".join(reasons)})


def _changed_fields(current: MemoryItem, next_values: dict[str, Any]) -> list[str]:
    changed = []
    for field in ("kind", "title", "body", "entity", "tags", "layer", "source_ref", "confidence", "authority"):
        if getattr(current, field) != next_values[field]:
            changed.append(field)
    return changed


def _render_view(*, title: str, kind: str, items: list[MemoryItem]) -> str:
    lines = [
        f"# {title}",
        "",
        f"_Generated from `memory/state/{LEGACY_V1_STATE_DB_NAME}`. Markdown views are generated (never canonical); SQLite is canonical current state per ADR-0001._",
        "",
    ]
    if not items:
        lines.append(f"_(no `{kind}` entries)_")
        lines.append("")
        return "\n".join(lines)

    for item in items:
        lines.extend(
            [
                f"## {item.title}",
                "",
                f"- **ID:** {item.id}",
                f"- **Kind:** {item.kind}",
                f"- **Entity:** {item.entity or '(none)'}",
                f"- **Layer:** {item.layer}",
                f"- **Source:** {item.source_ref or '(none)'}",
                f"- **Confidence:** {item.confidence}",
                f"- **Authority:** {item.authority}",
                f"- **Updated:** {item.updated_at}",
            ]
        )
        if item.tags:
            lines.append(f"- **Tags:** {', '.join(item.tags)}")
        lines.extend(["", item.body, ""])
    return "\n".join(lines)
