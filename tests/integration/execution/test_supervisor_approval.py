"""H0.2: supervisor pause/resume roundtrip for the require_approval verdict.

The vNext policy engine returns ``require_approval`` for any capability
invocation the autonomy stack cannot self-authorise. Before H0.2 the
supervisor blocked the node and paused the graph but never linked the
pause to an ``ApprovalRequest``, so ``resume()`` re-authorised, created a
brand-new pending request, and paused again forever -- an approved
decision never unblocked the graph. These tests pin the fixed contract:

1. Every ``require_approval`` pause is backed by exactly one approval
   request (idempotent on resume).
2. Once a human approves that request, resume advances the node.
3. Once a human rejects it, resume fails the node/graph -- no infinite
   pause.
4. ``deferred`` / ``revise`` re-pause without duplicating rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shiroe.adapters.capabilities.base import AdapterResult, EnforcementLevel, HealthReport
from shiroe.adapters.capabilities.registry import register_adapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.execution.supervisor import ExecutionSupervisor
from shiroe.policy.approval_service import ApprovalService
from shiroe.policy.schema import Decision, Verdict
from shiroe.storage.state import StateDB
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


class _EchoAdapter:
    name = "test-echo-approval"
    enforcement_level = EnforcementLevel.embedded
    supported_types = ("test_echo",)

    def health(self):
        return HealthReport(
            adapter=self.name,
            detected_version="1",
            enforcement_level=self.enforcement_level,
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        return AdapterResult(
            ok=True,
            output={"message": inputs.get("message", "ok")},
            usage={"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
        )


def _register_capability(root: Path, capability_id: str) -> None:
    adapter = _EchoAdapter()
    register_adapter(adapter.name, adapter)
    src = root / "capabilities" / capability_id.replace(".", "_") / "run.sh"
    src.parent.mkdir(parents=True)
    src.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    trust = inspect_source(src)
    manifest = {
        "schema": "shiroe.capability/v1",
        "id": capability_id,
        "name": capability_id,
        "type": "script",
        "version": "1",
        "source": {"kind": "local-file", "location": str(src)},
        "entrypoint": {"adapter": adapter.name, "command": [str(src)]},
        "requires": {},
    }
    store = CapabilityStore(root)
    try:
        store.upsert_capability(
            capability_id=capability_id,
            name=capability_id,
            type_="script",
            lifecycle="active",
            digest=trust.digest,
            manifest=manifest,
            source_kind="local-file",
            source_location=str(src),
        )
    finally:
        store.close()


def _seed_single_task_graph(root: Path, capability_id: str) -> str:
    graph = compile_work_graph(
        {
            "id": "g-approval-flow",
            "objective": "invoke a capability under require_approval",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "task",
                    "objective": "guarded",
                    "requires": [capability_id],
                },
            ],
            "edges": [],
        }
    )
    WorkStore(root).create(graph)
    return graph.id


def _approval_request_count(root: Path) -> int:
    db = StateDB(root)
    conn = db.connect()
    db.migrate()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM approval_requests").fetchone()[0])
    finally:
        db.close()


def _only_pending(root: Path):
    db = StateDB(root)
    conn = db.connect()
    db.migrate()
    try:
        rows = conn.execute("SELECT id, status FROM approval_requests").fetchall()
    finally:
        db.close()
    assert len(rows) == 1, f"expected exactly one approval request, got {rows!r}"
    return rows[0][0], rows[0][1]


@pytest.fixture
def force_require_approval(monkeypatch):
    """Force the policy engine to return require_approval for any action."""

    def stub_evaluate(action, stack, *, mode):
        return Decision(
            verdict=Verdict.require_approval,
            reason="test forces require_approval",
            deciding_layer="test-stub",
        )

    monkeypatch.setattr("shiroe.policy.service.evaluate", stub_evaluate)


def test_supervisor_pauses_and_creates_single_approval_request(
    tmp_path, force_require_approval
):
    capability_id = "test.echo.approval"
    _register_capability(tmp_path, capability_id)
    graph_id = _seed_single_task_graph(tmp_path, capability_id)

    summary = ExecutionSupervisor(tmp_path).run(graph_id)

    assert summary.status == "paused"
    assert summary.blocked == ("n1",)
    assert _approval_request_count(tmp_path) == 1
    approval_id, status = _only_pending(tmp_path)
    assert status == "pending"
    assert approval_id in (summary.reason or "")


def test_supervisor_resume_reuses_same_approval_when_still_pending(
    tmp_path, force_require_approval
):
    capability_id = "test.echo.approval"
    _register_capability(tmp_path, capability_id)
    graph_id = _seed_single_task_graph(tmp_path, capability_id)

    ExecutionSupervisor(tmp_path).run(graph_id)
    first_id, _ = _only_pending(tmp_path)

    summary = ExecutionSupervisor(tmp_path).resume(graph_id)
    assert summary.status == "paused"
    assert _approval_request_count(tmp_path) == 1
    second_id, second_status = _only_pending(tmp_path)
    assert second_id == first_id
    assert second_status == "pending"


def test_supervisor_resume_completes_after_human_approves(
    tmp_path, force_require_approval
):
    capability_id = "test.echo.approval"
    _register_capability(tmp_path, capability_id)
    graph_id = _seed_single_task_graph(tmp_path, capability_id)

    ExecutionSupervisor(tmp_path).run(graph_id)
    approval_id, _ = _only_pending(tmp_path)

    service = ApprovalService(tmp_path)
    service.decide_human(
        approval_id, decision="approved", actor="human", reason="looks fine"
    )
    service.close()

    summary = ExecutionSupervisor(tmp_path).resume(graph_id)
    assert summary.status == "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "completed"
    assert _approval_request_count(tmp_path) == 1


def test_supervisor_resume_fails_after_human_rejects(
    tmp_path, force_require_approval
):
    capability_id = "test.echo.approval"
    _register_capability(tmp_path, capability_id)
    graph_id = _seed_single_task_graph(tmp_path, capability_id)

    ExecutionSupervisor(tmp_path).run(graph_id)
    approval_id, _ = _only_pending(tmp_path)

    service = ApprovalService(tmp_path)
    service.decide_human(
        approval_id, decision="rejected", actor="human", reason="unsafe"
    )
    service.close()

    summary = ExecutionSupervisor(tmp_path).resume(graph_id)
    assert summary.status == "failed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "failed"
    assert "reject" in (summary.reason or "").lower()
    assert _approval_request_count(tmp_path) == 1


def test_supervisor_resume_stays_paused_after_deferred(
    tmp_path, force_require_approval
):
    capability_id = "test.echo.approval"
    _register_capability(tmp_path, capability_id)
    graph_id = _seed_single_task_graph(tmp_path, capability_id)

    ExecutionSupervisor(tmp_path).run(graph_id)
    approval_id, _ = _only_pending(tmp_path)

    service = ApprovalService(tmp_path)
    service.decide_human(
        approval_id, decision="deferred", actor="human", reason="revisit later"
    )
    service.close()

    summary = ExecutionSupervisor(tmp_path).resume(graph_id)
    assert summary.status == "paused"
    assert _approval_request_count(tmp_path) == 1


def test_supervisor_resume_blocks_on_revise(
    tmp_path, force_require_approval
):
    capability_id = "test.echo.approval"
    _register_capability(tmp_path, capability_id)
    graph_id = _seed_single_task_graph(tmp_path, capability_id)

    ExecutionSupervisor(tmp_path).run(graph_id)
    approval_id, _ = _only_pending(tmp_path)

    service = ApprovalService(tmp_path)
    service.decide_human(
        approval_id, decision="revise", actor="human", reason="tighten scope"
    )
    service.close()

    summary = ExecutionSupervisor(tmp_path).resume(graph_id)
    assert summary.status == "paused"
    assert "revis" in (summary.reason or "").lower()
    assert _approval_request_count(tmp_path) == 1
