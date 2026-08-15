"""Bounded sequential supervisor for canonical Work Graphs."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiroe.adapters.capabilities.registry import resolve_adapter
from shiroe.capabilities.gate import CapabilityGateError, assert_executable
from shiroe.capabilities.store import CapabilityStore
from shiroe.execution.budget import BudgetTracker
from shiroe.nodes.dispatcher import NodeDispatcher
from shiroe.policy.schema import Action, ActionKind, Verdict
from shiroe.policy.service import PolicyService
from shiroe.work.schema import NodeKind, NodeStatus
from shiroe.work.store import ConcurrentWorkUpdate, WorkStore


@dataclass(frozen=True)
class RunSummary:
    graph_id: str
    status: str
    completed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ExecutionSupervisor:
    def __init__(
        self,
        root: Path | str,
        *,
        usd_max: float = 0.0,
        tokens_input_max: int = 0,
        tokens_output_max: int = 0,
        node_dispatcher: NodeDispatcher | None = None,
        remote_executor=None,
        transport=None,
    ):
        self.root = Path(root)
        self.store = WorkStore(self.root)
        self.node_dispatcher = node_dispatcher or NodeDispatcher(
            self.root,
            remote_executor=remote_executor,
            transport=transport,
        )
        self.budget = BudgetTracker(
            usd_max=usd_max,
            tokens_input_max=tokens_input_max,
            tokens_output_max=tokens_output_max,
        )

    def run(self, graph_id: str) -> RunSummary:
        # Resume-safety: any task-kind node that a previous pass parked in
        # `blocked` (approval or budget) needs to re-derive its status now.
        # Otherwise it stays out of ready_node_ids and the loop treats the
        # graph as deadlocked. Approval-kind nodes are refreshed by
        # refresh_readiness against the latest approval row.
        self._unblock_task_nodes(graph_id)
        self.store.set_graph_status(graph_id, "running")
        completed: list[str] = []
        failed: list[str] = []
        blocked: list[str] = []

        while True:
            self.store.refresh_readiness(graph_id)
            ready = self.store.ready_node_ids(graph_id)
            graph = self.store.get(graph_id)
            statuses = {node.id: self.store.get_node(node.id).status for node in graph.nodes}
            if not ready:
                if all(status in {NodeStatus.completed, NodeStatus.skipped} for status in statuses.values()):
                    self.store.set_graph_status(graph_id, "completed")
                    return RunSummary(graph_id, "completed", tuple(completed), tuple(failed), tuple(blocked), usage=self.budget.snapshot())
                self.store.set_graph_status(graph_id, "failed")
                pending = tuple(node_id for node_id, status in statuses.items() if status is NodeStatus.pending)
                return RunSummary(graph_id, "failed", tuple(completed), tuple(failed), tuple(blocked), reason=f"deadlocked pending nodes: {pending}", usage=self.budget.snapshot())

            for node_id in ready:
                state = self.store.get_node(node_id)
                node = state.node
                if node.kind is NodeKind.approval:
                    self.store.set_node_status(node_id, "blocked", expected_version=state.state_version)
                    blocked.append(node_id)
                    self.store.set_graph_status(graph_id, "paused")
                    return RunSummary(graph_id, "paused", tuple(completed), tuple(failed), tuple(blocked), reason="approval", usage=self.budget.snapshot())
                if not node.requires:
                    self.store.set_node_status(node_id, "completed", expected_version=state.state_version)
                    completed.append(node_id)
                    continue
                capability_id = node.requires[0]
                projection = dict(node.metadata.get("budget_projection", {}))
                burst = self.budget.would_exceed(projection)
                if burst:
                    self.store.set_node_status(node_id, "blocked", expected_version=state.state_version)
                    blocked.append(node_id)
                    self.store.set_graph_status(graph_id, "paused")
                    return RunSummary(graph_id, "paused", tuple(completed), tuple(failed), tuple(blocked), reason="budget", usage=self.budget.snapshot())

                try:
                    assert_executable(self.root, capability_id)
                    auth = PolicyService(self.root).authorize(
                        Action(ActionKind.capability_invoke, target=capability_id),
                        graph_id=graph_id,
                        node_id=node_id,
                        scope={"capability_id": capability_id, "node_id": node_id},
                    )
                    if auth.verdict is Verdict.require_approval:
                        self.store.set_node_status(node_id, "blocked", expected_version=state.state_version)
                        blocked.append(node_id)
                        self.store.set_graph_status(graph_id, "paused")
                        reason = f"approval {auth.approval_id}: {auth.reason}" if auth.approval_id else "approval"
                        return RunSummary(graph_id, "paused", tuple(completed), tuple(failed), tuple(blocked), reason=reason, usage=self.budget.snapshot())
                    if auth.verdict is Verdict.deny:
                        raise PermissionError(auth.reason)
                    attempt_id = self._record_attempt(graph_id, node_id, capability_id, "running")
                    inputs = {
                        "root": str(self.root),
                        "autonomy_mode": "policy-bound",
                        **dict(node.metadata.get("inputs", {})),
                    }
                    timeout_s = int(node.metadata.get("timeout_s", 60))
                    if node.placement.mode == "node":
                        result = self.node_dispatcher.invoke(
                            graph_id=graph_id,
                            work_node=node,
                            capability_id=capability_id,
                            inputs=inputs,
                            timeout_s=timeout_s,
                        )
                    else:
                        adapter_name = self._adapter_name(capability_id)
                        adapter = resolve_adapter(adapter_name)
                        result = adapter.invoke(
                            capability_id=capability_id,
                            action="run",
                            inputs=inputs,
                            timeout_s=timeout_s,
                        )
                    if not result.ok:
                        self._finish_attempt(attempt_id, "failed", error=result.error, usage=result.usage)
                        raise RuntimeError(result.error or "adapter failed")
                    usage = result.usage or {}
                    self.budget.charge(
                        usd=float(usage.get("cost_usd", 0.0) or 0.0),
                        tokens_input=int(usage.get("tokens_in", 0) or 0),
                        tokens_output=int(usage.get("tokens_out", 0) or 0),
                    )
                    self._finish_attempt(attempt_id, "completed", usage=usage)
                    version = self.store.node_state_version(node_id)
                    self.store.record_output(node_id, result.output or {}, expected_version=version)
                    self.store.set_node_status(node_id, "completed", expected_version=version + 1)
                    completed.append(node_id)
                except (CapabilityGateError, PermissionError, RuntimeError, ConcurrentWorkUpdate) as exc:
                    latest = self.store.get_node(node_id)
                    if latest.status is not NodeStatus.failed:
                        self.store.set_node_status(node_id, "failed", expected_version=latest.state_version)
                    failed.append(node_id)
                    self.store.set_graph_status(graph_id, "failed")
                    return RunSummary(graph_id, "failed", tuple(completed), tuple(failed), tuple(blocked), reason=str(exc), usage=self.budget.snapshot())

    def resume(self, graph_id: str) -> RunSummary:
        return self.run(graph_id)

    def _unblock_task_nodes(self, graph_id: str) -> None:
        """Reset task-kind blocked nodes to pending on run/resume entry.

        Approval-kind nodes stay put: refresh_readiness projects the
        latest approval decision onto them (approved/rejected/revise/...)
        each cycle.
        """
        graph = self.store.get(graph_id)
        for node in graph.nodes:
            if node.kind is NodeKind.approval:
                continue
            state = self.store.get_node(node.id)
            if state.status is NodeStatus.blocked:
                self.store.set_node_status(
                    node.id, "pending", expected_version=state.state_version
                )

    def _adapter_name(self, capability_id: str) -> str:
        store = CapabilityStore(self.root)
        try:
            row = store.conn.execute(
                "SELECT manifest FROM capability_versions WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
                (capability_id,),
            ).fetchone()
        finally:
            store.close()
        if row is None:
            raise CapabilityGateError(f"no manifest for capability {capability_id!r}")
        return json.loads(row[0])["entrypoint"]["adapter"]

    def _record_attempt(self, graph_id: str, node_id: str, capability_id: str, state: str) -> str:
        attempt_id = "wa_" + uuid.uuid4().hex[:16]
        self.store.conn.execute(
            """
            INSERT INTO work_attempts(id, graph_id, node_id, attempt, capability_id, state, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (attempt_id, graph_id, node_id, self._next_attempt(node_id), capability_id, state, _now()),
        )
        self.store.conn.commit()
        return attempt_id

    def _next_attempt(self, node_id: str) -> int:
        row = self.store.conn.execute(
            "SELECT COALESCE(MAX(attempt), 0) + 1 FROM work_attempts WHERE node_id=?",
            (node_id,),
        ).fetchone()
        return int(row[0])

    def _finish_attempt(
        self,
        attempt_id: str,
        state: str,
        *,
        error: str | None = None,
        usage: dict | None = None,
    ) -> None:
        self.store.conn.execute(
            "UPDATE work_attempts SET state=?, error=?, usage_json=?, ended_at=? WHERE id=?",
            (state, error, json.dumps(usage or {}, sort_keys=True), _now(), attempt_id),
        )
        self.store.conn.commit()
