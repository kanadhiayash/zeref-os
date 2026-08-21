"""Honest, evidence-backed runtime-update payload (schema shiroe.runtime-update/v1).

Every field is either pulled from a verifiable source in this process (the
installed version, an on-disk adapter's own detect() result, the event log's
own hash-chain walk, the approvals table) or explicitly marked "unknown" /
null. Fields that only a host harness can observe (which skills or agents are
active, which model is answering) are never inferred from files or env vars
here — a shell CLI process cannot see them, so guessing would be dishonest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMA_ID = "shiroe.runtime-update/v1"


def build_runtime_report(root: Path) -> dict[str, Any]:
    root = Path(root)
    chain_ok = _verify_chain(root)

    return {
        "schema": SCHEMA_ID,
        "runtime": {"version": _version(), "hash_chain": "verified" if chain_ok else "unverified"},
        "project": _project_section(root),
        "harness": _harness_section(),
        "run": {"graph_id": None, "run_id": None, "node_id": None, "status": None},
        "capability": {"active_id": None, "lifecycle": None, "digest": None},
        "approvals": _approvals_section(root),
        "verification": {"state": "pass" if chain_ok else "fail"},
        "skills": {"available": "unknown", "active": "unknown"},
        "agents": {"active": "unknown"},
        "model": None,
        "routing": {
            "intended": None,
            "actual": None,
            "provenance": {"model": "unknown", "routing": "unknown"},
        },
        "provenance": {
            "runtime_version": "runtime",
            "harness": "detected" if _any_harness_detected() else "unknown",
            "project_root": "runtime",
            "skills_active": "unknown",
            "agents_active": "unknown",
            "model": "unknown",
        },
    }


def _version() -> str:
    from shiroe import __version__

    return __version__


def _verify_chain(root: Path) -> bool:
    from shiroe.storage import EventLog

    try:
        EventLog(root).verify_chain()
        return True
    except Exception:  # noqa: BLE001 - any failure means we can't vouch for the chain
        return False


def _project_section(root: Path) -> dict[str, Any]:
    return {
        "root": root.name,
        "state_db_present": (root / "memory" / "state" / "shiroe.sqlite").exists(),
    }


def _detected_harness_reports() -> list:
    from shiroe.adapters.harnesses.base import detect_all

    return [report for report in detect_all() if report.detected]


def _any_harness_detected() -> bool:
    return bool(_detected_harness_reports())


def _harness_section() -> dict[str, Any]:
    detected = _detected_harness_reports()
    if not detected:
        return {"detected": "unknown", "version": "unknown", "level": "unknown", "transport": "unknown"}
    report = detected[0]
    return {
        "detected": report.name,
        "version": report.detected_version or "unknown",
        "level": report.enforcement_level.value,
        # ponytail: no adapter carries a verified transport signal today
        # (detect() proves presence, not which channel is live this
        # session) -- report "unknown" rather than guess. Add a real
        # transport field to HarnessReport if/when an adapter can verify it.
        "transport": "unknown",
    }


def _approvals_section(root: Path) -> dict[str, Any]:
    from shiroe.policy.approval_service import ApprovalService
    from shiroe.policy.approvals import ApprovalStatus

    service = ApprovalService(root)
    try:
        rows = service.conn.execute(
            "SELECT id FROM approval_requests WHERE status=? ORDER BY requested_at DESC, id ASC",
            (ApprovalStatus.pending.value,),
        ).fetchall()
    finally:
        service.close()
    ids = [row[0] for row in rows]
    return {"pending_count": len(ids), "pending_ids": ids}
