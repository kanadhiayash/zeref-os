"""Persistence for the capability registry — backed by PR 2's SQLite v2."""

from __future__ import annotations

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
from shiroe.storage import EventEnvelope, EventLog, StateDB, projections


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
    def _relativize(self, location: str) -> str:
        try:
            p = Path(location)
            if p.is_absolute():
                return str(p.relative_to(self.root))
        except (ValueError, OSError):
            pass
        return location

    def _relativize_manifest(self, manifest: dict) -> dict:
        m = dict(manifest)
        src = m.get("source")
        if isinstance(src, dict) and "location" in src:
            src = dict(src)
            src["location"] = self._relativize(src["location"])
            m["source"] = src
        ep = m.get("entrypoint")
        if isinstance(ep, dict):
            ep = dict(ep)
            cmd = ep.get("command")
            if isinstance(cmd, list) and cmd:
                ep["command"] = [self._relativize(cmd[0])] + list(cmd[1:])
            m["entrypoint"] = ep
        return m

    # ------------------------------------------------------------------
    def upsert_capability(self, *, capability_id: str, name: str, type_: str,
                          lifecycle: str, digest: str,
                          manifest: dict, source_kind: str,
                          source_location: str,
                          license_: str | None = None,
                          permissions: dict | None = None,
                          actor: str = "capability-manager") -> None:
        """Event-first capability write: append ``capability.discovered``
        with the full-snapshot payload, then fold it via the shared
        projection dispatcher. No direct table INSERT/UPDATE here -- the
        reducer (``storage.projections._apply_capability``) is the only
        interpreter, so replay reproduces exactly this state.

        ponytail: normalizes absolute paths under ``self.root`` to relative
        so REDACT.md's internal_paths class does not scrub operational
        location data out of the event log. Gate/adapter resolve relative
        paths against the project root at read time.
        """
        source_location = self._relativize(source_location)
        manifest = self._relativize_manifest(manifest)
        now = _now()
        payload = {
            "id": capability_id,
            "name": name,
            "type": type_,
            "lifecycle": lifecycle,
            "digest": digest,
            "version_id": "cv_" + uuid.uuid4().hex[:16],
            "version": manifest.get("version", "0.0.0-draft"),
            "manifest": manifest,
            "source_kind": source_kind,
            "source_location": source_location,
            "license": license_,
            "adapter": manifest.get("entrypoint", {}).get("adapter"),
            "compatibility": manifest.get("compatibility") or None,
            "permissions": permissions,
            "event_time": now,
        }
        env = self.events.append(EventEnvelope(
            event_type="capability.discovered",
            actor=actor,
            target=f"capability:{capability_id}",
            payload=payload,
        ))
        # ponytail: source_location + manifest paths MUST be project-relative
        # here; absolute paths get REDACTed by EventLog.append (internal_paths
        # class) and would corrupt state. Onboarding normalizes before call;
        # gate/adapter resolve against project root at read time.
        projections.apply_event(self.conn, env)
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
        """Event-first lifecycle transition: append the whitelisted event for
        ``target`` before touching current state, then apply it. The shared
        reducer (``projections._apply_capability``) does not yet interpret
        anything but ``capability.discovered`` (Steps 4-5 land the rest), so
        the direct ``UPDATE`` here is the state mutation until then; calling
        ``projections.apply_event`` too keeps this call site unchanged once
        those reducers exist."""
        row = self.get(capability_id)
        if row is None:
            raise KeyError(capability_id)
        if not can_transition(row["lifecycle"], target):
            raise InvalidTransition(
                f"cannot transition {capability_id}: {row['lifecycle']!r} → {target!r}"
            )
        event_type = _LIFECYCLE_EVENT_TYPE[target]
        env = self.events.append(EventEnvelope(
            event_type=event_type,
            actor=actor,
            target=f"capability:{capability_id}",
            payload={"from": row["lifecycle"], "to": target},
        ))
        now = _now()
        self.conn.execute(
            "UPDATE capabilities SET lifecycle=?, updated_at=? WHERE id=?",
            (target, now, capability_id),
        )
        projections.apply_event(self.conn, env)
        self.conn.commit()

    def refresh_digest(self, capability_id: str, new_digest: str) -> str:
        """Re-record the digest for a capability. If it drifted, snap the
        lifecycle back to ``quarantined`` and log ``capability.digest_drift``.
        Returns the resulting lifecycle."""
        row = self.get(capability_id)
        if row is None:
            raise KeyError(capability_id)
        if row["current_digest"] == new_digest:
            return row["lifecycle"]
        new_state = next_state_for_digest_change(row["lifecycle"])
        env = self.events.append(EventEnvelope(
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
        now = _now()
        self.conn.execute(
            "UPDATE capabilities SET current_digest=?, lifecycle=?, updated_at=? "
            "WHERE id=?",
            (new_digest, new_state, now, capability_id),
        )
        projections.apply_event(self.conn, env)
        self.conn.commit()
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
    "stale": "capability.stale",
    "compromised": "capability.compromised",
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
    # ponytail: rewrite absolute paths to project-relative post-inference so
    # REDACT.md's internal_paths class does not scrub them out of the event.
    try:
        rel = discovered.path.relative_to(store.root)
        rel_source = str(rel)
        manifest["source"]["location"] = rel_source
        cmd = manifest.get("entrypoint", {}).get("command") or []
        if cmd and Path(cmd[0]).is_absolute():
            try:
                cmd[0] = str(Path(cmd[0]).relative_to(store.root))
                manifest["entrypoint"]["command"] = cmd
            except ValueError:
                pass
    except ValueError:
        rel_source = str(discovered.path)
    validate_manifest(manifest)
    existing = store.get(capability_id)
    if existing is None:
        # upsert_capability already emits the full-snapshot
        # capability.discovered event (event-first); quarantined is the
        # separate lifecycle-entry event that follows a new discovery.
        store.upsert_capability(
            capability_id=capability_id,
            name=manifest["name"],
            type_=manifest["type"],
            lifecycle="quarantined",
            digest=trust.digest,
            manifest=manifest,
            source_kind=manifest["source"]["kind"],
            source_location=rel_source,
            license_=trust.license,
        )
        env = store.events.append(EventEnvelope(
            event_type="capability.quarantined",
            actor="capability-manager",
            target=f"capability:{capability_id}",
            payload={"reason": "new discovery"},
        ))
        projections.apply_event(store.conn, env)
        store.conn.commit()
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
