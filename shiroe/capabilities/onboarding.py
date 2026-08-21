"""Composite capability onboarding flow (Step 3).

Chains inspection -> manifest inference -> registration -> inspected
lifecycle -> a human approval request. Single CLI call walks a
capability from "found on disk" to "waiting on a human decision"
without executing it or auto-approving it.

All persisted paths are project-relative. EventLog.append scrubs
absolute filesystem paths (REDACT.md internal_paths class); gate
and adapters resolve relative paths against the project root at read.
"""

from __future__ import annotations

import re
from pathlib import Path

from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.manifest import infer_manifest, validate_manifest
from shiroe.capabilities.store import CapabilityStore
from shiroe.storage.events import EventEnvelope
from shiroe.storage import projections
from shiroe.policy.approval_service import ApprovalService


class OnboardingError(ValueError):
    """Raised when a capability source cannot be onboarded."""


_ID_SAFE = re.compile(r"[^a-z0-9]+")


def _derive_capability_id(rel_path: Path) -> str:
    stem = rel_path.stem or rel_path.name
    slug = _ID_SAFE.sub("_", stem.lower()).strip("_") or "capability"
    return f"local.{slug}"


def onboard(project_root: Path, source: Path) -> dict:
    """Onboard one capability source into the registry, pending approval."""
    project_root = Path(project_root).resolve()
    source = Path(source).resolve()
    if not source.exists():
        raise OnboardingError(f"capability source does not exist: {source}")
    try:
        rel = source.relative_to(project_root)
    except ValueError as exc:
        raise OnboardingError(
            f"capability source {source} is outside project root {project_root}"
        ) from exc

    trust = inspect_source(source)
    capability_id = _derive_capability_id(rel)

    # Manifest carries the RELATIVE path so REDACT does not scrub it.
    manifest = infer_manifest(
        rel,
        capability_id=capability_id,
        name=rel.name,
        type_="script" if source.is_file() else "capability",
    )
    validate_manifest(manifest)

    store = CapabilityStore(project_root)
    try:
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
                source_location=str(rel),
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

        store.set_lifecycle(capability_id, "inspected", actor="onboarding")
        row = store.get(capability_id)
    finally:
        store.close()

    approvals = ApprovalService(project_root)
    try:
        approval = approvals.request(
            approval_type="capability",
            requested_action=f"approve {capability_id}",
            scope={"capability_id": capability_id, "digest": row["current_digest"]},
            reason="onboarding",
            risk="medium",
            action_kind="capability.approve",
        )
    finally:
        approvals.close()

    return {
        "capability_id": capability_id,
        "lifecycle": row["lifecycle"],
        "digest": row["current_digest"],
        "approval_id": approval.id,
        "trust_report": trust.to_dict(),
    }
