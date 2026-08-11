"""Non-authorizing approval advisor."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiroe.adapters.capabilities import resolve_adapter
from shiroe.capabilities.gate import assert_executable
from shiroe.capabilities.store import CapabilityStore
from shiroe.memory.service import MemoryService
from shiroe.policy.approval_service import ApprovalService
from shiroe.storage.state import StateDB


_RECOMMENDATIONS = {"approve", "reject", "revise", "defer"}


@dataclass(frozen=True)
class ApprovalAdvice:
    id: str
    approval_id: str
    capability_id: str
    recommendation: str
    rationale: str
    risks: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    conditions: tuple[str, ...]
    created_at: str


class ApprovalAdvisor:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.db = StateDB(self.root)
        self.conn = self.db.connect()
        self.db.migrate()

    def advise(self, request_id: str, capability_id: str) -> ApprovalAdvice:
        assert_executable(self.root, capability_id)
        approval = ApprovalService(self.root).get(request_id)
        adapter_name = self._adapter_name(capability_id)
        adapter = resolve_adapter(adapter_name)
        result = adapter.invoke(
            capability_id=capability_id,
            action="approval_advice",
            inputs=self._request_payload(approval),
            permissions={"external_write": False, "approval_decision": False},
            timeout_s=30,
        )
        if not result.ok:
            raise RuntimeError(result.error or "approval advisor capability failed")
        payload = _parse_payload(result.output)
        advice = ApprovalAdvice(
            id=f"adv_{uuid.uuid4().hex}",
            approval_id=request_id,
            capability_id=capability_id,
            recommendation=_recommendation(payload),
            rationale=str(payload.get("rationale") or ""),
            risks=tuple(str(item) for item in payload.get("risks") or ()),
            evidence_gaps=tuple(str(item) for item in payload.get("evidence_gaps") or ()),
            conditions=tuple(str(item) for item in payload.get("conditions") or ()),
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO approval_advice(
                    id, approval_id, capability_id, recommendation, rationale,
                    risks_json, evidence_gaps_json, conditions_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    advice.id,
                    advice.approval_id,
                    advice.capability_id,
                    advice.recommendation,
                    advice.rationale,
                    json.dumps(list(advice.risks), sort_keys=True),
                    json.dumps(list(advice.evidence_gaps), sort_keys=True),
                    json.dumps(list(advice.conditions), sort_keys=True),
                    advice.created_at,
                ),
            )
        return advice

    def _adapter_name(self, capability_id: str) -> str:
        row = CapabilityStore(self.root).conn.execute(
            "SELECT manifest FROM capability_versions WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
            (capability_id,),
        ).fetchone()
        if row is None:
            raise KeyError(capability_id)
        manifest = json.loads(row[0])
        return str(manifest["entrypoint"]["adapter"])

    def _request_payload(self, approval) -> dict[str, Any]:
        decisions = [
            {
                "id": record.id,
                "title": record.title,
                "claim": record.claim,
                "evidence_grade": record.evidence_grade,
            }
            for record in MemoryService(self.root).list(kinds=("decision",), statuses=("active",), limit=10)
        ]
        return {
            "approval": {
                "id": approval.id,
                "type": approval.approval_type.value,
                "requested_action": approval.requested_action,
                "scope": dict(approval.scope),
                "reason": approval.reason,
                "risk": approval.risk,
                "status": approval.status.value,
            },
            "graph_context": {"graph_id": approval.graph_id, "node_id": approval.node_id},
            "verification": {"latest": None},
            "memory_decisions": decisions,
            "instruction": "Return JSON with recommendation, rationale, risks, evidence_gaps, conditions",
        }


def _parse_payload(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    if isinstance(output, str):
        return json.loads(output)
    raise ValueError("advisor output must be a JSON object")


def _recommendation(payload: dict[str, Any]) -> str:
    value = str(payload.get("recommendation") or "")
    if value not in _RECOMMENDATIONS:
        raise ValueError(f"unknown advisor recommendation: {value!r}")
    return value
