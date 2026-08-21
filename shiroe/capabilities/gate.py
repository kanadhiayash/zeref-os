"""``assert_executable`` — the single choke point for capability execution."""

from __future__ import annotations

from pathlib import Path

from shiroe.adapters.capabilities.base import EnforcementLevel
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.lifecycle import is_executable
from shiroe.capabilities.store import CapabilityStore


class CapabilityGateError(RuntimeError):
    """Raised when a capability is not permitted to execute."""


def assert_executable(root: Path | str, capability_id: str) -> None:
    """Raise unless the capability is in an executable lifecycle state AND
    its on-disk source still matches the stored digest.

    Any digest drift snaps the capability back to ``quarantined`` (recorded
    as ``capability.digest_drift``) BEFORE this call raises — so the caller
    sees a consistent state on the next attempt.
    """
    store = CapabilityStore(root)
    try:
        row = store.get(capability_id)
        if row is None:
            raise CapabilityGateError(f"unknown capability {capability_id!r}")
        if not is_executable(row["lifecycle"]):
            raise CapabilityGateError(
                f"capability {capability_id!r} lifecycle is {row['lifecycle']!r}; "
                "execution requires approved / benchmarked / active"
            )
        current_row = _resolve_source(store, capability_id, row["current_digest"])
        state_now = current_row["lifecycle"]
        if not is_executable(state_now):
            raise CapabilityGateError(
                f"capability {capability_id!r} was snapped back to {state_now!r} "
                "by digest drift; re-inspect and re-approve"
            )
        _assert_manifest_adapter_executable(store, capability_id)
    finally:
        store.close()


def _resolve_source(store: CapabilityStore, capability_id: str,
                    expected_digest: str) -> dict:
    """Look up the on-disk location for the capability, recompute its digest,
    and (if different) refresh the store — which will re-quarantine.

    ponytail: source_location is project-relative (REDACT.md scrubs absolute
    paths from event log). Resolve against store.root when relative.
    """
    row = store.conn.execute(
        "SELECT source_location FROM capability_versions "
        "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
        (capability_id,),
    ).fetchone()
    if row is None:
        raise CapabilityGateError(
            f"no version record for capability {capability_id!r}"
        )
    raw = Path(row[0])
    location = raw if raw.is_absolute() else (store.root / raw).resolve()
    if not location.exists():
        raise CapabilityGateError(
            f"capability {capability_id!r} source no longer exists at {location}"
        )
    trust = inspect_source(location)
    if trust.digest != expected_digest:
        store.refresh_digest(capability_id, trust.digest)
    return store.get(capability_id)


def _assert_manifest_adapter_executable(store: CapabilityStore, capability_id: str) -> None:
    from shiroe.adapters.capabilities.registry import AdapterNotFoundError, resolve_adapter

    row = store.conn.execute(
        "SELECT manifest FROM capability_versions "
        "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
        (capability_id,),
    ).fetchone()
    if row is None:
        raise CapabilityGateError(f"no manifest for capability {capability_id!r}")
    import json
    manifest = json.loads(row[0] or "{}")
    adapter_name = manifest.get("entrypoint", {}).get("adapter")
    if not adapter_name:
        raise CapabilityGateError(f"capability {capability_id!r} has no executable adapter")
    try:
        adapter = resolve_adapter(adapter_name)
    except AdapterNotFoundError as exc:
        raise CapabilityGateError(str(exc)) from exc
    health = adapter.health()
    if not health.healthy:
        raise CapabilityGateError(f"adapter {adapter_name!r} is unhealthy: {health.failure_reason}")
    if health.enforcement_level not in {EnforcementLevel.embedded, EnforcementLevel.sidecar}:
        raise CapabilityGateError(f"adapter {adapter_name!r} is not executable")
