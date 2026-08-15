from __future__ import annotations

import sqlite3

from shiroe.storage.state import StateDB


def test_node_tables_and_active_lease_unique_index_exist(tmp_path) -> None:
    with StateDB(tmp_path) as db:
        db.migrate()
        conn = db.connect()
        tables = set(db.tables())
        index_sql = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type='index' AND name='uq_active_work_node_lease'
            """
        ).fetchone()

    assert {"nodes", "node_leases"} <= tables
    assert index_sql is not None
    assert "WHERE state='active'" in index_sql[0]


def test_sqlite_rejects_two_active_leases_for_one_work_node(tmp_path) -> None:
    with StateDB(tmp_path) as db:
        db.migrate()
        conn = db.connect()
        conn.execute(
            """
            INSERT INTO nodes(
                id, name, role, transport, transport_host, ssh_user, trusted,
                status, capabilities_json, created_at, updated_at
            ) VALUES (
                'node_a', 'Node A', 'worker', 'tailscale', 'node-a.tailnet.ts.net',
                'shiroe', 1, 'unknown', '[]', '2026-08-15T00:00:00+00:00',
                '2026-08-15T00:00:00+00:00'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO node_leases(
                id, graph_id, work_node_id, node_id, state, acquired_at, expires_at
            ) VALUES (
                'lease_a', 'graph1', 'work1', 'node_a', 'active',
                '2026-08-15T00:00:00+00:00', '2026-08-15T00:01:00+00:00'
            )
            """
        )

        try:
            conn.execute(
                """
                INSERT INTO node_leases(
                    id, graph_id, work_node_id, node_id, state, acquired_at, expires_at
                ) VALUES (
                    'lease_b', 'graph1', 'work1', 'node_a', 'active',
                    '2026-08-15T00:00:01+00:00', '2026-08-15T00:01:00+00:00'
                )
                """
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("second active lease should violate uq_active_work_node_lease")
