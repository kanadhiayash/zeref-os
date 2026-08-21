"""Domain projection dispatcher (ADR-0001 extended beyond memory).

``storage.records.apply_event`` proved the pattern for memory: one reducer,
called by both the live write path and replay, so the two can never drift
apart. This module generalizes that pattern to the other domains that live
in canonical event history -- capabilities, approvals, and the work-graph
projection -- by routing each event to its domain's reducer by
``event_type`` prefix.

The capability/approval/work reducers below are intentionally partial: only
the event types whose emission side already exists, or is defined by the
next tranche's payload contract, are implemented. Every other event type in
a supported prefix is a safe no-op (returns without mutation) so that wiring
up its emitter later needs no change here.
"""

from __future__ import annotations

import json
import sqlite3

from shiroe.storage.records import apply_event as _apply_memory_event


SUPPORTED_DOMAINS: frozenset[str] = frozenset(
    {"memory", "capabilities", "approvals", "work_projection"}
)


def _dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def apply_event(conn: sqlite3.Connection, env: dict) -> set[str]:
    """Dispatch one canonical event to every relevant domain projection.

    Routes by ``event_type`` prefix to the domain reducer, which does not
    open its own transaction or emit new events -- it only folds the given
    envelope into that domain's current-state tables. Returns the set of
    domain names actually touched, for replay reporting.
    """
    event_type = env.get("event_type") or ""

    if event_type.startswith("memory."):
        return {"memory"} if _apply_memory_event(conn, env) else set()

    if event_type.startswith("capability."):
        return {"capabilities"} if _apply_capability(conn, env) else set()

    if event_type.startswith("approval."):
        return {"approvals"} if _apply_approval(conn, env) else set()

    if event_type.startswith(("run.", "step.", "node.", "transfer.")):
        return {"work_projection"} if _apply_work(conn, env) else set()

    return set()


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

def _apply_capability(conn: sqlite3.Connection, env: dict) -> bool:
    """Fold capability events into ``capabilities``/``capability_versions``/
    ``capability_permissions``.

    Only ``capability.discovered`` is implemented -- the one event type whose
    full-snapshot payload contract is fixed by source-plan A3 (id, name,
    type, digest, version_id, version, manifest, source_kind,
    source_location, permissions, event_time). Older/incomplete
    ``capability.discovered`` events (today's emitter only carries path +
    digest) are recognised and safely skipped rather than crashing replay.
    Other capability.* event types (quarantined, approved, ...) are no-ops
    here until Steps 3-5 define their reducer-facing payloads.
    """
    payload = env.get("payload") or {}
    if env.get("event_type") != "capability.discovered":
        return False

    required = (
        "id", "name", "type", "digest", "version_id", "version",
        "manifest", "source_kind", "source_location",
    )
    if any(payload.get(field) is None for field in required):
        return False

    when = payload.get("event_time") or env.get("timestamp")
    manifest = payload["manifest"]
    manifest_json = manifest if isinstance(manifest, str) else _dumps(manifest)
    lifecycle = payload.get("lifecycle", "quarantined")

    conn.execute(
        """
        INSERT OR REPLACE INTO capabilities
            (id, name, type, lifecycle, current_digest, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (payload["id"], payload["name"], payload["type"], lifecycle,
         payload["digest"], when, when),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO capability_versions
            (id, capability_id, version, digest, manifest, source_kind,
             source_location, license, adapter, compatibility, lifecycle,
             created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["version_id"], payload["id"], payload["version"],
            payload["digest"], manifest_json, payload["source_kind"],
            payload["source_location"], payload.get("license"),
            payload.get("adapter"),
            _dumps(payload["compatibility"]) if payload.get("compatibility") else None,
            lifecycle, when,
        ),
    )

    permissions = payload.get("permissions")
    if permissions:
        conn.execute(
            """
            INSERT OR REPLACE INTO capability_permissions
                (id, capability_id, filesystem_read, filesystem_write,
                 network, secrets, subprocess, external_write, destructive,
                 approved_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                permissions.get("id") or f"{payload['id']}_perm",
                payload["id"],
                _dumps(permissions.get("filesystem_read", [])),
                _dumps(permissions.get("filesystem_write", [])),
                _dumps(permissions.get("network", "none")),
                _dumps(permissions.get("secrets", [])),
                1 if permissions.get("subprocess") else 0,
                1 if permissions.get("external_write") else 0,
                1 if permissions.get("destructive") else 0,
                permissions.get("approved_at"),
                permissions.get("approved_by"),
            ),
        )
    return True


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

def _apply_approval(conn: sqlite3.Connection, env: dict) -> bool:
    """Fold approval events into ``approval_requests``.

    Implements the three event types source-plan A4 defines payload
    contracts for (``approval.requested``, ``approval.decided``,
    ``approval.staled``). ``ApprovalService`` does not emit these yet
    (Step 4's job); this reducer is written against A4's declared shape so
    that wiring the emitter later needs no change here.
    """
    payload = env.get("payload") or {}
    event_type = env.get("event_type")

    if event_type == "approval.requested":
        required = (
            "id", "approval_type", "requested_action", "scope",
            "scope_digest", "reason", "risk", "status", "requested_at",
        )
        if any(payload.get(field) is None for field in required):
            return False
        conn.execute(
            """
            INSERT OR REPLACE INTO approval_requests
                (id, graph_id, node_id, approval_type, action_kind,
                 requested_action, scope_json, scope_digest, reason,
                 options_json, evidence_refs_json, risk, status,
                 requested_at, decided_at, decided_by, decision_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"], payload.get("graph_id"), payload.get("node_id"),
                payload["approval_type"], payload.get("action_kind"),
                payload["requested_action"], _dumps(payload["scope"]),
                payload["scope_digest"], payload["reason"],
                _dumps(payload.get("options", [])),
                _dumps(payload.get("evidence_refs", [])),
                payload["risk"], payload["status"], payload["requested_at"],
                None, None, None,
            ),
        )
        return True

    if event_type == "approval.decided":
        required = ("id", "decision", "actor", "reason", "decided_at")
        if any(payload.get(field) is None for field in required):
            return False
        conn.execute(
            """
            UPDATE approval_requests
            SET status=?, decided_at=?, decided_by=?, decision_reason=?
            WHERE id=?
            """,
            (payload["decision"], payload["decided_at"], payload["actor"],
             payload["reason"], payload["id"]),
        )
        return True

    if event_type == "approval.staled":
        if payload.get("id") is None:
            return False
        conn.execute(
            "UPDATE approval_requests SET status=? WHERE id=?",
            ("stale", payload["id"]),
        )
        return True

    return False


# ---------------------------------------------------------------------------
# Work-graph projection
# ---------------------------------------------------------------------------

_RUN_STATUS_EVENTS = frozenset({
    "run.started", "run.paused", "run.resumed",
    "run.completed", "run.failed", "run.cancelled",
})
_STEP_EVENTS = frozenset({"step.started", "step.completed", "step.failed"})


def _apply_work(conn: sqlite3.Connection, env: dict) -> bool:
    """Fold run/step events into the work-graph projection tables.

    ``run.created`` carries the complete compiled graph (source-plan A5) so
    the projection can be rebuilt from JSONL alone. The ``run.*`` lifecycle
    events (started/paused/resumed/completed/failed/cancelled) update
    ``work_graphs.status``; the ``step.*`` events update ``work_nodes``
    (status, state_version, and optionally output_json). Every UPDATE here
    is unconditional (no CAS predicate) so replay stays deterministic --
    each event was already CAS-validated at live-write time by its
    emitter's pre-check. ``node.*`` / ``transfer.*`` events are no-ops
    until their reducer-facing payloads are defined.
    """
    payload = env.get("payload") or {}
    event_type = env.get("event_type")

    if event_type == "run.created":
        return _apply_run_created(conn, payload, env.get("timestamp"))
    if event_type in _RUN_STATUS_EVENTS:
        return _apply_run_status(conn, payload, env.get("timestamp"))
    if event_type in _STEP_EVENTS:
        return _apply_step(conn, payload)
    return False


def _apply_run_created(conn: sqlite3.Connection, payload: dict, env_timestamp: str | None) -> bool:
    required = ("id", "objective", "status", "version", "nodes", "edges")
    if any(payload.get(field) is None for field in required):
        return False

    when = payload.get("event_time") or env_timestamp
    graph_id = payload["id"]

    conn.execute(
        """
        INSERT OR REPLACE INTO work_graphs
            (id, objective, constraints_json, success_criteria_json, status,
             version, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            graph_id, payload["objective"],
            _dumps(payload.get("constraints", [])),
            _dumps(payload.get("success_criteria", [])),
            payload["status"], payload["version"], when, when,
        ),
    )

    for node in payload["nodes"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO work_nodes
                (id, graph_id, kind, objective, requires_json, risk,
                 approval_required, independent_review, evidence_required,
                 expected_outputs_json, retry_json, placement_json,
                 metadata_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node["id"], graph_id, node["kind"], node["objective"],
                _dumps(node.get("requires", [])), node.get("risk", ""),
                1 if node.get("approval_required") else 0,
                1 if node.get("independent_review") else 0,
                1 if node.get("evidence_required") else 0,
                _dumps(node.get("expected_outputs", [])),
                _dumps(node.get("retry", {})),
                _dumps(node.get("placement", {"mode": "local", "node_id": None})),
                _dumps(node.get("metadata", {})),
                node.get("status", "pending"),
            ),
        )

    for edge in payload["edges"]:
        conn.execute(
            "INSERT OR REPLACE INTO work_edges(graph_id, src_id, dst_id) "
            "VALUES (?, ?, ?)",
            (graph_id, edge["src_id"], edge["dst_id"]),
        )

    return True


def _apply_run_status(conn: sqlite3.Connection, payload: dict, env_timestamp: str | None) -> bool:
    graph_id = payload.get("id")
    status = payload.get("status")
    if graph_id is None or status is None:
        return False
    when = payload.get("event_time") or env_timestamp
    conn.execute(
        "UPDATE work_graphs SET status=?, updated_at=COALESCE(?, updated_at) WHERE id=?",
        (status, when, graph_id),
    )
    return True


def _apply_step(conn: sqlite3.Connection, payload: dict) -> bool:
    node_id = payload.get("node_id")
    if node_id is None:
        return False
    to = payload.get("to")
    output = payload.get("output")
    has_output = "output" in payload and output is not None
    if to is not None and has_output:
        conn.execute(
            "UPDATE work_nodes SET status=?, output_json=?, state_version=state_version+1 WHERE id=?",
            (to, _dumps(output), node_id),
        )
    elif to is not None:
        conn.execute(
            "UPDATE work_nodes SET status=?, state_version=state_version+1 WHERE id=?",
            (to, node_id),
        )
    elif has_output:
        conn.execute(
            "UPDATE work_nodes SET output_json=?, state_version=state_version+1 WHERE id=?",
            (_dumps(output), node_id),
        )
    else:
        conn.execute(
            "UPDATE work_nodes SET state_version=state_version+1 WHERE id=?",
            (node_id,),
        )
    return True
