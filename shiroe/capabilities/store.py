"""Persistence for the capability registry — backed by PR 2's SQLite v2."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from shiroe.capabilities.discovery import DiscoveredCapability
from shiroe.capabilities.inspection import TrustReport
from shiroe.capabilities.lifecycle import (
    InvalidTransition,
    can_transition,
    next_state_for_digest_change,
)
from shiroe.capabilities.manifest import infer_manifest, validate_manifest
from shiroe.storage import EventEnvelope, EventLog, StateDB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CapabilityStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.db = StateDB(self.root)
        self.db.migrate()
        self.conn = self.db.connect()
        self.events = EventLog(self.root, mirror_conn=self.conn)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "CapabilityStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    def upsert_capability(self, *, capability_id: str, name: str, type_: str,
                          lifecycle: str, digest: str,
                          manifest: dict, source_kind: str,
                          source_location: str,
                          license_: str | None = None) -> None:
        now = _now()
        cur = self.conn.execute(
            "SELECT current_digest, lifecycle FROM capabilities WHERE id=?",
            (capability_id,),
        ).fetchone()
        if cur is None:
            self.conn.execute(
                """
                INSERT INTO capabilities
                    (id, name, type, lifecycle, current_digest, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (capability_id, name, type_, lifecycle, digest, now, now),
            )
        else:
            self.conn.execute(
                "UPDATE capabilities SET name=?, type=?, lifecycle=?, "
                "current_digest=?, updated_at=? WHERE id=?",
                (name, type_, lifecycle, digest, now, capability_id),
            )
        self.conn.execute(
            """
            INSERT INTO capability_versions
                (id, capability_id, version, digest, manifest, source_kind,
                 source_location, license, adapter, compatibility, lifecycle,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cv_" + uuid.uuid4().hex[:16],
                capability_id, manifest.get("version", "0.0.0-draft"),
                digest, json.dumps(manifest, sort_keys=True),
                source_kind, source_location, license_,
                manifest.get("entrypoint", {}).get("adapter"),
                json.dumps(manifest.get("compatibility", {}), sort_keys=True),
                lifecycle, now,
            ),
        )
        self.conn.commit()

    def get(self, capability_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, name, type, lifecycle, current_digest, updated_at "
            "FROM capabilities WHERE id=?",
            (capability_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(
            ("id", "name", "type", "lifecycle", "current_digest", "updated_at"),
            row,
        ))

    def list(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, type, lifecycle, current_digest FROM capabilities "
            "ORDER BY name"
        ).fetchall()
        return [dict(zip(("id", "name", "type", "lifecycle", "current_digest"), r))
                for r in rows]

    def set_lifecycle(self, capability_id: str, target: str,
                      *, actor: str = "user") -> None:
        row = self.get(capability_id)
        if row is None:
            raise KeyError(capability_id)
        if not can_transition(row["lifecycle"], target):
            raise InvalidTransition(
                f"cannot transition {capability_id}: {row['lifecycle']!r} → {target!r}"
            )
        now = _now()
        self.conn.execute(
            "UPDATE capabilities SET lifecycle=?, updated_at=? WHERE id=?",
            (target, now, capability_id),
        )
        self.conn.commit()
        self.events.append(EventEnvelope(
            event_type=_LIFECYCLE_EVENT_TYPE.get(target, "capability.approved"),
            actor=actor,
            target=f"capability:{capability_id}",
            payload={"from": row["lifecycle"], "to": target},
        ))

    def refresh_digest(self, capability_id: str, new_digest: str) -> str:
        """Re-record the digest for a capability. If it drifted, snap the
        lifecycle back to ``quarantined`` and log ``capability.digest_drift``.
        Returns the resulting lifecycle."""
        row = self.get(capability_id)
        if row is None:
            raise KeyError(capability_id)
        if row["current_digest"] == new_digest:
            return row["lifecycle"]
        now = _now()
        new_state = next_state_for_digest_change(row["lifecycle"])
        self.conn.execute(
            "UPDATE capabilities SET current_digest=?, lifecycle=?, updated_at=? "
            "WHERE id=?",
            (new_digest, new_state, now, capability_id),
        )
        self.conn.commit()
        self.events.append(EventEnvelope(
            event_type="capability.digest_drift",
            actor="capability-manager",
            target=f"capability:{capability_id}",
            payload={
                "previous_digest": row["current_digest"],
                "new_digest": new_digest,
                "previous_state": row["lifecycle"],
                "new_state": new_state,
            },
        ))
        return new_state


# lifecycle target → whitelisted event type (from shiroe.storage.events)
_LIFECYCLE_EVENT_TYPE: dict[str, str] = {
    "discovered": "capability.discovered",
    "quarantined": "capability.quarantined",
    "inspected": "capability.inspected",
    "approved": "capability.approved",
    "benchmarked": "capability.benchmarked",
    "active": "capability.activated",
    "revoked": "capability.revoked",
    # stale / compromised have no whitelist event yet; caller falls back to
    # capability.approved for the mirror insert. Real-world path lands the
    # correct events when PR 8 supervisor wires them.
}


# ---------------------------------------------------------------------------
# Convenience API used by CLI + tests
# ---------------------------------------------------------------------------

def register_discovery(root: Path | str, discovered: DiscoveredCapability,
                       *, trust: TrustReport,
                       adapter: str | None = None) -> str:
    """Insert (or replace) a capability from a discovery + inspection pass.

    New capabilities land in ``quarantined``. If the digest already matched a
    stored version we leave the state untouched; if it drifted the drift
    handler snaps it back to ``quarantined``.
    """
    store = CapabilityStore(root)
    capability_id = _capability_id_for(discovered, adapter or discovered.adapter)
    manifest = infer_manifest(
        discovered.path,
        capability_id=capability_id,
        name=discovered.path.name,
        type_=_kind_to_type(discovered.kind),
    )
    validate_manifest(manifest)
    existing = store.get(capability_id)
    if existing is None:
        store.upsert_capability(
            capability_id=capability_id,
            name=manifest["name"],
            type_=manifest["type"],
            lifecycle="quarantined",
            digest=trust.digest,
            manifest=manifest,
            source_kind=manifest["source"]["kind"],
            source_location=str(discovered.path),
            license_=trust.license,
        )
        store.events.append(EventEnvelope(
            event_type="capability.discovered",
            actor="capability-manager",
            target=f"capability:{capability_id}",
            payload={"path": str(discovered.path), "digest": trust.digest},
        ))
        store.events.append(EventEnvelope(
            event_type="capability.quarantined",
            actor="capability-manager",
            target=f"capability:{capability_id}",
            payload={"reason": "new discovery"},
        ))
    else:
        store.refresh_digest(capability_id, trust.digest)
    store.close()
    return capability_id


def _kind_to_type(kind: str) -> str:
    return {
        "script": "script",
        "cli": "cli",
        "repository_tool": "repository_tool",
        "workflow": "workflow",
        "evaluator": "evaluator",
        "api_service": "api_service",
    }.get(kind, "script")


def _capability_id_for(discovered: DiscoveredCapability, adapter: str) -> str:
    return f"{adapter}:{discovered.path.name}"


def approve(root: Path | str, capability_id: str, *, actor: str = "user") -> None:
    store = CapabilityStore(root)
    row = store.get(capability_id)
    if row is None:
        raise KeyError(capability_id)
    if row["lifecycle"] == "quarantined":
        store.set_lifecycle(capability_id, "inspected", actor=actor)
    row = store.get(capability_id)
    if row["lifecycle"] == "inspected":
        store.set_lifecycle(capability_id, "approved", actor=actor)
    store.close()


def revoke(root: Path | str, capability_id: str, *, actor: str = "user") -> None:
    store = CapabilityStore(root)
    row = store.get(capability_id)
    if row is None:
        raise KeyError(capability_id)
    if not can_transition(row["lifecycle"], "revoked"):
        # allow bounce via quarantined if terminal-blocked
        if can_transition(row["lifecycle"], "quarantined"):
            store.set_lifecycle(capability_id, "quarantined", actor=actor)
    if can_transition(store.get(capability_id)["lifecycle"], "revoked"):
        store.set_lifecycle(capability_id, "revoked", actor=actor)
    store.close()
