from __future__ import annotations

from shiroe.memory.models import MemoryWrite
from shiroe.memory.search import search_memory
from shiroe.memory.service import MemoryService


def _seed_memory(root, claim):
    return MemoryService(root).write(
        MemoryWrite(
            kind="decision",
            title=claim.split()[0],
            claim=claim,
            source_refs=("user-input",),
            privacy_class="internal",
            evidence_grade="C",
        )
    )


def test_zero_overlap_abstains(tmp_path):
    _seed_memory(tmp_path, claim="Use SQLite for state")

    result = search_memory(tmp_path, "banana telescope")

    assert result.abstained is True
    assert result.hits == ()


def test_more_unique_token_overlap_ranks_first(tmp_path):
    _seed_memory(tmp_path, claim="Use local rate limiter")
    expected = _seed_memory(tmp_path, claim="Use local in-process rate limiter")

    hits = search_memory(tmp_path, "local in-process rate limiter").hits

    assert hits[0].record.id == expected.id


def test_filters_to_active_status_by_default(tmp_path):
    svc = MemoryService(tmp_path)
    old = svc.write(
        MemoryWrite(
            kind="decision",
            title="Limiter",
            claim="Use local in-process rate limiter",
            source_refs=("user-input",),
            evidence_grade="C",
        )
    )
    svc.supersede(old.id)

    assert search_memory(tmp_path, "in-process limiter").abstained is True
