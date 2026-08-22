"""RED gate for runtime-domain event sourcing and replay (Tasks A2, A4, A5, A6).

Proves the storage/replay contract must extend beyond memory:

* ApprovalService.request / decide_human / assert_current must emit
  approval.requested / approval.decided / approval.staled.
* WorkStore.create / set_node_status must emit run.created / step.*.
* EventLog.replay_into must rebuild capability/approval/work-graph
  projections from JSONL alone and return a per-domain report.
* Semantic digest before / after replay must be equal.

Fails on 451a74d because those emissions do not exist and replay only
touches the memory tables. Turns GREEN once Tasks A2/A4/A5/A6 land.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from shiroe.capabilities.store import CapabilityStore
from shiroe.policy.approval_service import ApprovalService
from shiroe.storage import EventEnvelope, EventLog, StateDB
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


def _prepare(tmp_path: Path) -> tuple[sqlite3.Connection, EventLog]:
    (tmp_path / "REDACT.md").write_text("# minimal\n", encoding="utf-8")
    db = StateDB(tmp_path)
    db.migrate()
    conn = db.connect()
    log = EventLog(tmp_path, redact_md=tmp_path / "REDACT.md", mirror_conn=conn)
    return conn, log


def _event_types(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT event_type FROM memory_events ORDER BY timestamp"
        ).fetchall()
    ]


def _domain_digest(conn: sqlite3.Connection) -> dict[str, str]:
    return _digest_queries(conn, (
        (
            "capabilities",
            "SELECT id, name, type, lifecycle, current_digest "
            "FROM capabilities ORDER BY id",
        ),
        (
            "approvals",
            "SELECT id, approval_type, status, scope_digest, decided_by, decision_reason "
            "FROM approval_requests ORDER BY id",
        ),
        (
            "work_graphs",
            "SELECT id, objective, status FROM work_graphs ORDER BY id",
        ),
        (
            "work_nodes",
            "SELECT id, graph_id, status, kind FROM work_nodes ORDER BY graph_id, id",
        ),
        (
            "work_attempts",
            "SELECT graph_id, node_id, attempt, capability_id, state, input_digest, "
            "output_digest, error, usage_json FROM work_attempts "
            "ORDER BY graph_id, node_id, attempt",
        ),
    ))


def _digest_queries(conn: sqlite3.Connection, queries: tuple[tuple[str, str], ...]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for domain, sql in queries:
        rows = conn.execute(sql).fetchall()
        h = hashlib.sha256()
        for row in rows:
            h.update(repr(tuple(row)).encode("utf-8"))
        digests[domain] = h.hexdigest()
    return digests


def _wipe_projections(conn: sqlite3.Connection) -> None:
    for table in (
        "work_attempts",
        "work_edges",
        "work_nodes",
        "work_graphs",
        "approval_advice",
        "approval_requests",
        "capability_permissions",
        "capability_versions",
        "capabilities",
    ):
        try:
            conn.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def test_approval_service_emits_events(tmp_path: Path) -> None:
    conn, _log = _prepare(tmp_path)
    service = ApprovalService(tmp_path)
    try:
        req = service.request(
            approval_type="action",
            requested_action="publish",
            scope={"tag": "v1"},
            reason="test",
            risk="high",
        )
        service.decide_human(
            req.id, decision="approved", actor="human", reason="ok"
        )
        service.assert_current(req.id, current_scope={"tag": "v2"})
    finally:
        service.close()

    types = _event_types(conn)
    assert "approval.requested" in types, types
    assert "approval.decided" in types, types
    assert "approval.staled" in types, types


def test_work_store_emits_run_events(tmp_path: Path) -> None:
    conn, _log = _prepare(tmp_path)
    graph = compile_work_graph(
        {
            "id": "graph_rt",
            "objective": "runtime domain replay",
            "nodes": [
                {"id": "n1", "kind": "task", "objective": "one", "requires": []}
            ],
            "edges": [],
        }
    )
    store = WorkStore(tmp_path)
    try:
        store.create(graph)
    finally:
        store.close()

    types = _event_types(conn)
    assert "run.created" in types, types


def test_semantic_digest_fails_loudly_on_bad_schema_column(tmp_path: Path) -> None:
    conn, _log = _prepare(tmp_path)

    with pytest.raises(sqlite3.OperationalError):
        _digest_queries(conn, (("bad", "SELECT missing_column FROM capabilities"),))


def test_replay_rebuilds_runtime_domains(tmp_path: Path) -> None:
    conn, log = _prepare(tmp_path)

    store = CapabilityStore(tmp_path)
    try:
        store.upsert_capability(
            capability_id="cap.demo",
            name="Demo",
            type_="script",
            lifecycle="active",
            digest="sha256:deadbeef",
            manifest={
                "schema": "shiroe.capability/v1",
                "id": "cap.demo",
                "name": "Demo",
                "type": "script",
                "version": "1.0.0",
                "source": {"kind": "local-file", "location": "./run.py"},
                "entrypoint": {"adapter": "cli", "command": ["./run.py"]},
                "requires": {},
            },
            source_kind="local-file",
            source_location="./run.py",
        )
    finally:
        store.close()

    service = ApprovalService(tmp_path)
    try:
        req = service.request(
            approval_type="action",
            requested_action="approve cap.demo",
            scope={"capability_id": "cap.demo", "digest": "sha256:deadbeef"},
            reason="test",
            risk="low",
        )
        service.decide_human(req.id, decision="approved", actor="human", reason="ok")
    finally:
        service.close()

    graph = compile_work_graph(
        {
            "id": "graph_replay",
            "objective": "replay coverage",
            "nodes": [
                {"id": "n1", "kind": "task", "objective": "one", "requires": []}
            ],
            "edges": [],
        }
    )
    work = WorkStore(tmp_path)
    try:
        work.create(graph)
    finally:
        work.close()

    before = _domain_digest(conn)

    _wipe_projections(conn)
    empty = _domain_digest(conn)
    assert empty != before, "wipe must clear projection state"

    result = log.replay_into(conn)

    assert not isinstance(result, int), (
        "replay_into must return per-domain report dict; got bare int"
    )
    assert isinstance(result, dict), result
    assert "domains" in result, result
    for domain in ("capabilities", "approvals", "work_projection"):
        assert result["domains"].get(domain) == "rebuilt", result

    after = _domain_digest(conn)
    assert after == before, f"semantic digest drift after replay: {before} != {after}"


def test_replay_reports_incomplete_domain_for_legacy_partial_payload(tmp_path: Path) -> None:
    conn, log = _prepare(tmp_path)
    log.append(EventEnvelope(
        event_type="capability.discovered",
        actor="legacy-test",
        target="capability:legacy.partial",
        payload={"path": "./old.py", "digest": "sha256:legacy"},
    ))

    result = log.replay_into(conn)

    assert result["domains"]["capabilities"] == "replay_incomplete"
    assert result["legacy_incomplete"] == ["capabilities"]


def test_replay_applies_capability_lifecycle_and_digest_drift(tmp_path: Path) -> None:
    conn, log = _prepare(tmp_path)

    store = CapabilityStore(tmp_path)
    try:
        store.upsert_capability(
            capability_id="cap.drift",
            name="Drift",
            type_="script",
            lifecycle="quarantined",
            digest="sha256:old",
            manifest={
                "schema": "shiroe.capability/v1",
                "id": "cap.drift",
                "name": "Drift",
                "type": "script",
                "version": "1.0.0",
                "source": {"kind": "local-file", "location": "./run.py"},
                "entrypoint": {"adapter": "cli", "command": ["./run.py"]},
                "requires": {},
            },
            source_kind="local-file",
            source_location="./run.py",
        )
        store.set_lifecycle("cap.drift", "inspected", actor="human")
        store.set_lifecycle("cap.drift", "approved", actor="human")
        store.refresh_digest("cap.drift", "sha256:new")
    finally:
        store.close()

    before = conn.execute(
        "SELECT id, lifecycle, current_digest FROM capabilities ORDER BY id"
    ).fetchall()

    _wipe_projections(conn)
    log.replay_into(conn)

    after = conn.execute(
        "SELECT id, lifecycle, current_digest FROM capabilities ORDER BY id"
    ).fetchall()
    assert after == before
