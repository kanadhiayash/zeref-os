"""SQLite persistence for canonical Work Graphs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiroe.storage.state import StateDB
from shiroe.work.schema import (
    GraphStatus,
    NodeKind,
    NodeStatus,
    RetryPolicy,
    WorkEdge,
    WorkGraph,
    WorkNode,
)


class ConcurrentWorkUpdate(RuntimeError):
    """Raised when a compare-and-swap state update loses a race."""


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
