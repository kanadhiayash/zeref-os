"""Canonical memory recall and search explanation."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from shiroe.memory.models import RecallResult
from shiroe.memory.service import MemoryService


def recall(
    root: Path | str,
    query: str,
    *,
    limit: int = 5,
    atom_type: str | None = None,
    status: str | None = "active",
) -> RecallResult:
    statuses = (status,) if status else ("active", "superseded", "archived", "disputed", "stale")
    kinds = (atom_type,) if atom_type else None
    result = MemoryService(root).search(query, limit=limit, kinds=kinds, statuses=statuses)
    evidence_refs = tuple(
        ref
        for hit in result.hits
        for ref in hit.record.source_refs
    )
    return RecallResult(
        query=query,
        hits=result.hits,
        evidence_refs=evidence_refs,
        open_contradictions=(),
    )


def recall_to_dict(result: RecallResult) -> dict[str, Any]:
    top = result.hits[0].record if result.hits else None
    return {
        "query": result.query,
        "answer": top.summary or top.claim if top else "No matching memory record found.",
        "matched_atoms": [
            {
                "atom": _record_to_legacy_atom(hit.record),
                "score": hit.score,
                "why": hit.why,
            }
            for hit in result.hits
        ],
        "hits": [
            {
                "record": asdict(hit.record),
                "score": hit.score,
                "why": hit.why,
            }
            for hit in result.hits
        ],
        "evidence_grade": top.evidence_grade if top else "unverified",
        "evidence_refs": list(result.evidence_refs),
        "source": "sqlite",
        "open_contradictions": [asdict(record) for record in result.open_contradictions],
        "abstained": result.abstained,
    }


def recall_to_legacy_dict(result: RecallResult) -> dict[str, Any]:
    return recall_to_dict(result)


def explain_search(
    root: Path | str,
    query: str,
    *,
    limit: int = 3,
    atom_type: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    statuses = (status,) if status else ("active", "superseded", "archived", "disputed", "stale")
    kinds = (atom_type,) if atom_type else None
    result = MemoryService(root).search(query, limit=limit, kinds=kinds, statuses=statuses)
    return {
        "query": query,
        "tokens": list(result.tokens),
        "source": result.source,
        "candidates": [
            {
                "id": hit.record.id,
                "type": hit.record.kind,
                "status": hit.record.status,
                "score": hit.score,
                "why_selected": hit.why,
                "claim": hit.record.claim,
                "evidence": hit.record.evidence_grade,
            }
            for hit in result.hits
        ],
    }


def _record_to_legacy_atom(record) -> dict[str, Any]:
    return {
        "id": record.id,
        "type": record.kind,
        "claim": record.claim,
        "summary": record.summary or record.claim,
        "source": ",".join(record.source_refs),
        "source_type": "user",
        "evidence": record.evidence_grade,
        "confidence": record.confidence,
        "status": record.status,
        "created_at": record.created_at,
        "observed_at": None,
        "last_confirmed_at": None,
        "valid_from": record.valid_from,
        "valid_until": record.valid_until,
        "recorded_at": record.created_at,
        "superseded_at": None,
        "entities": [],
        "tags": list(record.tags),
        "links": [],
        "privacy": record.privacy_class,
        "provenance": record.owner,
    }
