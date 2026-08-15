"""Shared CLI helpers."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any


def project_root() -> Path:
    from shiroe.memory import discover_project_root

    return discover_project_root()


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def record_payload(record) -> dict[str, Any]:
    data = asdict(record)
    data["type"] = record.kind
    data["evidence"] = record.evidence_grade
    data["privacy"] = record.privacy_class
    data["tags"] = list(record.tags)
    return data


def memory_write_from_payload(payload: dict[str, Any]):
    from shiroe.memory.models import MemoryWrite

    return MemoryWrite(
        kind=str(payload.get("kind") or payload.get("type") or "note"),
        title=str(payload.get("title") or payload.get("claim") or "Memory"),
        claim=str(payload.get("claim") or payload.get("body") or ""),
        summary=str(payload.get("summary") or ""),
        source_refs=tuple(str(ref) for ref in (payload.get("source_refs") or payload.get("sources") or ["user-input"])),
        confidence=str(payload.get("confidence") or "unknown"),
        evidence_grade=str(payload.get("evidence_grade") or payload.get("evidence") or ""),
        privacy_class=str(payload.get("privacy_class") or payload.get("privacy") or "internal"),
        tags=tuple(str(tag) for tag in (payload.get("tags") or ())),
    )


def report_payload(report) -> dict[str, Any]:
    return asdict(report)
