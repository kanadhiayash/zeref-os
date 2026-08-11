"""m0001 — SQLite v2 canonical state schema (vNext §6.2).

Creates the 17 tables that hold canonical current state for memory,
capabilities, missions, execution, evidence, evaluators, adapters, and
codec profiles. Additive; may not drop or rewrite existing v1 tables
(shiroe.db and shiroe.memory_state own theirs).
"""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    c = conn.executescript

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------
    c(
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
            archived INTEGER NOT NULL DEFAULT 0
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

        CREATE TABLE IF NOT EXISTS contradictions (
            id TEXT PRIMARY KEY,
            side_a TEXT NOT NULL,
            side_b TEXT NOT NULL,
            evidence TEXT,
            state TEXT NOT NULL,
            arbitration TEXT,
            winner TEXT,
            loser TEXT,
            resolution_reason TEXT,
            detected_at TEXT NOT NULL,
            resolved_at TEXT
        );
        """
    )

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------
    c(
        """
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

        CREATE TABLE IF NOT EXISTS capability_benchmarks (
            id TEXT PRIMARY KEY,
            capability_id TEXT NOT NULL,
            suite TEXT NOT NULL,
            dataset TEXT,
            model_or_harness TEXT,
            result_json TEXT NOT NULL,
            mean REAL,
            variance REAL,
            run_at TEXT NOT NULL,
            raw_artifact_ref TEXT,
            FOREIGN KEY(capability_id) REFERENCES capabilities(id)
        );
        CREATE INDEX IF NOT EXISTS ix_capability_benchmarks_cap ON capability_benchmarks(capability_id);
        """
    )

    # ------------------------------------------------------------------
    # Missions / teams / execution
    # ------------------------------------------------------------------
    c(
        """
        CREATE TABLE IF NOT EXISTS missions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL,
            blueprint TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS team_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            mission_id TEXT,
            policy TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            ended_at TEXT,
            cost_usd REAL,
            tokens_input INTEGER,
            tokens_output INTEGER,
            completion_status TEXT,
            result TEXT,
            FOREIGN KEY(mission_id) REFERENCES missions(id)
        );
        CREATE INDEX IF NOT EXISTS ix_team_runs_state ON team_runs(state);

        CREATE TABLE IF NOT EXISTS team_assignments (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            seat_id TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            capability_version_id TEXT NOT NULL,
            score REAL,
            rationale TEXT,
            FOREIGN KEY(run_id) REFERENCES team_runs(id),
            FOREIGN KEY(capability_id) REFERENCES capabilities(id),
            FOREIGN KEY(capability_version_id) REFERENCES capability_versions(id)
        );

        CREATE TABLE IF NOT EXISTS execution_steps (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            dependency_ids TEXT,
            state TEXT NOT NULL,
            retries INTEGER NOT NULL DEFAULT 0,
            timeout_s INTEGER,
            permissions TEXT,
            input_hash TEXT,
            output_hash TEXT,
            started_at TEXT,
            ended_at TEXT,
            FOREIGN KEY(run_id) REFERENCES team_runs(id)
        );
        """
    )

    # ------------------------------------------------------------------
    # Evidence / evaluators
    # ------------------------------------------------------------------
    c(
        """
        CREATE TABLE IF NOT EXISTS evidence_reviews (
            id TEXT PRIMARY KEY,
            memory_id TEXT,
            claim TEXT NOT NULL,
            source_quality_json TEXT NOT NULL,
            review_robustness_json TEXT,
            reviewed_at TEXT NOT NULL,
            reviewer TEXT,
            FOREIGN KEY(memory_id) REFERENCES memory_records(id)
        );

        CREATE TABLE IF NOT EXISTS evaluator_runs (
            id TEXT PRIMARY KEY,
            evaluator TEXT NOT NULL,
            panel_json TEXT,
            provider_metadata_json TEXT,
            independent_outputs_json TEXT,
            dissent_json TEXT,
            verdict TEXT,
            failures TEXT,
            run_at TEXT NOT NULL
        );
        """
    )

    # ------------------------------------------------------------------
    # Adapters / codecs
    # ------------------------------------------------------------------
    c(
        """
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

        CREATE TABLE IF NOT EXISTS codec_profiles (
            id TEXT PRIMARY KEY,
            codec TEXT NOT NULL,
            model_or_harness TEXT NOT NULL,
            data_shape TEXT NOT NULL,
            tokens INTEGER,
            latency_ms INTEGER,
            comprehension REAL,
            parse REAL,
            reliability REAL,
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_codec_profiles_codec ON codec_profiles(codec);
        """
    )
