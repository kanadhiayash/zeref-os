"""SQLite persistence for canonical Work Graphs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shiroe.storage.state import StateDB
from shiroe.policy.approvals import ApprovalStatus
from shiroe.policy.approval_service import ApprovalService
from shiroe.work.schema import (
    GraphStatus,
    NodeKind,
    NodeStatus,
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
    def __init__(self, root: Path | str):
        self.db = StateDB(root)
        self.conn = self.db.connect()
        self.db.migrate()

    def close(self) -> None:
        self.db.close()

    def create(self, graph: WorkGraph) -> None:
        now = _now()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO work_graphs(
                    id, objective, constraints_json, success_criteria_json,
                    status, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    graph.id,
                    graph.objective,
                    _json(list(graph.constraints)),
                    _json(list(graph.success_criteria)),
                    graph.status.value,
                    graph.version,
                    now,
                    now,
                ),
            )
            for node in graph.nodes:
                self.conn.execute(
                    """
                    INSERT INTO work_nodes(
                        id, graph_id, kind, objective, requires_json, risk,
                        approval_required, independent_review, evidence_required,
                        expected_outputs_json, retry_json, metadata_json, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node.id,
                        node.graph_id,
                        node.kind.value,
                        node.objective,
                        _json(list(node.requires)),
                        node.risk,
                        int(node.approval_required),
                        int(node.independent_review),
                        int(node.evidence_required),
                        _json(list(node.expected_outputs)),
                        _json({
                            "max_attempts": node.retry.max_attempts,
                            "backoff_s": node.retry.backoff_s,
                        }),
                        _json(node.metadata),
                        NodeStatus.pending.value,
                    ),
                )
            for edge in graph.edges:
                self.conn.execute(
                    "INSERT INTO work_edges(graph_id, src_id, dst_id) VALUES (?, ?, ?)",
                    (edge.graph_id, edge.src_id, edge.dst_id),
                )

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
                   expected_outputs_json, retry_json, metadata_json
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
            metadata=_loads(row[11], {}),
        )

    def set_graph_status(self, graph_id: str, status: GraphStatus | str) -> None:
        next_status = GraphStatus(status).value
        with self.conn:
            cur = self.conn.execute(
                "UPDATE work_graphs SET status=?, updated_at=? WHERE id=?",
                (next_status, _now(), graph_id),
            )
        if cur.rowcount != 1:
            raise KeyError(graph_id)

    def node_state_version(self, node_id: str) -> int:
        row = self.conn.execute(
            "SELECT state_version FROM work_nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        return int(row[0])

    def set_node_status(
        self,
        node_id: str,
        status: NodeStatus | str,
        *,
        expected_version: int,
    ) -> None:
        next_status = NodeStatus(status).value
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE work_nodes
                SET status=?, state_version=state_version+1
                WHERE id=? AND state_version=?
                """,
                (next_status, node_id, expected_version),
            )
        if cur.rowcount != 1:
            raise ConcurrentWorkUpdate(f"stale work node version: {node_id}")

    def record_output(self, node_id: str, output: dict[str, Any], *, expected_version: int) -> None:
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE work_nodes
                SET output_json=?, state_version=state_version+1
                WHERE id=? AND state_version=?
                """,
                (_json(output), node_id, expected_version),
            )
        if cur.rowcount != 1:
            raise ConcurrentWorkUpdate(f"stale work node version: {node_id}")

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
                   expected_outputs_json, retry_json, metadata_json, status, state_version
            FROM work_nodes WHERE id=?
            """,
            (node_id,),
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        node = self._node_from_row(row[:12])
        return StoredWorkNode(node=node, status=NodeStatus(row[12]), state_version=int(row[13]))

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
        service = ApprovalService(self.db.root)
        with self.conn:
            for node in graph.nodes:
                if node.kind is not NodeKind.approval:
                    continue
                approval_id = self._latest_approval_id(graph_id, node.id)
                if approval_id is None:
                    continue
                scope = node.metadata.get("scope", {})
                req = service.assert_current(approval_id, current_scope=scope)
                next_status = self._APPROVAL_TO_NODE_STATUS[req.status].value
                self.conn.execute(
                    """
                    UPDATE work_nodes
                    SET status=?,
                        state_version=CASE WHEN status=? THEN state_version ELSE state_version+1 END
                    WHERE id=?
                    """,
                    (next_status, next_status, node.id),
                )

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
