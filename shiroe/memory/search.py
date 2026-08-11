"""Deterministic canonical memory search.

Search is intentionally one path: SQLite rows from ``MemoryService`` scored by
unique token overlap. There is no index rebuild, ranking backend switch, query
expansion, or generated-markdown fallback.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from shiroe.memory.models import SearchHit, SearchResult
from shiroe.memory.service import MemoryService


def _tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return tuple(dict.fromkeys(re.findall(r"\w+", normalized, flags=re.UNICODE)))


def tokenize(text: str) -> list[str]:
    """Compatibility wrapper for callers that still inspect tokenization."""
    return list(_tokens(text))


def _overlap_score(query_tokens: set[str], candidate: str) -> int:
    return len(query_tokens & set(_tokens(candidate)))


def _candidate_text(record) -> str:
    return " ".join(
        part
        for part in (
            record.title,
            record.claim,
            record.summary,
            " ".join(record.tags),
        )
        if part
    )


def search_memory(
    root: Path | str,
    query: str,
    *,
    limit: int = 10,
    kinds: tuple[str, ...] | list[str] | None = None,
    statuses: tuple[str, ...] | list[str] = ("active",),
    as_of: str | None = None,
) -> SearchResult:
    query_tokens = set(_tokens(query))
    if not query_tokens or limit <= 0:
        return SearchResult(query=query, tokens=tuple(query_tokens), hits=(), abstained=True)

    svc = MemoryService(root)
    records = svc.list(kinds=kinds, statuses=statuses, include_archived=False)
    hits: list[tuple[int, str, str, SearchHit]] = []
    for record in records:
        score = _overlap_score(query_tokens, _candidate_text(record))
        if score <= 0:
            continue
        # Currentness/status ordering is mostly enforced by the default status
        # filter. Keep this explicit key for future callers that intentionally
        # include superseded or archived rows.
        current_rank = "0" if record.status == "active" and not record.archived else "1"
        hits.append(
            (
                -score,
                current_rank,
                _reverse_timestamp(record.updated_at),
                SearchHit(
                    record=record,
                    score=score,
                    why=f"{score} unique query token(s) overlapped canonical memory text",
                ),
            )
        )
    hits.sort(key=lambda item: (item[1], item[0], item[2], item[3].record.id))
    selected = tuple(item[3] for item in hits[:limit])
    return SearchResult(
        query=query,
        tokens=tuple(query_tokens),
        hits=selected,
        abstained=not selected,
    )


def search_atoms(
    root: Path | str,
    query: str,
    *,
    limit: int = 10,
    atom_type: str | None = None,
    status: str | None = "active",
    as_of: str | None = None,
    expand: bool = False,
) -> dict:
    """Temporary compatibility shim for pre-Phase-05 CLI callers.

    Returns the old dict shape from canonical memory rows only. The shim exists
    while recall/CLI/handoff are migrated, not as a second backend.
    """
    statuses = (status,) if status else ("active", "superseded", "archived", "disputed", "stale")
    kinds = (atom_type,) if atom_type else None
    result = search_memory(root, query, limit=limit, kinds=kinds, statuses=statuses, as_of=as_of)
    return {
        "query": query,
        "tokens": list(result.tokens),
        "source": result.source,
        "abstained": result.abstained,
        "matches": [
            {
                "atom": _record_to_legacy_atom(hit.record),
                "score": hit.score,
                "matched_via": "canonical",
                "why": hit.why,
            }
            for hit in result.hits
        ],
        "expansion": {"tokens": [], "added": []},
    }


def _record_to_legacy_atom(record) -> dict:
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


def _reverse_timestamp(value: str) -> str:
    # ISO-8601 strings sort chronologically ascending. Invert digits to make
    # newer timestamps sort first without depending on datetime parsing.
    table = str.maketrans("0123456789", "9876543210")
    return value.translate(table)
