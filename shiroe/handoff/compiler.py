"""Compile handoff artifacts from canonical Shiroe state.

privacy-audit: allow-file "Handoff compiler references provenance fields and generated artifacts; no real user data."
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiroe.handoff.schema import HandoffPacket
from shiroe.lock import MemoryLock, atomic_write
from shiroe.memory.models import MemoryRecord
from shiroe.memory.service import MemoryService
from shiroe.privacy import scrub
from shiroe.storage.state import StateDB


TARGETS = {"codex", "claude", "cursor", "github", "human"}


def compile_handoff(
    root: Path | str = Path("."),
    *,
    target: str,
    graph_id: str | None = None,
    objective: str = "Continue from current Shiroe memory state.",
    include_private: bool = False,
) -> dict[str, Any]:
    """Compile a canonical-state handoff and write JSON/Markdown artifacts.

    The machine packet is assembled from SQLite Work Graph, approval, memory,
    and verification state. Generated Markdown memory views are never read.
    """

    if target not in TARGETS:
        raise ValueError(f"unsupported handoff target: {target}")
    root_path = Path(root)
    service = MemoryService(root_path)
    all_records = list(service.list(statuses=("active",)))
    records, excluded_atoms = _filter_exportable_records(
        all_records,
        target=target,
        include_private=include_private,
    )
    if include_private:
        _log_private_export(root_path, target=target, records=records)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    redact_path = root_path / "REDACT.md"
    objective_clean, objective_report = scrub(
        objective,
        redact_path,
        provenance=f"handoff/{target}/objective",
    )
    packet = _compile_packet(
        root_path,
        graph_id=graph_id,
        records=records,
        objective=objective_clean,
        generated_at=generated_at,
        redact_path=redact_path,
    )
    packet_dict = packet.to_dict()
    legacy_payload, record_redactions = _legacy_payload(
        target=target,
        objective=objective_clean,
        records=records,
        packet=packet,
        redact_path=redact_path,
    )
    field_redactions = objective_report.redacted + record_redactions
    artifact_payload = {
        "target": target,
        "objective": objective_clean,
        "schema": packet.schema,
        "packet": packet_dict,
        **legacy_payload,
    }
    markdown = _render_markdown(target, objective_clean, packet)
    json_text = json.dumps(artifact_payload, indent=2, sort_keys=True) + "\n"

    out_dir = root_path / "memory" / "handoffs"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    basename = f"{target}-{ts}"
    md_path = out_dir / f"{basename}.md"
    json_path = out_dir / f"{basename}.json"
    with MemoryLock(root_path / "memory"):
        atomic_write(md_path, markdown)
        atomic_write(json_path, json_text)
    return {
        "target": target,
        "markdown": str(md_path),
        "json": str(json_path),
        "packet": packet_dict,
        "privacy": {
            "field_redactions": field_redactions,
            "include_private": include_private,
            "excluded_atoms": excluded_atoms,
        },
        "summary": legacy_payload["current_state"],
    }


def _compile_packet(
    root: Path,
    *,
    graph_id: str | None,
    records: list[MemoryRecord],
    objective: str,
    generated_at: str,
    redact_path: Path,
) -> HandoffPacket:
    graph = _graph(root, graph_id)
    pending_nodes = _pending_nodes(root, graph_id)
    pending_approvals = _pending_approvals(root, graph_id)
    active_decisions = tuple(
        _record_brief(record, redact_path)[0]
        for record in records
        if record.kind == "decision"
    )
    open_risks = tuple(
        _record_brief(record, redact_path)[0]
        for record in records
        if record.kind in {"risk", "contradiction"}
    )
    relevant_files = sorted(
        set(
            _node_files(pending_nodes)
            + _memory_files(active_decisions)
            + _memory_files(open_risks)
        )
    )
    next_actions = tuple(
        node["objective"] for node in pending_nodes[:5]
    ) or ("Run targeted verification before continuing.",)
    verification = _verification(root, graph_id)
    if not graph and objective:
        graph = {"id": graph_id, "objective": objective, "version": None, "status": "unknown"}
    return HandoffPacket(
        schema="shiroe.handoff/v1",
        graph=graph,
        pending_nodes=tuple(pending_nodes),
        pending_approvals=tuple(pending_approvals),
        active_decisions=active_decisions,
        open_risks=open_risks,
        verification=tuple(verification),
        relevant_files=tuple(relevant_files),
        next_actions=tuple(next_actions),
        generated_at=generated_at,
    )


def _filter_exportable_records(
    records: list[MemoryRecord],
    *,
    target: str,
    include_private: bool,
) -> tuple[list[MemoryRecord], dict[str, int]]:
    if include_private:
        allowed = {"public", "internal", "confidential"}
    elif target == "human":
        allowed = {"public", "internal"}
    else:
        allowed = {"public"}
    exportable: list[MemoryRecord] = []
    excluded: dict[str, int] = {}
    for record in records:
        privacy = (
            record.privacy_class
            if record.privacy_class in {"public", "internal", "confidential", "restricted"}
            else "internal"
        )
        if privacy in allowed:
            exportable.append(record)
        else:
            excluded[privacy] = excluded.get(privacy, 0) + 1
    return exportable, excluded


def _log_private_export(root_path: Path, *, target: str, records: list[MemoryRecord]) -> None:
    from shiroe.audit.logger import AuditLogger

    private_ids = [
        record.id for record in records
        if record.privacy_class in ("internal", "confidential")
        or record.privacy_class not in ("public", "internal", "confidential", "restricted")
    ]
    AuditLogger.from_root(root_path).append(
        event_type="redaction",
        status="override",
        reason=f"handoff compiled with include_private=True for target '{target}'",
        guards_run=["handoff_privacy_filter"],
        payload={
            "target": target,
            "private_atoms_included": len(private_ids),
            "private_atom_ids": private_ids,
        },
    )


def _graph(root: Path, graph_id: str | None) -> dict[str, Any]:
    if not graph_id:
        return {}
    from shiroe.work.store import WorkStore

    store = WorkStore(root)
    try:
        graph = store.get(graph_id)
    finally:
        store.close()
    return {
        "id": graph.id,
        "objective": graph.objective,
        "status": graph.status.value,
        "version": graph.version,
        "constraints": list(graph.constraints),
        "success_criteria": list(graph.success_criteria),
    }


def _pending_nodes(root: Path, graph_id: str | None) -> list[dict[str, Any]]:
    if not graph_id:
        return []
    db = StateDB(root)
    conn = db.connect()
    db.migrate()
    try:
        rows = conn.execute(
            """
            SELECT id, kind, objective, requires_json, risk, approval_required,
                   independent_review, evidence_required, metadata_json, status,
                   state_version
            FROM work_nodes
            WHERE graph_id=? AND status NOT IN ('completed', 'skipped')
            ORDER BY id
            """,
            (graph_id,),
        ).fetchall()
    finally:
        db.close()
    return [
        {
            "id": row[0],
            "kind": row[1],
            "objective": row[2],
            "requires": json.loads(row[3] or "[]"),
            "risk": row[4],
            "approval_required": bool(row[5]),
            "independent_review": bool(row[6]),
            "evidence_required": bool(row[7]),
            "metadata": json.loads(row[8] or "{}"),
            "status": row[9],
            "state_version": int(row[10]),
        }
        for row in rows
    ]


def _pending_approvals(root: Path, graph_id: str | None) -> list[dict[str, Any]]:
    db = StateDB(root)
    conn = db.connect()
    db.migrate()
    params: tuple[object, ...]
    where = "status='pending'"
    params = ()
    if graph_id:
        where += " AND graph_id=?"
        params = (graph_id,)
    try:
        rows = conn.execute(
            f"""
            SELECT id, graph_id, node_id, approval_type, action_kind,
                   requested_action, scope_json, scope_digest, reason,
                   options_json, evidence_refs_json, risk, requested_at
            FROM approval_requests
            WHERE {where}
            ORDER BY requested_at DESC, id ASC
            """,
            params,
        ).fetchall()
    finally:
        db.close()
    return [
        {
            "id": row[0],
            "graph_id": row[1],
            "node_id": row[2],
            "approval_type": row[3],
            "action_kind": row[4],
            "requested_action": row[5],
            "scope": json.loads(row[6] or "{}"),
            "scope_digest": row[7],
            "reason": row[8],
            "options": json.loads(row[9] or "[]"),
            "evidence_refs": json.loads(row[10] or "[]"),
            "risk": row[11],
            "requested_at": row[12],
        }
        for row in rows
    ]


def _verification(root: Path, graph_id: str | None) -> list[dict[str, Any]]:
    db = StateDB(root)
    conn = db.connect()
    db.migrate()
    checks: list[dict[str, Any]] = []
    try:
        if graph_id:
            row = conn.execute(
                "SELECT COUNT(*) FROM work_nodes WHERE graph_id=? AND status='blocked'",
                (graph_id,),
            ).fetchone()
            blocked = int(row[0]) if row else 0
            checks.append({
                "name": "work_graph_blockers",
                "status": "block" if blocked else "pass",
                "blocked_nodes": blocked,
            })
    finally:
        db.close()
    return checks


def _legacy_payload(
    *,
    target: str,
    objective: str,
    records: list[MemoryRecord],
    packet: HandoffPacket,
    redact_path: Path,
) -> tuple[dict[str, Any], int]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    redactions = 0
    relevant_files = list(packet.relevant_files)
    for record in records:
        brief, count = _record_brief(record, redact_path)
        redactions += count
        by_type.setdefault(record.kind, []).append(brief)
        if brief["source_type"] == "file":
            relevant_files.append(brief["source"])
    open_contradictions = by_type.get("contradiction", [])
    return {
        "current_state": {
            "active_records": len(records),
            "health_passed": not open_contradictions,
            "open_contradictions": len(open_contradictions),
            "graph_id": packet.graph.get("id"),
            "pending_nodes": len(packet.pending_nodes),
            "pending_approvals": len(packet.pending_approvals),
        },
        "known_facts": by_type.get("fact", []),
        "active_decisions": by_type.get("decision", []),
        "open_risks": by_type.get("risk", []),
        "open_contradictions": open_contradictions,
        "relevant_files": sorted(set(relevant_files)),
        "do_not_touch": ["generated memory views are projections, not authority"],
        "next_steps": list(packet.next_actions),
        "verification_checklist": [
            "python3 -m pytest -q",
            "python3 -m shiroe doctor --json",
        ],
        "memory_health_summary": {
            "active_records": len(records),
            "open_contradictions": len(open_contradictions),
            "target": target,
            "objective": objective,
        },
    }, redactions


def _record_brief(record: MemoryRecord, redact_path: Path) -> tuple[dict[str, Any], int]:
    source_value = record.source_refs[0] if record.source_refs else ""
    claim, claim_report = scrub(record.claim, redact_path, provenance=f"handoff/memory/{record.id}/claim")
    summary, summary_report = scrub(record.summary, redact_path, provenance=f"handoff/memory/{record.id}/summary")
    source, source_report = scrub(source_value, redact_path, provenance=f"handoff/memory/{record.id}/source")
    return {
        "id": record.id,
        "kind": record.kind,
        "title": record.title,
        "claim": claim,
        "summary": summary,
        "source": source,
        "source_refs": list(record.source_refs),
        "source_type": "file" if source and not source.startswith(("http://", "https://")) else "user",
        "evidence": record.evidence_grade,
        "status": record.status,
    }, claim_report.redacted + summary_report.redacted + source_report.redacted


def _node_files(nodes: list[dict[str, Any]]) -> list[str]:
    files: list[str] = []
    for node in nodes:
        metadata = node.get("metadata") or {}
        raw_files = metadata.get("files") or ()
        if isinstance(raw_files, str):
            files.append(raw_files)
        else:
            files.extend(str(item) for item in raw_files)
    return files


def _memory_files(records: tuple[dict, ...]) -> list[str]:
    files: list[str] = []
    for record in records:
        for source in record.get("source_refs", ()):
            if source and not str(source).startswith(("http://", "https://")):
                files.append(str(source))
    return files


def _render_markdown(target: str, objective: str, packet: HandoffPacket) -> str:
    lines = [
        f"# {target.title()} Handoff",
        "",
        "## Objective",
        "",
        objective,
        "",
        "## Graph",
        "",
        f"- id: {packet.graph.get('id') or 'none'}",
        f"- status: {packet.graph.get('status') or 'unknown'}",
        f"- version: {packet.graph.get('version') or 'unknown'}",
    ]
    _extend_items(lines, "Pending Nodes", packet.pending_nodes)
    _extend_items(lines, "Pending Approvals", packet.pending_approvals)
    _extend_items(lines, "Active Decisions", packet.active_decisions)
    _extend_items(lines, "Open Risks", packet.open_risks)
    _extend_items(lines, "Verification", packet.verification)
    _extend_items(lines, "Relevant Files", packet.relevant_files)
    _extend_items(lines, "Next Actions", packet.next_actions)
    return "\n".join(lines).rstrip() + "\n"


def _extend_items(lines: list[str], title: str, items: tuple[Any, ...]) -> None:
    lines.extend(["", f"## {title}", ""])
    if not items:
        lines.append("- none")
        return
    for item in items:
        if isinstance(item, dict):
            label = item.get("objective") or item.get("requested_action") or item.get("claim") or item.get("name") or item.get("id")
            detail = item.get("id") or item.get("status") or ""
            lines.append(f"- {label} ({detail})" if detail else f"- {label}")
        else:
            lines.append(f"- {item}")
