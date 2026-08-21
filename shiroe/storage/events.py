"""JSONL v2 event log — canonical append-only history (vNext §6.3, ADR-0001).

Envelope: ``shiroe.event/v2``. Hash-chained per project. Redacted through
:func:`shiroe.privacy.scrub` BEFORE disk write. Schema validated on read
AND write; unknown ``event_type`` is rejected unless the caller declares
its versioned schema.

Layout:
    <root>/memory/events/YYYY/MM/events.jsonl
    <root>/memory/events/head.json   (hash chain head per project)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from shiroe.lock import MemoryLock, atomic_append, atomic_write
from shiroe.privacy import scrub


SCHEMA_ID = "shiroe.event/v2"
_HEAD_FILE = "head.json"

_REQUIRED_FIELDS = (
    "schema",
    "event_id",
    "timestamp",
    "event_type",
    "actor",
    "payload",
    "privacy_class",
    "hash",
    "previous_hash",
)

_ALLOWED_PRIVACY_CLASSES = {"public", "internal", "confidential", "restricted"}

# Whitelist of event types accepted without an explicit schema declaration.
# New types must either be added here or land with an entry in a per-type
# schema module (future). Unknown types get rejected — silent acceptance
# was one of the ways v1 events drifted.
_KNOWN_EVENT_TYPES: set[str] = {
    # memory
    "memory.written", "memory.superseded", "memory.archived", "memory.rejected",
    "contradiction.detected", "contradiction.resolved",
    # capability lifecycle
    "capability.discovered", "capability.quarantined", "capability.inspected",
    "capability.approved", "capability.benchmarked", "capability.activated",
    "capability.deactivated", "capability.revoked", "capability.digest_drift",
    "capability.invoked", "capability.stale", "capability.compromised",
    # approvals
    "approval.requested", "approval.decided", "approval.staled",
    # adapters (PR 5)
    "adapter.probed", "adapter.unhealthy",
    # team runs
    "run.created", "run.compiled", "run.authorized", "run.started",
    "run.paused", "run.resumed", "run.completed", "run.failed", "run.cancelled",
    "step.started", "step.completed", "step.failed", "step.retried",
    # evidence / evaluators
    "evidence.reviewed", "evaluator.ran",
    # policy
    "policy.applied", "policy.denied",
    # nodes / transfer / remote execution
    "node.registered", "node.trust_changed", "node.probed",
    "node.lease_acquired", "node.lease_completed", "node.lease_failed",
    "transfer.started", "transfer.completed", "transfer.rejected",
    "remote.execution_started", "remote.execution_completed",
    "remote.execution_failed",
}


class EventValidationError(ValueError):
    pass


class HashChainError(ValueError):
    pass


@dataclass
class EventEnvelope:
    event_type: str
    actor: str
    payload: dict
    privacy_class: str = "internal"
    run_id: str | None = None
    target: str | None = None
    event_id: str | None = None
    timestamp: str | None = None

    def _prepared(self, previous_hash: str) -> dict:
        env = {
            "schema": SCHEMA_ID,
            "event_id": self.event_id or f"evt_{uuid.uuid4().hex[:16]}",
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event_type": self.event_type,
            "run_id": self.run_id,
            "actor": self.actor,
            "target": self.target,
            "payload": self.payload,
            "privacy_class": self.privacy_class,
            "previous_hash": previous_hash,
        }
        env["hash"] = _hash_envelope(env)
        return env


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_envelope(env: dict) -> str:
    body = {k: v for k, v in env.items() if k != "hash"}
    return "sha256:" + hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def validate_envelope(env: dict, *, strict_type: bool = True) -> None:
    for k in _REQUIRED_FIELDS:
        if k not in env:
            raise EventValidationError(f"missing field {k!r}")
    if env["schema"] != SCHEMA_ID:
        raise EventValidationError(f"expected schema {SCHEMA_ID!r}, got {env['schema']!r}")
    if env["privacy_class"] not in _ALLOWED_PRIVACY_CLASSES:
        raise EventValidationError(f"privacy_class {env['privacy_class']!r} not allowed")
    if not isinstance(env["payload"], dict):
        raise EventValidationError("payload must be an object")
    if strict_type and env["event_type"] not in _KNOWN_EVENT_TYPES:
        raise EventValidationError(
            f"unknown event_type {env['event_type']!r}; "
            "register it in shiroe.storage.events._KNOWN_EVENT_TYPES"
        )


class EventLog:
    """Append-only hash-chained JSONL log with mirror into ``memory_events``."""

    def __init__(self, root: Path | str, *, redact_md: Path | None = None,
                 mirror_conn: sqlite3.Connection | None = None):
        self.root = Path(root)
        self.dir = self.root / "memory" / "events"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._head_path = self.dir / _HEAD_FILE
        self._redact = redact_md or (self.root / "REDACT.md")
        self._mirror = mirror_conn
        self._recovered = False  # one-time head reconciliation, on first head read

    # ------------------------------------------------------------------
    def _current_path(self, ts: str) -> Path:
        # events/YYYY/MM/events.jsonl
        year, month = ts[:4], ts[5:7]
        p = self.dir / year / month / "events.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _validated_tail(self) -> tuple[str, str, set[str]]:
        """Walk the log validating the chain; return (tail_hash, tail_event_id, all_hashes).

        Raises HashChainError on any break or byte-level tamper, so a caller
        that trusts the return value has already failed closed on corruption.
        The tail is the genesis sentinel with an empty event id for an empty log.
        """
        prev = "sha256:0"
        last_event_id = ""
        hashes: set[str] = set()
        for env in self.iter_events():
            validate_envelope(env, strict_type=False)  # historical types accepted
            if env["previous_hash"] != prev:
                raise HashChainError(
                    f"chain break at {env['event_id']}: previous_hash="
                    f"{env['previous_hash']!r}, expected {prev!r}"
                )
            recomputed = _hash_envelope(env)
            if recomputed != env["hash"]:
                raise HashChainError(
                    f"hash mismatch at {env['event_id']}: stored {env['hash']!r}, "
                    f"recomputed {recomputed!r}"
                )
            prev = env["hash"]
            last_event_id = env["event_id"]
            hashes.add(env["hash"])
        return prev, last_event_id, hashes

    def _recover_head(self) -> None:
        """Reconcile head.json with the log tail once per open (fail closed on tamper).

        The log is the single canonical authority: the head is derived from it,
        never trusted blindly. A crash between the event fsync and the head
        replacement leaves head.json pointing at the prior event (or missing);
        rebuilding it to the validated tail is what stops the next append from
        forking off that stale head. Runs once, not per append, so the append
        path stays O(1) over a long log.
        """
        tail, tail_event_id, hashes = self._validated_tail()  # raises on tamper (C)
        if not self._head_path.exists():
            if tail != "sha256:0":
                self._write_head(tail, tail_event_id)  # reconstruct missing head (D)
            return
        stored = json.loads(self._head_path.read_text(encoding="utf-8"))["head"]
        if stored == tail:
            return
        # Head disagrees with the log. Advance to the tail only when the stored
        # head is a real event the log still contains (the head merely lagged the
        # log after a crash); if it names an event absent from the log, the log
        # may have lost a sealed event, so fail closed rather than silently fork.
        if stored == "sha256:0" or stored in hashes:
            self._write_head(tail, tail_event_id)  # advance lagged head (A)
            return
        raise HashChainError(
            f"head marker {stored!r} references an event absent from the log; "
            "refusing to reconstruct (possible truncation)"
        )

    def _load_head(self) -> str:
        if not self._recovered:
            self._recover_head()
            self._recovered = True
        if not self._head_path.exists():
            return "sha256:0"  # sentinel genesis (empty log, never written)
        return json.loads(self._head_path.read_text(encoding="utf-8"))["head"]

    def _write_head(self, head: str, event_id: str) -> None:
        # atomic_write: temp -> fsync -> os.replace -> parent-dir fsync, so a
        # crash mid-write leaves the prior head.json intact rather than a
        # truncated marker. A plain write_text left the head less durable than
        # the fsync'd event it was meant to seal.
        atomic_write(
            self._head_path,
            json.dumps({"head": head, "last_event_id": event_id}, indent=2),
        )

    def _scrub_payload(self, payload: dict) -> dict:
        # scrub each string value; leave structure intact.
        def _walk(x: Any) -> Any:
            if isinstance(x, str):
                cleaned, _ = scrub(x, self._redact, provenance="storage/events")
                return cleaned
            if isinstance(x, dict):
                return {k: _walk(v) for k, v in x.items()}
            if isinstance(x, list):
                return [_walk(v) for v in x]
            return x
        return _walk(payload)

    # ------------------------------------------------------------------
    def append(self, envelope: EventEnvelope) -> dict:
        """Redact, seal, append to JSONL, mirror to SQLite. Returns final envelope."""
        envelope.payload = self._scrub_payload(envelope.payload)
        with MemoryLock(self.root / "memory"):
            head = self._load_head()
            env = envelope._prepared(previous_hash=head)
            validate_envelope(env)
            target = self._current_path(env["timestamp"])
            # fsync'd O_APPEND, same helper the legacy log uses. A plain
            # buffered write left the canonical event log less durable than
            # the v1 store it replaced: a crash could lose events that the
            # caller had already been told were sealed.
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_append(target, _canonical_json(env) + "\n")
            self._write_head(env["hash"], env["event_id"])
            if self._mirror is not None:
                _mirror_row(self._mirror, env)
                # Commit here, not in the caller. The mirror insert rides the
                # caller's connection, and every caller closes that connection
                # without committing -- sqlite3 discards a pending transaction
                # on close, so the final event of each session silently
                # vanished from the SQLite mirror while surviving in the JSONL
                # chain. The two stores disagreed by exactly one row.
                self._mirror.commit()
        return env

    # ------------------------------------------------------------------
    def iter_events(self) -> Iterable[dict]:
        for path in sorted(self.dir.rglob("events.jsonl")):
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)

    def verify_chain(self) -> None:
        """Walk the log; raise if any envelope fails schema or hash chain."""
        prev = "sha256:0"
        seen = False
        for env in self.iter_events():
            validate_envelope(env, strict_type=False)  # historical types accepted
            if env["previous_hash"] != prev:
                raise HashChainError(
                    f"chain break at {env['event_id']}: previous_hash={env['previous_hash']!r}, expected {prev!r}"
                )
            recomputed = _hash_envelope(env)
            if recomputed != env["hash"]:
                raise HashChainError(
                    f"hash mismatch at {env['event_id']}: stored {env['hash']!r}, recomputed {recomputed!r}"
                )
            prev = env["hash"]
            seen = True
        if seen:
            # sanity: head must equal last event's hash
            head_path = self.dir / _HEAD_FILE
            if head_path.exists():
                declared = json.loads(head_path.read_text(encoding="utf-8"))["head"]
                if declared != prev:
                    raise HashChainError(
                        f"head marker {declared!r} does not match last event hash {prev!r}"
                    )

    def replay_into(self, conn: sqlite3.Connection) -> dict:
        """
        Rebuild current state from the JSONL log for every supported domain.

        Rebuilds each domain's rebuildable current/projection tables, not just
        ``memory_events``. Mirroring the events alone left canonical state
        empty after a rebuild, which made the JSONL log a write-only audit
        trail and SQLite the only copy of the truth -- the single point of
        failure that ADR-0001's split exists to remove.

        Events are folded in file order, which is append order, so a later
        supersede lands after the write it supersedes. Interpretation is
        delegated to ``storage.projections.apply_event``, the single
        dispatcher the live write path and replay both go through: a second
        interpreter here is how a replay stops reproducing the state it is
        meant to.

        Returns ``{"replayed": N, "domains": {name: "rebuilt", ...},
        "legacy_incomplete": []}`` rather than a bare count, so a caller can
        tell which domains were actually reconstructed.
        """
        from shiroe.storage import projections

        self.verify_chain()

        # FK-safe delete order: children before parents in every domain.
        # memory_sources holds a foreign key into memory_records, so it has
        # to go before memory_records or the delete fails the constraint.
        # approval_requests also carries (nullable) FKs into work_graphs and
        # work_nodes, so it -- and its own child, approval_advice -- must be
        # cleared before those work tables, not after.
        for table in (
            "memory_events", "memory_sources", "memory_records",
            "approval_advice", "approval_requests",
            "work_attempts", "work_edges", "work_nodes", "work_graphs",
            "capability_permissions", "capability_versions", "capabilities",
        ):
            conn.execute(f"DELETE FROM {table}")

        count = 0
        for env in self.iter_events():
            _mirror_row(conn, env)
            projections.apply_event(conn, env)
            count += 1
        conn.commit()

        return {
            "replayed": count,
            "domains": {domain: "rebuilt" for domain in projections.SUPPORTED_DOMAINS},
            "legacy_incomplete": [],
        }


def _mirror_row(conn: sqlite3.Connection, env: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO memory_events
            (event_id, timestamp, event_type, run_id, actor, target,
             payload, privacy_class, hash, previous_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            env["event_id"], env["timestamp"], env["event_type"],
            env.get("run_id"), env["actor"], env.get("target"),
            _canonical_json(env["payload"]),
            env["privacy_class"], env["hash"], env["previous_hash"],
        ),
    )
