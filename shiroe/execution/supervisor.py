"""Bounded sequential supervisor for canonical Work Graphs."""

from __future__ import annotations

import json
import time
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
from shiroe.policy.approval_service import ApprovalService
from shiroe.policy.approvals import ApprovalStatus
from shiroe.policy.schema import Action, ActionKind, Verdict
from shiroe.policy.service import PolicyService
from shiroe.storage import EventEnvelope, projections
from shiroe.verification.review import run_independent_review
from shiroe.verification.schema import CheckStatus
from shiroe.work.schema import NodeKind, NodeStatus
from shiroe.work.store import ConcurrentWorkUpdate, WorkStore

# Upper bound on any single inter-attempt backoff sleep. Retry budgets are
# bounded by max_attempts; this bounds the *wait* so a large backoff_s can
# never hang the run.
_MAX_BACKOFF_S = 30.0


@dataclass(frozen=True)
class RunSummary:
    graph_id: str
    status: str
    completed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    pending_approvals: tuple[str, ...] = ()


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
        # Injectable so tests can observe/skip backoff without real waiting.
        self._sleep = time.sleep

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
                    approval_id = self._ensure_approval_request(
                        graph_id=graph_id,
                        node_id=node_id,
                        action_kind="approval_node",
                        scope=dict(node.metadata.get("scope", {})),
                        reason=str(node.metadata.get("reason") or f"approval required for node {node_id}"),
                        risk=node.risk or "medium",
                    )
                    self.store.set_node_status(node_id, "blocked", expected_version=state.state_version)
                    blocked.append(node_id)
                    self.store.set_graph_status(graph_id, "paused")
                    return RunSummary(graph_id, "paused", tuple(completed), tuple(failed), tuple(blocked), reason="approval", usage=self.budget.snapshot(), pending_approvals=(approval_id,))
                # approval_required gate: a task node cannot execute/complete
                # (even via the no-requires fast path) without a current,
                # in-scope human approval. Wrong-scope / revoked / missing ->
                # block + pause, same contract as NodeKind.approval nodes.
                if node.approval_required and not self._task_approval_current(
                    graph_id, node_id, dict(node.metadata.get("scope", {}))
                ):
                    approval_id = self._ensure_approval_request(
                        graph_id=graph_id,
                        node_id=node_id,
                        action_kind="approval_required",
                        scope=dict(node.metadata.get("scope", {})),
                        reason=str(node.metadata.get("reason") or f"approval required for node {node_id}"),
                        risk=node.risk or "medium",
                    )
                    self.store.set_node_status(node_id, "blocked", expected_version=state.state_version)
                    blocked.append(node_id)
                    self.store.set_graph_status(graph_id, "paused")
                    return RunSummary(graph_id, "paused", tuple(completed), tuple(failed), tuple(blocked), reason="approval_required", usage=self.budget.snapshot(), pending_approvals=(approval_id,))
                if not node.requires:
                    # independent_review gates even the no-requires fast path:
                    # a review-required node with no executor cannot be
                    # verified, so it stays blocked rather than completing.
                    if node.independent_review and not self._independent_review_passes(graph_id, node):
                        self.store.set_node_status(node_id, "blocked", expected_version=state.state_version)
                        blocked.append(node_id)
                        self.store.set_graph_status(graph_id, "paused")
                        return RunSummary(graph_id, "paused", tuple(completed), tuple(failed), tuple(blocked), reason="independent_review", usage=self.budget.snapshot())
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

                # Bounded retry. ``attempts_done`` is seeded from the persisted
                # attempt count so a restart/resume continues the same budget
                # instead of resetting it -- attempts already spent stay spent.
                max_attempts = max(1, node.retry.max_attempts)
                backoff_s = min(max(0.0, float(node.retry.backoff_s)), _MAX_BACKOFF_S)
                attempts_done = self._attempt_count(node_id)
                last_error: Exception | None = None
                node_completed = False
                while attempts_done < max_attempts:
                    attempts_done += 1
                    try:
                        # Gate ALL required capabilities, not just requires[0]:
                        # any drifted/revoked/quarantined entry blocks the node.
                        for required_id in node.requires:
                            assert_executable(self.root, required_id)
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
                            pending = (auth.approval_id,) if auth.approval_id else ()
                            return RunSummary(graph_id, "paused", tuple(completed), tuple(failed), tuple(blocked), reason=reason, usage=self.budget.snapshot(), pending_approvals=pending)
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
                        # Completion-validation gates. A successful adapter run
                        # that fails to deliver declared outputs or required
                        # evidence must NOT complete -> reuse the failure path
                        # (attempt failed, retried, else node -> failed).
                        out = result.output if isinstance(result.output, dict) else {}
                        missing = [name for name in node.expected_outputs if name not in out]
                        if missing:
                            self._finish_attempt(attempt_id, "failed", error=f"missing expected outputs: {missing}", usage=result.usage)
                            raise RuntimeError(f"node {node_id} missing expected outputs: {missing}")
                        if node.evidence_required and not self._has_evidence(out):
                            self._finish_attempt(attempt_id, "failed", error="evidence_required but none produced", usage=result.usage)
                            raise RuntimeError(f"node {node_id} completed without required evidence")
                        usage = result.usage or {}
                        self.budget.charge(
                            usd=float(usage.get("cost_usd", 0.0) or 0.0),
                            tokens_input=int(usage.get("tokens_in", 0) or 0),
                            tokens_output=int(usage.get("tokens_out", 0) or 0),
                        )
                        self._finish_attempt(attempt_id, "completed", usage=usage)
                        version = self.store.node_state_version(node_id)
                        self.store.record_output(node_id, result.output or {}, expected_version=version)
                        # independent_review gate: execution succeeded, but the
                        # node cannot complete until an independent reviewer
                        # passes it. A failing/missing review pauses (blocked),
                        # not retried -- it is a human/reviewer decision.
                        if node.independent_review and not self._independent_review_passes(graph_id, node):
                            self.store.set_node_status(node_id, "blocked", expected_version=version + 1)
                            blocked.append(node_id)
                            self.store.set_graph_status(graph_id, "paused")
                            return RunSummary(graph_id, "paused", tuple(completed), tuple(failed), tuple(blocked), reason="independent_review", usage=self.budget.snapshot())
                        self.store.set_node_status(node_id, "completed", expected_version=version + 1)
                        completed.append(node_id)
                        node_completed = True
                        break
                    except (CapabilityGateError, PermissionError, RuntimeError, ConcurrentWorkUpdate) as exc:
                        last_error = exc
                        if attempts_done < max_attempts:
                            self._sleep(backoff_s)

                if node_completed:
                    continue
                latest = self.store.get_node(node_id)
                if latest.status is not NodeStatus.failed:
                    self.store.set_node_status(node_id, "failed", expected_version=latest.state_version)
                failed.append(node_id)
                self.store.set_graph_status(graph_id, "failed")
                return RunSummary(graph_id, "failed", tuple(completed), tuple(failed), tuple(blocked), reason=str(last_error), usage=self.budget.snapshot())

    def resume(self, graph_id: str) -> RunSummary:
        return self.run(graph_id)

    def _ensure_approval_request(
        self,
        *,
        graph_id: str,
        node_id: str,
        action_kind: str,
        scope: dict,
        reason: str,
        risk: str = "medium",
    ) -> str:
        """Return the approval request that gates ``node_id``, minting one
        via ``ApprovalService.request`` if none exists yet.

        Dedup is keyed on (graph_id, node_id) alone -- the same lookup
        ``refresh_readiness``/``_task_approval_current`` already treat as
        the node's governing approval -- so a request seeded by another
        caller (CLI, PolicyService, a test) is reused rather than
        duplicated, even if its action_kind/requested_action differ from
        what this call would have used.
        """
        existing_id = self.store._latest_approval_id(graph_id, node_id)
        if existing_id is not None:
            return existing_id
        service = ApprovalService(self.root)
        try:
            req = service.request(
                approval_type="action",
                requested_action=f"approve {node_id}",
                scope=scope,
                reason=reason,
                risk=risk,
                graph_id=graph_id,
                node_id=node_id,
                action_kind=action_kind,
            )
        finally:
            service.close()
        return req.id

    def _task_approval_current(self, graph_id: str, node_id: str, scope: dict) -> bool:
        """True iff the latest human approval for this node is approved AND
        still current for ``scope``. Reuses the approval record + scope-digest
        mechanism (ApprovalService.assert_current stales a scope mismatch)."""
        approval_id = self.store._latest_approval_id(graph_id, node_id)
        if approval_id is None:
            return False
        service = ApprovalService(self.root)
        try:
            req = service.assert_current(approval_id, current_scope=scope)
        finally:
            service.close()
        return req.status is ApprovalStatus.approved

    @staticmethod
    def _has_evidence(output: dict) -> bool:
        return bool(output.get("evidence") or output.get("evidence_refs"))

    def _independent_review_passes(self, graph_id: str, node) -> bool:
        """True iff an independent review of ``node`` returns a pass.

        The reviewer capability is named in ``node.metadata`` and must be
        distinct from the executor (``node.requires[0]``). A missing reviewer,
        an unusable one, or any non-pass verdict is treated as NOT passing so
        the node stays blocked rather than completing unverified.
        """
        reviewer = node.metadata.get("reviewer_capability_id")
        executor = node.requires[0] if node.requires else None
        if not reviewer or not executor:
            return False
        try:
            check = run_independent_review(
                self.root,
                node_id=node.id,
                executor_capability_id=executor,
                reviewer_capability_id=reviewer,
                subject={"output": self.store.node_output(node.id) or {}},
                required=True,
            )
        except (CapabilityGateError, ValueError):
            return False
        return check.status is CheckStatus.passed

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
        env = self.store.events.append(EventEnvelope(
            event_type="attempt.started",
            actor="system",
            target=f"work_attempt:{attempt_id}",
            payload={
                "id": attempt_id,
                "graph_id": graph_id,
                "node_id": node_id,
                "attempt": self._next_attempt(node_id),
                "capability_id": capability_id,
                "state": state,
                "event_time": _now(),
            },
        ))
        projections.apply_event(self.store.conn, env)
        self.store.conn.commit()
        return attempt_id

    def _attempt_count(self, node_id: str) -> int:
        row = self.store.conn.execute(
            "SELECT COUNT(*) FROM work_attempts WHERE node_id=?",
            (node_id,),
        ).fetchone()
        return int(row[0])

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
        row = self.store.conn.execute(
            "SELECT graph_id, node_id, attempt, capability_id FROM work_attempts WHERE id=?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise KeyError(attempt_id)
        event_type = "attempt.completed" if state == "completed" else "attempt.failed"
        env = self.store.events.append(EventEnvelope(
            event_type=event_type,
            actor="system",
            target=f"work_attempt:{attempt_id}",
            payload={
                "id": attempt_id,
                "graph_id": row[0],
                "node_id": row[1],
                "attempt": row[2],
                "capability_id": row[3],
                "state": state,
                "error": error,
                "usage": usage or {},
                "event_time": _now(),
            },
        ))
        projections.apply_event(self.store.conn, env)
        self.store.conn.commit()
