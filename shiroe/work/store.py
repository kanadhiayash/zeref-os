"""Work Graph projection over canonical event history.

``WorkStore`` is NOT the source of truth -- it is a SQLite projection
rebuilt from ``run.*``/``step.*`` events in the canonical JSONL log
(ADR-0001), the same split ``CapabilityStore`` and ``ApprovalService``
already follow. Every mutating method appends an event first, then folds
it into ``work_graphs``/``work_nodes``/``work_edges`` via the shared
``storage.projections.apply_event`` reducer -- the one interpreter both
the live write path and ``EventLog.replay_into`` share, so replay can
never drift from live state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shiroe.storage import EventEnvelope, EventLog, StateDB, projections
from shiroe.policy.approvals import ApprovalStatus
from shiroe.policy.approval_service import ApprovalService
from shiroe.work.schema import (
    GraphStatus,
    NodeKind,
    NodeStatus,
    Placement,
    RetryPolicy,
    WorkEdge,
    WorkGraph,
    WorkNode,
)
from shiroe.work.readiness import ready_node_ids as calculate_ready_node_ids


class ConcurrentWorkUpdate(RuntimeError):
    """Raised when a compare-and-swap state update loses a race."""


@dataclass(frozen=True)
class StoredWorkNode:
    node: WorkNode
    status: NodeStatus
    state_version: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _loads(text: str | None, fallback: Any) -> Any:
    if text is None:
        return fallback
    return json.loads(text)


class WorkStore:
    # Node-status targets that map onto a distinct step.* event type. Any
    # target not listed here (blocked, pending, skipped, ...) falls back to
    # "step.started" -- the whitelist has no step.blocked/step.paused type,
    # and the real target status travels in payload["to"] regardless of
    # which wrapper event_type carried it, so the fallback loses no
    # information.
    _NODE_STATUS_EVENTS: dict[NodeStatus, str] = {
        NodeStatus.running: "step.started",
        NodeStatus.completed: "step.completed",
        NodeStatus.failed: "step.failed",
    }

    # GraphStatus targets that map onto a distinct run.* event type.
    # "running" is handled separately (run.started vs run.resumed depends
    # on the current status, not just the target).
    _GRAPH_STATUS_EVENTS: dict[GraphStatus, str] = {
        GraphStatus.paused: "run.paused",
        GraphStatus.completed: "run.completed",
        GraphStatus.failed: "run.failed",
        GraphStatus.cancelled: "run.cancelled",
    }

    def __init__(self, root: Path | str):
        self.db = StateDB(root)
        self.conn = self.db.connect()
        self.db.migrate()
        self.root = self.db.root
        self.events = EventLog(self.root, mirror_conn=self.conn)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "WorkStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def create(self, graph: WorkGraph) -> None:
        """Event-first graph creation: append ``run.created`` carrying the
        full compiled graph shape, then fold it via the shared projection
        dispatcher. No direct table INSERT here -- the reducer
        (``storage.projections._apply_work``) is the only interpreter, so
        replay reproduces exactly this state."""
        now = _now()
        payload = {
            "id": graph.id,
            "objective": graph.objective,
            "constraints": list(graph.constraints),
            "success_criteria": list(graph.success_criteria),
            "status": GraphStatus(graph.status).value,
            "version": graph.version,
            "event_time": now,
            "nodes": [
                {
                    "id": node.id,
                    "kind": node.kind.value,
                    "objective": node.objective,
                    "requires": list(node.requires),
                    "risk": node.risk,
                    "approval_required": node.approval_required,
                    "independent_review": node.independent_review,
                    "evidence_required": node.evidence_required,
                    "expected_outputs": list(node.expected_outputs),
                    "retry": {
                        "max_attempts": node.retry.max_attempts,
                        "backoff_s": node.retry.backoff_s,
                    },
                    "placement": {
                        "mode": node.placement.mode,
                        "node_id": node.placement.node_id,
                    },
                    "metadata": node.metadata,
                    "status": NodeStatus.pending.value,
                }
                for node in graph.nodes
            ],
            "edges": [
                {"src_id": edge.src_id, "dst_id": edge.dst_id} for edge in graph.edges
            ],
        }
        env = self.events.append(EventEnvelope(
            event_type="run.created",
            actor="system",
            target=f"graph:{graph.id}",
            payload=payload,
        ))
        projections.apply_event(self.conn, env)
        self.conn.commit()

    def get(self, graph_id: str) -> WorkGraph:
        row = self.conn.execute(
            """
            SELECT id, objective, constraints_json, success_criteria_json, status, version
            FROM work_graphs WHERE id=?
            """,
            (graph_id,),
        ).fetchone()
        if row is None:
            raise KeyError(graph_id)
        node_rows = self.conn.execute(
            """
            SELECT id, graph_id, kind, objective, requires_json, risk,
                   approval_required, independent_review, evidence_required,
                   expected_outputs_json, retry_json, placement_json, metadata_json
            FROM work_nodes WHERE graph_id=? ORDER BY id
            """,
            (graph_id,),
        ).fetchall()
        edge_rows = self.conn.execute(
            "SELECT graph_id, src_id, dst_id FROM work_edges WHERE graph_id=? ORDER BY src_id, dst_id",
            (graph_id,),
        ).fetchall()
        nodes = tuple(self._node_from_row(r) for r in node_rows)
        edges = tuple(WorkEdge(graph_id=r[0], src_id=r[1], dst_id=r[2]) for r in edge_rows)
        return WorkGraph(
            id=row[0],
            objective=row[1],
            constraints=tuple(_loads(row[2], [])),
            success_criteria=tuple(_loads(row[3], [])),
            status=GraphStatus(row[4]),
            version=int(row[5]),
            nodes=nodes,
            edges=edges,
        )

    def _node_from_row(self, row: tuple) -> WorkNode:
        retry = _loads(row[10], {})
        return WorkNode(
            id=row[0],
            graph_id=row[1],
            kind=NodeKind(row[2]),
            objective=row[3],
            requires=tuple(_loads(row[4], [])),
            risk=row[5],
            approval_required=bool(row[6]),
            independent_review=bool(row[7]),
            evidence_required=bool(row[8]),
            expected_outputs=tuple(_loads(row[9], [])),
            retry=RetryPolicy(**retry),
            placement=Placement(**_loads(row[11], {"mode": "local", "node_id": None})),
            metadata=_loads(row[12], {}),
        )

    def set_graph_status(self, graph_id: str, status: GraphStatus | str) -> None:
        next_status = GraphStatus(status)
        row = self.conn.execute(
            "SELECT status FROM work_graphs WHERE id=?", (graph_id,)
        ).fetchone()
        if row is None:
            raise KeyError(graph_id)
        current = row[0]
        if next_status is GraphStatus.running:
            event_type = "run.resumed" if current == GraphStatus.paused.value else "run.started"
        else:
            event_type = self._GRAPH_STATUS_EVENTS.get(next_status)
            if event_type is None:
                raise ValueError(f"unsupported graph status transition: {next_status.value!r}")
        env = self.events.append(EventEnvelope(
            event_type=event_type,
            actor="system",
            target=f"graph:{graph_id}",
            payload={"id": graph_id, "status": next_status.value, "event_time": _now()},
        ))
        projections.apply_event(self.conn, env)
        self.conn.commit()

    def node_state_version(self, node_id: str) -> int:
        row = self.conn.execute(
            "SELECT state_version FROM work_nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        return int(row[0])

    def _emit_node_status(self, node_id: str, next_status: NodeStatus) -> None:
        """Append the step.* event for a node-status transition and fold it.

        No CAS predicate here -- the reducer applies a plain UPDATE so
        replay stays deterministic. The caller (``set_node_status``) does
        its own pre-check before calling this; ``refresh_readiness`` calls
        it unconditionally after already deciding the transition is real.
        """
        event_type = self._NODE_STATUS_EVENTS.get(next_status, "step.started")
        env = self.events.append(EventEnvelope(
            event_type=event_type,
            actor="system",
            target=f"work_node:{node_id}",
            payload={"node_id": node_id, "to": next_status.value},
        ))
        projections.apply_event(self.conn, env)
        self.conn.commit()

    def set_node_status(
        self,
        node_id: str,
        status: NodeStatus | str,
        *,
        expected_version: int,
    ) -> None:
        next_status = NodeStatus(status)
        row = self.conn.execute(
            "SELECT state_version FROM work_nodes WHERE id=?", (node_id,)
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        if int(row[0]) != expected_version:
            raise ConcurrentWorkUpdate(f"stale work node version: {node_id}")
        # ponytail: pre-check + append + plain-UPDATE assumes a single
        # writer between the check and the commit (this project's
        # single-process supervisor). A second writer racing the same
        # window is not rejected by the reducer's unconditional UPDATE --
        # add a real per-node lock (or a CAS-guarded UPDATE gating the
        # event append itself) if a multi-writer supervisor ever lands.
        self._emit_node_status(node_id, next_status)

    def record_output(self, node_id: str, output: dict[str, Any], *, expected_version: int) -> None:
        row = self.conn.execute(
            "SELECT state_version FROM work_nodes WHERE id=?", (node_id,)
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        if int(row[0]) != expected_version:
            raise ConcurrentWorkUpdate(f"stale work node version: {node_id}")
        # Reuses step.completed (no dedicated "output recorded" event type
        # is whitelisted): the reducer keys off payload["output"] rather
        # than the event_type name, and this call site never changes
        # status (record_output runs before the status flips to
        # "completed"), so no "to" key is sent.
        env = self.events.append(EventEnvelope(
            event_type="step.completed",
            actor="system",
            target=f"work_node:{node_id}",
            payload={"node_id": node_id, "output": output},
        ))
        projections.apply_event(self.conn, env)
        self.conn.commit()

    def node_output(self, node_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT output_json FROM work_nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        return _loads(row[0], None)

    def get_node(self, node_id: str) -> StoredWorkNode:
        row = self.conn.execute(
            """
            SELECT id, graph_id, kind, objective, requires_json, risk,
                   approval_required, independent_review, evidence_required,
                   expected_outputs_json, retry_json, placement_json, metadata_json,
                   status, state_version
            FROM work_nodes WHERE id=?
            """,
            (node_id,),
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        node = self._node_from_row(row[:13])
        return StoredWorkNode(node=node, status=NodeStatus(row[13]), state_version=int(row[14]))

    def _node_statuses(self, graph_id: str) -> dict[str, str]:
        rows = self.conn.execute(
            "SELECT id, status FROM work_nodes WHERE graph_id=?",
            (graph_id,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def _latest_approval_id(self, graph_id: str, node_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT id FROM approval_requests
            WHERE graph_id=? AND node_id=?
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (graph_id, node_id),
        ).fetchone()
        return row[0] if row else None

    # Approval-lifecycle mapping for approval-kind nodes. Each of the six
    # ApprovalStatus values is projected onto exactly one NodeStatus so
    # rejected / revise decisions are not silently retried as pending, and
    # stale / deferred still block downstream nodes until a fresh decision
    # covers the current scope.
    _APPROVAL_TO_NODE_STATUS: dict[ApprovalStatus, NodeStatus] = {
        ApprovalStatus.approved: NodeStatus.completed,
        ApprovalStatus.pending: NodeStatus.pending,
        ApprovalStatus.deferred: NodeStatus.pending,
        ApprovalStatus.stale: NodeStatus.pending,
        ApprovalStatus.rejected: NodeStatus.failed,
        ApprovalStatus.revise: NodeStatus.blocked,
    }

    def refresh_readiness(self, graph_id: str) -> None:
        graph = self.get(graph_id)
        service = ApprovalService(self.root)
        try:
            for node in graph.nodes:
                if node.kind is not NodeKind.approval:
                    continue
                approval_id = self._latest_approval_id(graph_id, node.id)
                if approval_id is None:
                    continue
                scope = node.metadata.get("scope", {})
                req = service.assert_current(approval_id, current_scope=scope)
                next_status = self._APPROVAL_TO_NODE_STATUS[req.status]
                current_status = self.get_node(node.id).status
                if next_status is current_status:
                    continue
                self._emit_node_status(node.id, next_status)
        finally:
            service.close()

    def ready_node_ids(self, graph_id: str) -> tuple[str, ...]:
        graph = self.get(graph_id)
        statuses = self._node_statuses(graph_id)
        ready = set(calculate_ready_node_ids(graph, statuses))
        predecessors: dict[str, set[str]] = {node.id: set() for node in graph.nodes}
        for edge in graph.edges:
            predecessors[edge.dst_id].add(edge.src_id)
        for node in graph.nodes:
            if node.kind is not NodeKind.approval:
                continue
            if statuses.get(node.id, NodeStatus.pending.value) != NodeStatus.pending.value:
                continue
            if all(
                statuses.get(pred) in {NodeStatus.completed.value, NodeStatus.skipped.value}
                for pred in predecessors[node.id]
            ):
                ready.add(node.id)
        return tuple(sorted(ready))
