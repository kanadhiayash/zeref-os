"""m0004 — scope-bound human approval records."""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approval_requests (
            id TEXT PRIMARY KEY,
            graph_id TEXT,
            node_id TEXT,
            approval_type TEXT NOT NULL,
            action_kind TEXT,
            requested_action TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            scope_digest TEXT NOT NULL,
            reason TEXT NOT NULL,
            options_json TEXT NOT NULL,
            evidence_refs_json TEXT NOT NULL,
            risk TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by TEXT,
            decision_reason TEXT,
            FOREIGN KEY(graph_id) REFERENCES work_graphs(id),
            FOREIGN KEY(node_id) REFERENCES work_nodes(id)
        );
        CREATE INDEX IF NOT EXISTS ix_approval_status ON approval_requests(status);
        CREATE INDEX IF NOT EXISTS ix_approval_graph ON approval_requests(graph_id);
        CREATE INDEX IF NOT EXISTS ix_approval_node ON approval_requests(node_id);
        CREATE INDEX IF NOT EXISTS ix_approval_scope_digest ON approval_requests(scope_digest);
        """
    )
