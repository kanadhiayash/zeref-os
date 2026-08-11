from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiroe.adapters.capabilities import AdapterResult, EnforcementLevel, HealthReport, register_adapter
from shiroe.capabilities.gate import CapabilityGateError
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy.approval_service import ApprovalService
from shiroe.policy.approvals import ApprovalStatus
from shiroe.work.schema import WorkGraph
from shiroe.work.store import WorkStore


class EmbeddedReasoner:
    name = "test-reasoner"
    enforcement_level = EnforcementLevel.embedded
    supported_types = ("api_service",)

    def health(self) -> HealthReport:
        return HealthReport(
            adapter=self.name,
            detected_version="test",
            enforcement_level=self.enforcement_level,
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id: str, action: str, inputs: dict, permissions=None, timeout_s=None) -> AdapterResult:
        return AdapterResult(
            ok=True,
            output=json.dumps(
                {
                    "recommendation": "revise",
                    "rationale": "Request needs a narrower release path.",
                    "risks": ["scope is high risk"],
                    "evidence_gaps": ["missing rollout proof"],
                    "conditions": ["human confirms final path"],
                }
            ),
        )


def _seed_pending_approval(root):
    WorkStore(root).create(WorkGraph(id="g1", objective="approval fixture", nodes=()))
    return ApprovalService(root).request(
        approval_type="strategic",
        requested_action="choose release path",
        scope={"graph": "g1", "node": "approve-release"},
        reason="strategic boundary",
        risk="high",
        graph_id="g1",
        node_id=None,
    )


def _register_executable_reasoning_capability(root: Path, capability_id: str = "test.reasoner") -> str:
    source = root / "reasoner.txt"
    source.write_text("local executable reasoner fixture\n", encoding="utf-8")
    digest = inspect_source(source).digest
    register_adapter("test-reasoner", EmbeddedReasoner())
    CapabilityStore(root).upsert_capability(
        capability_id=capability_id,
        name="Test Reasoner",
        type_="api_service",
        lifecycle="active",
        digest=digest,
        manifest={
            "schema": "shiroe.capability/v1",
            "id": capability_id,
            "name": "Test Reasoner",
            "type": "api_service",
            "version": "1.0.0",
            "source": {"kind": "file", "location": str(source)},
            "entrypoint": {"adapter": "test-reasoner", "url": "local://reasoner"},
            "requires": {},
        },
        source_kind="file",
        source_location=str(source),
    )
    return capability_id


def test_advisor_writes_advice_not_authorization(tmp_path):
    from shiroe.agents.approval_advisor import ApprovalAdvisor

    approval = _seed_pending_approval(tmp_path)
    capability_id = _register_executable_reasoning_capability(tmp_path)

    advice = ApprovalAdvisor(tmp_path).advise(approval.id, capability_id)

    assert advice.recommendation in {"approve", "reject", "revise", "defer"}
    assert ApprovalService(tmp_path).get(approval.id).status == ApprovalStatus.pending


def test_advisor_rejects_non_executable_reasoning_capability(tmp_path):
    from shiroe.agents.approval_advisor import ApprovalAdvisor

    approval = _seed_pending_approval(tmp_path)
    with pytest.raises(CapabilityGateError):
        ApprovalAdvisor(tmp_path).advise(approval.id, "context_only")
