"""Capability-backed independent semantic review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shiroe.adapters.capabilities import resolve_adapter
from shiroe.capabilities.gate import CapabilityGateError, assert_executable
from shiroe.capabilities.store import CapabilityStore
from shiroe.verification.schema import CheckStatus, VerificationCheck, VerificationFinding


_VERDICTS = {"pass", "revise", "block"}


def run_independent_review(
    root: Path | str,
    *,
    node_id: str,
    executor_capability_id: str,
    reviewer_capability_id: str,
    subject: dict[str, Any] | None = None,
    required: bool = True,
) -> VerificationCheck:
    """Run a semantic review through a capability other than the executor.

    The function deliberately returns a verification check only. It does not
    mutate graph state, create approval decisions, or record authority.
    """

    if executor_capability_id == reviewer_capability_id:
        raise ValueError("independent review requires a reviewer capability distinct from the executor")

    root_path = Path(root)
    assert_executable(root_path, reviewer_capability_id)
    adapter = resolve_adapter(_adapter_name(root_path, reviewer_capability_id))
    result = adapter.invoke(
        capability_id=reviewer_capability_id,
        action="independent_review",
        inputs={
            "node_id": node_id,
            "executor_capability_id": executor_capability_id,
            "subject": subject or {},
            "instruction": "Return JSON with verdict, findings, rationale, and evidence_gaps.",
        },
        permissions={"external_write": False, "approval_decision": False},
        timeout_s=30,
    )
    if not result.ok:
        return VerificationCheck(
            name="independent_review",
            status=CheckStatus.block,
            findings=(
                VerificationFinding(
                    code="review_capability_failed",
                    message=result.error or "independent review capability failed",
                    severity=CheckStatus.block,
                    fix="Repair or replace the reviewer capability before accepting this node.",
                ),
            ),
            required=required,
        )

    payload = _parse_payload(result.output)
    verdict = str(payload.get("verdict") or "")
    if verdict not in _VERDICTS:
        raise ValueError(f"unknown independent review verdict: {verdict!r}")

    status = _status_for_verdict(verdict, required=required)
    findings = tuple(_findings(payload, status))
    return VerificationCheck(
        name="independent_review",
        status=status,
        findings=findings,
        required=required,
    )


def _adapter_name(root: Path, capability_id: str) -> str:
    store = CapabilityStore(root)
    try:
        row = store.conn.execute(
            "SELECT manifest FROM capability_versions WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
            (capability_id,),
        ).fetchone()
    finally:
        store.close()
    if row is None:
        raise CapabilityGateError(f"no manifest for capability {capability_id!r}")
    return str(json.loads(row[0])["entrypoint"]["adapter"])


def _parse_payload(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    if isinstance(output, str):
        payload = json.loads(output)
        if isinstance(payload, dict):
            return payload
    raise ValueError("independent review output must be a JSON object")


def _status_for_verdict(verdict: str, *, required: bool) -> CheckStatus:
    if verdict == "pass":
        return CheckStatus.passed
    if verdict == "block":
        return CheckStatus.block
    return CheckStatus.block if required else CheckStatus.warn


def _findings(payload: dict[str, Any], status: CheckStatus) -> list[VerificationFinding]:
    items = payload.get("findings") or ()
    findings: list[VerificationFinding] = []
    if isinstance(items, list):
        for index, item in enumerate(items):
            if isinstance(item, dict):
                message = str(item.get("message") or item.get("finding") or item)
                code = str(item.get("code") or f"review_finding_{index + 1}")
            else:
                message = str(item)
                code = f"review_finding_{index + 1}"
            findings.append(
                VerificationFinding(
                    code=code,
                    message=message,
                    severity=status if status is not CheckStatus.passed else CheckStatus.warn,
                    fix=str(payload.get("rationale") or "Address the review finding before continuing."),
                )
            )
    if not findings and status is not CheckStatus.passed:
        findings.append(
            VerificationFinding(
                code="review_verdict",
                message=str(payload.get("rationale") or f"Independent review returned {status.value}."),
                severity=status,
                fix="Resolve the reviewer concern or request a new human decision.",
                evidence={"evidence_gaps": list(payload.get("evidence_gaps") or ())},
            )
        )
    return findings
