"""Probe a capability's adapter and record the outcome to ``adapter_status``.

``probe`` runs the adapter's ``health()`` method AND (for embedded / sidecar
adapters that support it) an actual dry-run invocation. The result lands in
SQLite v2's ``adapter_status`` table so the resolver (PR 7) and supervisor
(PR 8) can consult it without re-probing.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from shiroe.adapters.capabilities.base import HealthReport
from shiroe.adapters.capabilities.registry import resolve_adapter, AdapterNotFoundError
from shiroe.capabilities.store import CapabilityStore
from shiroe.storage import EventEnvelope, EventLog


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_status(root: Path | str, report: HealthReport) -> None:
    """Insert-or-update an ``adapter_status`` row for this adapter."""
    store = CapabilityStore(root)
    try:
        existing = store.conn.execute(
            "SELECT id FROM adapter_status WHERE adapter=?",
            (report.adapter,),
        ).fetchone()
        supported_features = json.dumps(list(report.supported_features), sort_keys=True)
        if existing is None:
            store.conn.execute(
                """
                INSERT INTO adapter_status
                    (id, adapter, detected_version, enforcement_level,
                     supported_features, last_health_check, failure_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "as_" + uuid.uuid4().hex[:16],
                    report.adapter, report.detected_version,
                    report.enforcement_level.value, supported_features,
                    _now(), None if report.healthy else report.failure_reason,
                ),
            )
        else:
            store.conn.execute(
                """
                UPDATE adapter_status
                   SET detected_version=?, enforcement_level=?,
                       supported_features=?, last_health_check=?,
                       failure_reason=?
                 WHERE adapter=?
                """,
                (
                    report.detected_version, report.enforcement_level.value,
                    supported_features, _now(),
                    None if report.healthy else report.failure_reason,
                    report.adapter,
                ),
            )
        store.conn.commit()
        # audit event through the hash-chained log
        log = EventLog(store.root, mirror_conn=store.conn)
        log.append(EventEnvelope(
            event_type="adapter.probed" if report.healthy else "adapter.unhealthy",
            actor="capability-manager",
            target=f"adapter:{report.adapter}",
            payload={
                "detected_version": report.detected_version,
                "enforcement_level": report.enforcement_level.value,
                "supported_features": list(report.supported_features),
                "healthy": report.healthy,
                "failure_reason": report.failure_reason,
            },
        ))
    finally:
        store.close()


def probe(root: Path | str, capability_id: str) -> HealthReport:
    """Look up the capability's declared adapter and probe it.

    Never substitutes silently — if the declared adapter is unknown we
    return an unhealthy report naming that fact, and the row is written.
    """
    store = CapabilityStore(root)
    try:
        row = store.conn.execute(
            "SELECT manifest FROM capability_versions "
            "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
            (capability_id,),
        ).fetchone()
    finally:
        store.close()
    if row is None:
        report = HealthReport(
            adapter="unknown",
            detected_version=None,
            enforcement_level=_unavailable_level(),
            healthy=False,
            failure_reason=f"no version record for {capability_id!r}",
        )
        record_status(root, report)
        return report

    manifest = json.loads(row[0]) if row[0] else {}
    adapter_name = manifest.get("entrypoint", {}).get("adapter") or ""
    try:
        adapter = resolve_adapter(adapter_name)
    except AdapterNotFoundError as e:
        report = HealthReport(
            adapter=adapter_name,
            detected_version=None,
            enforcement_level=_unavailable_level(),
            healthy=False,
            failure_reason=str(e),
        )
        record_status(root, report)
        return report

    report = adapter.health()
    record_status(root, report)
    return report


def _unavailable_level():
    # Deferred import so the enum doesn't pull adapter modules at module load.
    from shiroe.adapters.capabilities.base import EnforcementLevel
    return EnforcementLevel.sidecar
