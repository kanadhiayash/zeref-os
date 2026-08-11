from __future__ import annotations

from shiroe.memory.models import MemoryWrite
from shiroe.memory.search import search_memory
from shiroe.memory.service import MemoryService


def test_nfkc_case_normalization(tmp_path):
    MemoryService(tmp_path).write(
        MemoryWrite(
            kind="decision",
            title="Canonical",
            claim="Ｃａｎｏｎｉｃ State",
            source_refs=("user-input",),
            privacy_class="internal",
            evidence_grade="C",
        )
    )

    assert search_memory(tmp_path, "canonical state").hits
