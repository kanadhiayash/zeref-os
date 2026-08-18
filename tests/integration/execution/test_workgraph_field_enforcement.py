"""Wave 2a: WorkNode fields that must actually gate completion.

These pin the enforcement (previously inert / persisted-only) of four
WorkNode fields in the supervisor execute/complete path:

1. ``approval_required`` — a task node cannot execute/complete without a
   valid, current human approval for its scope.
2. ``requires`` — EVERY entry must pass ``assert_executable`` before the
   node runs, not just ``requires[0]``.
3. ``expected_outputs`` — declared outputs absent from a successful result
   → node does not complete (transitions to ``failed``).
4. ``evidence_required`` — success with no evidence → node does not
   complete (transitions to ``failed``).

Terminal state for output/evidence/capability validation failures is the
existing ``NodeStatus.failed`` (the architecture has no separate
``blocked_validation`` state; ``failed`` is the closest existing one).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiroe.adapters.capabilities.base import AdapterResult, EnforcementLevel, HealthReport
from shiroe.adapters.capabilities.registry import register_adapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.execution.supervisor import ExecutionSupervisor
from shiroe.policy.approval_service import ApprovalService
from shiroe.work.store import ConcurrentWorkUpdate, WorkStore
from shiroe.work.compiler import compile_work_graph


class _CfgAdapter:
    """Adapter returning a caller-fixed output; counts invocations."""

    enforcement_level = EnforcementLevel.embedded
    supported_types = ("test_cfg",)

    def __init__(self, name: str, output):
        self.name = name
        self._output = output
        self.calls = 0

    def health(self):
        return HealthReport(
            adapter=self.name,
            detected_version="1",
            enforcement_level=self.enforcement_level,
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        self.calls += 1
        return AdapterResult(
            ok=True,
            output=self._output,
            usage={"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        )


def _write_policy_defaults(root: Path) -> None:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["capability.invoke", "subprocess"]}),
        encoding="utf-8",
    )


def _register(root: Path, capability_id: str, *, output=None, lifecycle: str = "active") -> tuple[_CfgAdapter, Path]:
    _write_policy_defaults(root)
    adapter = _CfgAdapter(name=f"adapter-{capability_id}", output=output if output is not None else {"message": "ok"})
    register_adapter(adapter.name, adapter)
    src = root / "capabilities" / capability_id.replace(".", "_") / "run.sh"
    src.parent.mkdir(parents=True, exist_ok=True)
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
            lifecycle=lifecycle,
            digest=trust.digest,
            manifest=manifest,
            source_kind="local-file",
            source_location=str(src),
        )
    finally:
        store.close()
    return adapter, src


def _seed(root: Path, node: dict) -> str:
    graph = compile_work_graph(
        {
            "id": "g-field",
            "objective": "field enforcement",
            "nodes": [node],
            "edges": [],
        }
    )
    WorkStore(root).create(graph)
    return graph.id


def _approve(root: Path, graph_id: str, node_id: str, scope: dict) -> str:
    service = ApprovalService(root)
    try:
        req = service.request(
            approval_type="action",
            requested_action="run node",
            scope=scope,
            reason="test seed",
            risk="high",
            graph_id=graph_id,
            node_id=node_id,
        )
        service.decide_human(req.id, decision="approved", actor="human", reason="ok")
    finally:
        service.close()
    return req.id


# --- Field 1: approval_required -------------------------------------------


def test_approval_required_task_blocks_without_approval(tmp_path):
    cap = "test.appr"
    _register(tmp_path, cap)
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "guarded",
        "requires": [cap], "approval_required": True,
        "metadata": {"scope": {"tag": "v1"}},
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status != "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value != "completed"


def test_approval_required_task_proceeds_with_valid_approval(tmp_path):
    cap = "test.appr"
    _register(tmp_path, cap)
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "guarded",
        "requires": [cap], "approval_required": True,
        "metadata": {"scope": {"tag": "v1"}},
    })
    _approve(tmp_path, graph_id, "n1", {"tag": "v1"})
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "completed"


def test_approval_required_task_blocks_on_wrong_scope(tmp_path):
    cap = "test.appr"
    _register(tmp_path, cap)
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "guarded",
        "requires": [cap], "approval_required": True,
        "metadata": {"scope": {"tag": "v2"}},  # node scope differs from approval
    })
    _approve(tmp_path, graph_id, "n1", {"tag": "v1"})
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status != "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value != "completed"


def test_approval_required_task_without_requires_still_gated(tmp_path):
    """approval_required must gate even the no-requires fast path."""
    _write_policy_defaults(tmp_path)
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "guarded",
        "approval_required": True, "metadata": {"scope": {"tag": "v1"}},
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert WorkStore(tmp_path).get_node("n1").status.value != "completed"


# --- Field 2: capability all-vs-first -------------------------------------


def test_all_required_capabilities_gated_not_just_first(tmp_path):
    good = "test.good"
    bad = "test.bad"
    _register(tmp_path, good)
    _, bad_src = _register(tmp_path, bad)
    # Drift the second required capability's source so assert_executable snaps
    # it to quarantined and refuses execution.
    bad_src.write_text("#!/bin/sh\necho TAMPERED\n", encoding="utf-8")
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "needs two",
        "requires": [good, bad],
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "failed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "failed"


# --- Field 3: expected_outputs --------------------------------------------


def test_expected_outputs_missing_fails_node(tmp_path):
    cap = "test.out"
    _register(tmp_path, cap, output={"message": "ok"})  # no report.json key
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "produce report",
        "requires": [cap], "expected_outputs": ["report.json"],
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "failed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "failed"


def test_expected_outputs_present_completes(tmp_path):
    cap = "test.out"
    _register(tmp_path, cap, output={"report.json": {"rows": 3}})
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "produce report",
        "requires": [cap], "expected_outputs": ["report.json"],
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "completed"


# --- Field 4: evidence_required -------------------------------------------


def test_evidence_required_missing_fails_node(tmp_path):
    cap = "test.ev"
    _register(tmp_path, cap, output={"message": "done"})  # no evidence
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "prove it",
        "requires": [cap], "evidence_required": True,
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "failed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "failed"


def test_evidence_required_present_completes(tmp_path):
    cap = "test.ev"
    _register(tmp_path, cap, output={"message": "done", "evidence": ["log#1"]})
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "prove it",
        "requires": [cap], "evidence_required": True,
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "completed"


# --- Adversarial state machine --------------------------------------------


def test_capability_revoked_mid_graph_blocks_downstream(tmp_path):
    good = "test.mg.good"
    revoked = "test.mg.revoked"
    _register(tmp_path, good)
    _register(tmp_path, revoked, lifecycle="revoked")
    graph = compile_work_graph({
        "id": "g-mid", "objective": "mid-graph revoke",
        "nodes": [
            {"id": "n1", "kind": "task", "objective": "first", "requires": [good]},
            {"id": "n2", "kind": "task", "objective": "second", "requires": [revoked]},
        ],
        "edges": [{"from": "n1", "to": "n2"}],
    })
    WorkStore(tmp_path).create(graph)
    summary = ExecutionSupervisor(tmp_path).run(graph.id)
    assert summary.status == "failed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "completed"
    assert WorkStore(tmp_path).get_node("n2").status.value == "failed"


def test_completed_node_not_re_executed(tmp_path):
    cap = "test.once"
    adapter, _ = _register(tmp_path, cap)
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "one", "requires": [cap],
    })
    ExecutionSupervisor(tmp_path).run(graph_id)
    assert adapter.calls == 1
    ExecutionSupervisor(tmp_path).run(graph_id)
    assert adapter.calls == 1  # not re-executed


def test_duplicate_completion_rejected(tmp_path):
    cap = "test.dup"
    _register(tmp_path, cap)
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "one", "requires": [cap],
    })
    store = WorkStore(tmp_path)
    version = store.get_node("n1").state_version
    store.set_node_status("n1", "completed", expected_version=version)
    with pytest.raises(ConcurrentWorkUpdate):
        # Re-completing with the now-stale version must be rejected (CAS).
        store.set_node_status("n1", "completed", expected_version=version)
