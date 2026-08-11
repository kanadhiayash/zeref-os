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


def _reverse_timestamp(value: str) -> str:
    # ISO-8601 strings sort chronologically ascending. Invert digits to make
    # newer timestamps sort first without depending on datetime parsing.
    table = str.maketrans("0123456789", "9876543210")
    return value.translate(table)
