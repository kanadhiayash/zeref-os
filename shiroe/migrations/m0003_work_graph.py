"""m0003 — canonical Work Graph persistence."""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS work_graphs (
            id TEXT PRIMARY KEY,
            objective TEXT NOT NULL,
            constraints_json TEXT NOT NULL,
            success_criteria_json TEXT NOT NULL,
            status TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_work_graphs_status ON work_graphs(status);

        CREATE TABLE IF NOT EXISTS work_nodes (
            id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            objective TEXT NOT NULL,
            requires_json TEXT NOT NULL,
            risk TEXT NOT NULL,
            approval_required INTEGER NOT NULL DEFAULT 0,
            independent_review INTEGER NOT NULL DEFAULT 0,
            evidence_required INTEGER NOT NULL DEFAULT 0,
            expected_outputs_json TEXT NOT NULL,
            retry_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            status TEXT NOT NULL,
            output_json TEXT,
            state_version INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(graph_id) REFERENCES work_graphs(id)
        );
        CREATE INDEX IF NOT EXISTS ix_work_nodes_graph ON work_nodes(graph_id);
        CREATE INDEX IF NOT EXISTS ix_work_nodes_status ON work_nodes(status);
        CREATE INDEX IF NOT EXISTS ix_work_nodes_graph_status ON work_nodes(graph_id, status);

        CREATE TABLE IF NOT EXISTS work_edges (
            graph_id TEXT NOT NULL,
            src_id TEXT NOT NULL,
            dst_id TEXT NOT NULL,
            PRIMARY KEY(graph_id, src_id, dst_id),
            FOREIGN KEY(graph_id) REFERENCES work_graphs(id),
            FOREIGN KEY(src_id) REFERENCES work_nodes(id),
            FOREIGN KEY(dst_id) REFERENCES work_nodes(id)
        );

        CREATE TABLE IF NOT EXISTS work_attempts (
            id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            capability_id TEXT,
            state TEXT NOT NULL,
            input_digest TEXT,
            output_digest TEXT,
            error TEXT,
            usage_json TEXT,
            started_at TEXT,
            ended_at TEXT,
            FOREIGN KEY(graph_id) REFERENCES work_graphs(id),
            FOREIGN KEY(node_id) REFERENCES work_nodes(id)
        );
        CREATE INDEX IF NOT EXISTS ix_work_attempts_node ON work_attempts(node_id);
        CREATE INDEX IF NOT EXISTS ix_work_attempts_graph_node ON work_attempts(graph_id, node_id);
        """
    )
