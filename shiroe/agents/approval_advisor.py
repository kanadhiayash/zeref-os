"""Non-authorizing approval advice service."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiroe.adapters.capabilities.registry import resolve_adapter
from shiroe.capabilities.gate import CapabilityGateError, assert_executable
from shiroe.capabilities.store import CapabilityStore
from shiroe.memory.service import MemoryService
from shiroe.policy.approval_service import ApprovalService
from shiroe.policy.approvals import ApprovalRequest
from shiroe.storage.state import StateDB


RECOMMENDATIONS = {"approve", "reject", "revise", "defer"}


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
    """Invoke an approved reasoning capability and persist advice only.

    This class intentionally writes no approval decision. The approval request
    remains pending until a human writes authority through the approval service.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.db = StateDB(self.root)
        self.conn = self.db.connect()
        self.db.migrate()

    def advise(self, approval_id: str, capability_id: str) -> ApprovalAdvice:
        assert_executable(self.root, capability_id)
        approval = ApprovalService(self.root).get(approval_id)
        adapter = resolve_adapter(_adapter_name(self.root, capability_id))
        result = adapter.invoke(
            capability_id=capability_id,
            action="approval_advice",
            inputs=_advisor_payload(self.root, approval),
            permissions={"authorize": False, "write_approval_decision": False},
            timeout_s=30,
        )
        if not result.ok:
            raise RuntimeError(result.error or "approval advisor capability failed")
        advice = _parse_advice(approval_id, capability_id, result.output)
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _adapter_name(root: Path, capability_id: str) -> str:
    store = CapabilityStore(root)
    try:
        row = store.conn.execute(
            "SELECT manifest FROM capability_versions "
            "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
            (capability_id,),
        ).fetchone()
        if row is None:
            raise CapabilityGateError(f"no manifest for capability {capability_id!r}")
        manifest = json.loads(row[0] or "{}")
        adapter_name = manifest.get("entrypoint", {}).get("adapter")
        if not adapter_name:
            raise CapabilityGateError(f"capability {capability_id!r} has no executable adapter")
        return str(adapter_name)
    finally:
        store.close()


def _advisor_payload(root: Path, approval: ApprovalRequest) -> dict[str, Any]:
    graph_context = _graph_context(root, approval.graph_id)
    decisions = [
        {
            "id": record.id,
            "title": record.title,
            "claim": record.claim,
            "source_refs": list(record.source_refs),
        }
        for record in MemoryService(root).list(kinds=("decision",), statuses=("active",), limit=10)
    ]
    return {
        "approval": _approval_to_dict(approval),
        "graph_context": graph_context,
        "verification": {"latest": None, "status": "not_run"},
        "memory_decisions": decisions,
        "instruction": "Return JSON with recommendation, rationale, risks, evidence_gaps, conditions",
    }


def _graph_context(root: Path, graph_id: str | None) -> dict[str, Any]:
    if not graph_id:
        return {"graph_id": None, "nodes": []}
    try:
        from shiroe.work.store import WorkStore

        graph = WorkStore(root).get(graph_id)
        return {
            "graph_id": graph.id,
            "objective": graph.objective,
            "nodes": [
                {
                    "id": node.id,
                    "kind": node.kind.value,
                    "objective": node.objective,
                    "requires": list(node.requires),
                }
                for node in graph.nodes
            ],
        }
    except Exception:
        return {"graph_id": graph_id, "nodes": []}


def _approval_to_dict(approval: ApprovalRequest) -> dict[str, Any]:
    return {
        "id": approval.id,
        "approval_type": approval.approval_type.value,
        "requested_action": approval.requested_action,
        "scope": dict(approval.scope),
        "scope_digest": approval.digest,
        "reason": approval.reason,
        "risk": approval.risk,
        "graph_id": approval.graph_id,
        "node_id": approval.node_id,
        "status": approval.status.value,
    }


def _parse_advice(approval_id: str, capability_id: str, output: Any) -> ApprovalAdvice:
    payload = json.loads(output) if isinstance(output, str) else dict(output)
    recommendation = str(payload.get("recommendation") or "")
    if recommendation not in RECOMMENDATIONS:
        raise ValueError(f"unknown approval recommendation: {recommendation!r}")
    rationale = str(payload.get("rationale") or "").strip()
    if not rationale:
        raise ValueError("approval advice requires rationale")
    return ApprovalAdvice(
        id=f"adv_{uuid.uuid4().hex}",
        approval_id=approval_id,
        capability_id=capability_id,
        recommendation=recommendation,
        rationale=rationale,
        risks=tuple(str(item) for item in payload.get("risks") or ()),
        evidence_gaps=tuple(str(item) for item in payload.get("evidence_gaps") or ()),
        conditions=tuple(str(item) for item in payload.get("conditions") or ()),
        created_at=_now(),
    )
