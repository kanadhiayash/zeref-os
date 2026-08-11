"""Audit report generation.

privacy-audit: allow-file "Audit reports document example ISO timestamps + provenance keys as schema; no user data."
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from shiroe.audit.logger import read_audit_events


def audit_report(root: Path, *, since: str = "", format: str = "text") -> str:
    events, corrupt = read_audit_events(root, since=since)
    counts = Counter((event.event_type, event.status) for event in events)

    if format == "json":
        return json.dumps(
            {
                "events": [event.to_dict() for event in events],
                "corrupt": corrupt,
                "counts": {f"{k[0]}:{k[1]}": v for k, v in counts.items()},
            },
            indent=2,
            sort_keys=True,
        )

    lines = ["# Shiroe Audit Report" if format == "md" else "Shiroe Audit Report", ""]
    if since:
        lines.extend([f"Since: {since}", ""])
    lines.extend(
        [
            f"Memory writes accepted: {counts.get(('memory_write', 'accepted'), 0)}",
            f"Memory writes blocked: {counts.get(('memory_write', 'blocked'), 0)}",
            f"Guard failures: {counts.get(('guard_failure', 'blocked'), 0)}",
            f"Route decisions: {sum(v for (event_type, _), v in counts.items() if event_type == 'route_decision')}",
            f"Redactions: {sum(v for (event_type, _), v in counts.items() if event_type == 'redaction')}",
            f"Corrupt JSONL lines: {len(corrupt)}",
        ]
    )
    if corrupt:
        lines.extend(["", "Corrupt entries:"])
        lines.extend(f"- {entry}" for entry in corrupt)
    return "\n".join(lines) + "\n"
