"""m0100 — current Shiroe canonical state baseline."""

from __future__ import annotations

import sqlite3


DESTRUCTIVE = True


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_records (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            claim TEXT NOT NULL,
            summary TEXT,
            status TEXT NOT NULL,
            confidence TEXT NOT NULL,
            evidence_grade TEXT NOT NULL,
            privacy_class TEXT NOT NULL,
            authority REAL NOT NULL DEFAULT 0.0,
            scope TEXT NOT NULL DEFAULT 'project',
            valid_from TEXT,
            valid_until TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            owner TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            tags_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS ix_memory_records_kind ON memory_records(kind);
        CREATE INDEX IF NOT EXISTS ix_memory_records_status ON memory_records(status);
        CREATE INDEX IF NOT EXISTS ix_memory_records_scope ON memory_records(scope);

        CREATE TABLE IF NOT EXISTS memory_sources (
            id TEXT PRIMARY KEY,
            memory_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            source_digest TEXT,
            observed_at TEXT,
            retrieved_at TEXT,
            provenance TEXT NOT NULL,
            FOREIGN KEY(memory_id) REFERENCES memory_records(id)
        );
        CREATE INDEX IF NOT EXISTS ix_memory_sources_memory ON memory_sources(memory_id);

        CREATE TABLE IF NOT EXISTS memory_relations (
            id TEXT PRIMARY KEY,
            src_id TEXT NOT NULL,
            dst_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(src_id) REFERENCES memory_records(id),
            FOREIGN KEY(dst_id) REFERENCES memory_records(id)
        );
        CREATE INDEX IF NOT EXISTS ix_memory_relations_kind ON memory_relations(kind);

        CREATE TABLE IF NOT EXISTS memory_events (
            event_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            run_id TEXT,
            actor TEXT NOT NULL,
            target TEXT,
            payload TEXT NOT NULL,
            privacy_class TEXT NOT NULL,
            hash TEXT NOT NULL,
            previous_hash TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_memory_events_ts ON memory_events(timestamp);
        CREATE INDEX IF NOT EXISTS ix_memory_events_type ON memory_events(event_type);
        CREATE INDEX IF NOT EXISTS ix_memory_events_run ON memory_events(run_id);

        CREATE TABLE IF NOT EXISTS capabilities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            lifecycle TEXT NOT NULL,
            current_digest TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_capabilities_lifecycle ON capabilities(lifecycle);

        CREATE TABLE IF NOT EXISTS capability_versions (
            id TEXT PRIMARY KEY,
            capability_id TEXT NOT NULL,
            version TEXT NOT NULL,
            digest TEXT NOT NULL,
            manifest TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_location TEXT NOT NULL,
            license TEXT,
            adapter TEXT,
            compatibility TEXT,
            lifecycle TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(capability_id) REFERENCES capabilities(id)
        );
        CREATE INDEX IF NOT EXISTS ix_capability_versions_cap ON capability_versions(capability_id);
        CREATE INDEX IF NOT EXISTS ix_capability_versions_digest ON capability_versions(digest);

        CREATE TABLE IF NOT EXISTS capability_permissions (
            id TEXT PRIMARY KEY,
            capability_id TEXT NOT NULL,
            filesystem_read TEXT NOT NULL,
            filesystem_write TEXT NOT NULL,
            network TEXT NOT NULL,
            secrets TEXT NOT NULL,
            subprocess INTEGER NOT NULL DEFAULT 0,
            external_write INTEGER NOT NULL DEFAULT 0,
            destructive INTEGER NOT NULL DEFAULT 0,
            approved_at TEXT,
            approved_by TEXT,
            FOREIGN KEY(capability_id) REFERENCES capabilities(id)
        );

        CREATE TABLE IF NOT EXISTS adapter_status (
            id TEXT PRIMARY KEY,
            adapter TEXT NOT NULL,
            detected_version TEXT,
            enforcement_level TEXT NOT NULL,
            supported_features TEXT,
            last_health_check TEXT,
            failure_reason TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_adapter_status_adapter ON adapter_status(adapter);

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
            placement_json TEXT NOT NULL DEFAULT '{"mode":"local","node_id":null}',
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

        CREATE TABLE IF NOT EXISTS approval_advice (
            id TEXT PRIMARY KEY,
            approval_id TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            rationale TEXT NOT NULL,
            risks_json TEXT NOT NULL,
            evidence_gaps_json TEXT NOT NULL,
            conditions_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(approval_id) REFERENCES approval_requests(id)
        );
        CREATE INDEX IF NOT EXISTS ix_approval_advice_approval
            ON approval_advice(approval_id);

        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('controller','worker')),
            transport TEXT NOT NULL,
            transport_host TEXT NOT NULL,
            ssh_user TEXT NOT NULL,
            tailscale_stable_id TEXT,
            trusted INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'unknown',
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            capability_digest TEXT,
            last_seen_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_nodes_role_trusted ON nodes(role, trusted);
        CREATE INDEX IF NOT EXISTS ix_nodes_transport_host ON nodes(transport, transport_host);

        CREATE TABLE IF NOT EXISTS node_leases (
            id TEXT PRIMARY KEY,
            graph_id TEXT NOT NULL,
            work_node_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            state TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            released_at TEXT,
            FOREIGN KEY(node_id) REFERENCES nodes(id)
        );
        CREATE INDEX IF NOT EXISTS ix_node_leases_node ON node_leases(node_id);
        CREATE INDEX IF NOT EXISTS ix_node_leases_work_node ON node_leases(work_node_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_active_work_node_lease
            ON node_leases(work_node_id)
            WHERE state='active';

        CREATE TABLE IF NOT EXISTS transfers (
            id TEXT PRIMARY KEY,
            graph_id TEXT,
            work_node_id TEXT,
            node_id TEXT,
            direction TEXT NOT NULL,
            source_path TEXT NOT NULL,
            destination_path TEXT NOT NULL,
            manifest_digest TEXT NOT NULL,
            artifact_digest TEXT,
            status TEXT NOT NULL,
            receipt_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(node_id) REFERENCES nodes(id)
        );
        CREATE INDEX IF NOT EXISTS ix_transfers_graph_node ON transfers(graph_id, work_node_id);
        CREATE INDEX IF NOT EXISTS ix_transfers_node ON transfers(node_id);
        CREATE INDEX IF NOT EXISTS ix_transfers_status ON transfers(status);
        """
    )
    _ensure_column(conn, "memory_records", "tags_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(
        conn,
        "work_nodes",
        "placement_json",
        "TEXT NOT NULL DEFAULT '{\"mode\":\"local\",\"node_id\":null}'",
    )
    for table in (
        "contradictions",
        "evidence_reviews",
        "team_assignments",
        "execution_steps",
        "team_runs",
        "missions",
        "capability_benchmarks",
        "evaluator_runs",
        "codec_profiles",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {table}")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
