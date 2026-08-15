"""Canonical node registry and lease store."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from shiroe.storage import EventEnvelope, EventLog
from shiroe.storage.state import StateDB


_NODE_ID_RE = re.compile(r"^node_[a-z0-9_]{3,64}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_SSH_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_ROLES = {"controller", "worker"}
_TRANSPORTS = {"tailscale"}
_LEASE_STATES = {"active", "completed", "failed", "released", "expired"}


class NodeValidationError(ValueError):
    """Raised when a node record would create unsafe canonical identity."""


@dataclass(frozen=True)
class NodeRecord:
    id: str
    name: str
    role: str
    transport: str
    transport_host: str
    ssh_user: str
    tailscale_stable_id: str | None
    trusted: bool
    status: str
    capabilities: tuple[str, ...]
    capability_digest: str | None
    last_seen_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LeaseRecord:
    id: str
    graph_id: str
    work_node_id: str
    node_id: str
    state: str
    acquired_at: str
    expires_at: str
    released_at: str | None


class NodeStore:
    def __init__(
        self,
        root: Path | str,
        *,
        id_factory: Callable[[], str] | None = None,
        lease_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = StateDB(root)
        self.conn = self.db.connect()
        self.conn.row_factory = sqlite3.Row
        self.db.migrate()
        self.events = EventLog(self.db.root, mirror_conn=self.conn)
        self._id_factory = id_factory or (lambda: f"node_{uuid.uuid4().hex}")
        self._lease_id_factory = lease_id_factory or (lambda: f"lease_{uuid.uuid4().hex}")
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "NodeStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def register_candidate(
        self,
        *,
        name: str,
        role: str,
        transport_host: str,
        ssh_user: str,
        transport: str = "tailscale",
        tailscale_stable_id: str | None = None,
        capabilities: tuple[str, ...] = (),
        capability_digest: str | None = None,
        status: str = "unknown",
    ) -> NodeRecord:
        node_id = self._new_node_id()
        role = _validate_choice(role, _ROLES, "role")
        transport = _validate_choice(transport, _TRANSPORTS, "transport")
        transport_host = _validate_host(transport_host)
        ssh_user = _validate_ssh_user(ssh_user)
        now = self._now()
        caps = tuple(str(capability) for capability in capabilities)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO nodes(
                    id, name, role, transport, transport_host, ssh_user,
                    tailscale_stable_id, trusted, status, capabilities_json,
                    capability_digest, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    name,
                    role,
                    transport,
                    transport_host,
                    ssh_user,
                    tailscale_stable_id,
                    status,
                    _json(caps),
                    capability_digest,
                    now,
                    now,
                ),
            )
        self._emit(
            "node.registered",
            {
                "node_id": node_id,
                "role": role,
                "transport": transport,
                "transport_host": transport_host,
            },
            target=f"node:{node_id}",
        )
        return self.get_node(node_id)

    def trust_node(self, node_id: str, *, trusted: bool) -> NodeRecord:
        _validate_node_id(node_id)
        with self.conn:
            cur = self.conn.execute(
                "UPDATE nodes SET trusted=?, updated_at=? WHERE id=?",
                (1 if trusted else 0, self._now(), node_id),
            )
        if cur.rowcount != 1:
            raise KeyError(node_id)
        self._emit(
            "node.trust_changed",
            {"node_id": node_id, "trusted": bool(trusted)},
            target=f"node:{node_id}",
        )
        return self.get_node(node_id)

    def get_node(self, node_id: str) -> NodeRecord:
        _validate_node_id(node_id)
        row = self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        if row is None:
            raise KeyError(node_id)
        return _node_from_row(row)

    def list_nodes(self) -> tuple[NodeRecord, ...]:
        rows = self.conn.execute("SELECT * FROM nodes ORDER BY created_at, id").fetchall()
        return tuple(_node_from_row(row) for row in rows)

    def acquire_lease(
        self,
        *,
        graph_id: str,
        work_node_id: str,
        node_id: str,
        ttl_s: int = 300,
    ) -> LeaseRecord:
        node = self.get_node(node_id)
        if node.role != "worker" or not node.trusted:
            raise PermissionError("remote lease requires a trusted worker node")
        self.expire_active_leases()
        now = self._now()
        expires_at = _iso(self._clock() + timedelta(seconds=ttl_s))
        lease_id = self._new_lease_id()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO node_leases(
                        id, graph_id, work_node_id, node_id, state, acquired_at, expires_at
                    ) VALUES (?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (lease_id, graph_id, work_node_id, node_id, now, expires_at),
                )
        except sqlite3.IntegrityError as exc:
            raise RuntimeError(f"active lease already exists for work node {work_node_id}") from exc
        self._emit(
            "node.lease_acquired",
            {
                "lease_id": lease_id,
                "graph_id": graph_id,
                "work_node_id": work_node_id,
                "node_id": node_id,
                "state": "active",
            },
            target=f"node:{node_id}",
        )
        return self.get_lease(lease_id)

    def expire_active_leases(self) -> int:
        now = self._now()
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE node_leases
                SET state='expired', released_at=?
                WHERE state='active' AND expires_at <= ?
                """,
                (now, now),
            )
        return int(cur.rowcount)

    def complete_lease(self, lease_id: str) -> LeaseRecord:
        return self._terminal_lease(lease_id, target_state="completed", idempotent=True)

    def fail_lease(self, lease_id: str) -> LeaseRecord:
        return self._terminal_lease(lease_id, target_state="failed", idempotent=True)

    def release_lease(self, lease_id: str) -> LeaseRecord:
        return self._terminal_lease(lease_id, target_state="released", idempotent=True)

    def get_lease(self, lease_id: str) -> LeaseRecord:
        row = self.conn.execute("SELECT * FROM node_leases WHERE id=?", (lease_id,)).fetchone()
        if row is None:
            raise KeyError(lease_id)
        return _lease_from_row(row)

    def leases_for_work_node(self, work_node_id: str, *, state: str | None = None) -> tuple[LeaseRecord, ...]:
        params: list[str] = [work_node_id]
        sql = "SELECT * FROM node_leases WHERE work_node_id=?"
        if state is not None:
            if state not in _LEASE_STATES:
                raise NodeValidationError(f"unsupported lease state {state!r}")
            sql += " AND state=?"
            params.append(state)
        sql += " ORDER BY acquired_at, id"
        return tuple(_lease_from_row(row) for row in self.conn.execute(sql, params).fetchall())

    def _terminal_lease(self, lease_id: str, *, target_state: str, idempotent: bool) -> LeaseRecord:
        if target_state not in {"completed", "failed", "released"}:
            raise NodeValidationError(f"unsupported terminal lease state {target_state!r}")
        current = self.get_lease(lease_id)
        if current.state == target_state and idempotent:
            return current
        if current.state != "active":
            raise RuntimeError(f"lease {lease_id} is {current.state}, not active")
        with self.conn:
            self.conn.execute(
                "UPDATE node_leases SET state=?, released_at=? WHERE id=?",
                (target_state, self._now(), lease_id),
            )
        updated = self.get_lease(lease_id)
        event_type = "node.lease_completed" if target_state == "completed" else "node.lease_failed"
        self._emit(
            event_type,
            {
                "lease_id": updated.id,
                "graph_id": updated.graph_id,
                "work_node_id": updated.work_node_id,
                "node_id": updated.node_id,
                "state": updated.state,
            },
            target=f"node:{updated.node_id}",
        )
        return updated

    def _emit(self, event_type: str, payload: dict, *, target: str | None = None) -> None:
        self.events.append(
            EventEnvelope(
                event_type=event_type,
                actor="shiroe",
                target=target,
                payload=payload,
            )
        )

    def _new_node_id(self) -> str:
        node_id = self._id_factory()
        return _validate_node_id(node_id)

    def _new_lease_id(self) -> str:
        lease_id = self._lease_id_factory()
        if not re.fullmatch(r"lease_[a-z0-9_]{3,80}", lease_id):
            raise NodeValidationError("lease_id must be Shiroe-generated opaque id")
        return lease_id

    def _now(self) -> str:
        return _iso(self._clock())


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _validate_node_id(node_id: str) -> str:
    if not _NODE_ID_RE.fullmatch(node_id):
        raise NodeValidationError("node_id must be Shiroe-generated opaque id")
    return node_id


def _validate_choice(value: str, allowed: set[str], field: str) -> str:
    if value not in allowed:
        raise NodeValidationError(f"{field} must be one of {sorted(allowed)}")
    return value


def _validate_host(host: str) -> str:
    if not _HOST_RE.fullmatch(host) or ".." in host:
        raise NodeValidationError("transport_host must use conservative hostname syntax")
    return host


def _validate_ssh_user(user: str) -> str:
    if not _SSH_USER_RE.fullmatch(user):
        raise NodeValidationError("ssh_user must use conservative POSIX username syntax")
    return user


def _node_from_row(row: sqlite3.Row | tuple) -> NodeRecord:
    return NodeRecord(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        transport=row["transport"],
        transport_host=row["transport_host"],
        ssh_user=row["ssh_user"],
        tailscale_stable_id=row["tailscale_stable_id"],
        trusted=bool(row["trusted"]),
        status=row["status"],
        capabilities=tuple(json.loads(row["capabilities_json"])),
        capability_digest=row["capability_digest"],
        last_seen_at=row["last_seen_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _lease_from_row(row: sqlite3.Row | tuple) -> LeaseRecord:
    return LeaseRecord(
        id=row["id"],
        graph_id=row["graph_id"],
        work_node_id=row["work_node_id"],
        node_id=row["node_id"],
        state=row["state"],
        acquired_at=row["acquired_at"],
        expires_at=row["expires_at"],
        released_at=row["released_at"],
    )
