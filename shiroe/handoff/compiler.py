"""Compile privacy-scrubbed handoff artifacts from canonical memory records.

privacy-audit: allow-file "Handoff compiler references example ISO timestamps + provenance fields; no real user data."
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shiroe.lock import MemoryLock, atomic_write
from shiroe.memory.models import MemoryRecord
from shiroe.memory.service import MemoryService
from shiroe.privacy import scrub


TARGETS = {"codex", "claude", "cursor", "github", "human"}

def compile_handoff(
    root: Path | str = Path("."),
    *,
    target: str,
    objective: str = "Continue from current Shiroe memory state.",
    include_private: bool = False,
) -> dict[str, Any]:
    """Compile a scrubbed handoff artifact for `target`.

    Records are filtered by `privacy_class` before anything is rendered: only
    public records are exported by default. Passing include_private=True also
    exports internal and confidential records; restricted records are never
    exported under any flag.
    """
    if target not in TARGETS:
        raise ValueError(f"unsupported handoff target: {target}")
    root_path = Path(root)
    service = MemoryService(root_path)
    all_records = list(service.list(statuses=("active",)))
    records, excluded_atoms = _filter_exportable_records(all_records, include_private=include_private)
    if include_private:
        _log_private_export(root_path, target=target, records=records)
    health = _build_memory_summary(all_records)
    ts = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    basename = f"{target}-{ts}"
    redact_path = root_path / "REDACT.md"
    objective_clean, objective_report = scrub(
        objective,
        redact_path,
        provenance=f"handoff/{target}/objective",
    )
    handoff = _handoff_payload(target, objective_clean, records, health, redact_path)
    field_redactions = objective_report.redacted + handoff.pop("_redactions", 0)
    markdown = _render_markdown(handoff)
    json_text = json.dumps(handoff, indent=2, sort_keys=True) + "\n"

    out_dir = root_path / "memory" / "handoffs"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{basename}.md"
    json_path = out_dir / f"{basename}.json"
    with MemoryLock(root_path / "memory"):
        atomic_write(md_path, markdown)
        atomic_write(json_path, json_text)
    return {
        "target": target,
        "markdown": str(md_path),
        "json": str(json_path),
        "privacy": {
            "field_redactions": field_redactions,
            "include_private": include_private,
            "excluded_atoms": excluded_atoms,
        },
        "summary": handoff["current_state"],
    }


def _filter_exportable_records(
    records: list[MemoryRecord],
    *,
    include_private: bool,
) -> tuple[list[MemoryRecord], dict[str, int]]:
    """Split records into (exportable, excluded-count-by-privacy-class).

    Fails closed: a record with a missing or unrecognized privacy value is
    treated as internal and excluded from default external handoffs.
    """
    allowed = {"public"} if not include_private else {"public", "internal", "confidential"}
    exportable: list[MemoryRecord] = []
    excluded: dict[str, int] = {}
    for record in records:
        privacy = record.privacy_class if record.privacy_class in {"public", "internal", "confidential", "restricted"} else "internal"
        if privacy in allowed:
            exportable.append(record)
        else:
            excluded[privacy] = excluded.get(privacy, 0) + 1
    return exportable, excluded


def _log_private_export(root_path: Path, *, target: str, records: list[MemoryRecord]) -> None:
    """Record an include_private override in the redaction audit log.

    The event is emitted whenever the override flag is used, so the audit
    trail shows the operator's intent even when no private record happened to
    exist at the time.
    """
    from shiroe.audit.logger import AuditLogger

    private_ids = [
        record.id for record in records
        if record.privacy_class in ("internal", "confidential")
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


def _handoff_payload(
    target: str,
    objective: str,
    records: list[MemoryRecord],
    health: dict[str, Any],
    redact_path: Path,
) -> dict[str, Any]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    relevant_files = []
    redactions = 0
    for record in records:
        brief, count = _brief(record, redact_path)
        redactions += count
        by_type.setdefault(record.kind, []).append(brief)
        if brief["source_type"] == "file":
            relevant_files.append(brief["source"])
    return {
        "target": target,
        "objective": objective,
        "current_state": {
            "active_records": len(records),
            "health_passed": health["passed"],
            "open_contradictions": len(health["open_contradictions"]),
        },
        "known_facts": by_type.get("fact", []),
        "active_decisions": by_type.get("decision", []),
        "open_risks": by_type.get("risk", []),
        "open_contradictions": by_type.get("contradiction", []),
        "relevant_files": sorted(set(relevant_files)),
        "do_not_touch": ["legacy memory/*.md unless explicitly rendering views"],
        "next_steps": ["Run recall for targeted context before editing.", "Run focused verification before reporting completion."],
        "verification_checklist": [
            "python3 -m pytest -q",
            "python3 scripts/shiroe-validate.py",
            "python3 -m shiroe.cli --version",
        ],
        "memory_health_summary": health["summary"],
        "_redactions": redactions,
    }


def _brief(record: MemoryRecord, redact_path: Path) -> tuple[dict[str, Any], int]:
    source_value = record.source_refs[0] if record.source_refs else ""
    claim, claim_report = scrub(record.claim, redact_path, provenance=f"handoff/memory/{record.id}/claim")
    summary, summary_report = scrub(record.summary, redact_path, provenance=f"handoff/memory/{record.id}/summary")
    source, source_report = scrub(source_value, redact_path, provenance=f"handoff/memory/{record.id}/source")
    return {
        "id": record.id,
        "claim": claim,
        "summary": summary,
        "source": source,
        "source_type": "file" if source and not source.startswith(("http://", "https://")) else "user",
        "evidence": record.evidence_grade,
        "status": record.status,
    }, claim_report.redacted + summary_report.redacted + source_report.redacted


def _build_memory_summary(records: list[MemoryRecord]) -> dict[str, Any]:
    open_contradictions = [record for record in records if record.kind == "contradiction"]
    return {
        "passed": not open_contradictions,
        "open_contradictions": [record.id for record in open_contradictions],
        "summary": {
            "active_records": len(records),
            "open_contradictions": len(open_contradictions),
        },
    }


def _render_markdown(handoff: dict[str, Any]) -> str:
    lines = [
        f"# {handoff['target'].title()} Handoff",
        "",
        "## Objective",
        "",
        handoff["objective"],
        "",
        "## Current State",
        "",
    ]
    for key, value in handoff["current_state"].items():
        lines.append(f"- {key}: {value}")
    sections = [
        ("Known Facts", "known_facts"),
        ("Active Decisions", "active_decisions"),
        ("Open Risks", "open_risks"),
        ("Open Contradictions", "open_contradictions"),
        ("Relevant Files", "relevant_files"),
        ("Do Not Touch", "do_not_touch"),
        ("Next Steps", "next_steps"),
        ("Verification Checklist", "verification_checklist"),
    ]
    for title, key in sections:
        lines.extend(["", f"## {title}", ""])
        items = handoff[key]
        if not items:
            lines.append("- none")
        for item in items:
            if isinstance(item, dict):
                lines.append(
                    f"- {item['claim']} "
                    f"(id: {item['id']}; evidence: {item['evidence']}; source: {item['source']})"
                )
            else:
                lines.append(f"- {item}")
    lines.extend(["", "## Memory Health Summary", ""])
    for key, value in handoff["memory_health_summary"].items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines).rstrip() + "\n"
