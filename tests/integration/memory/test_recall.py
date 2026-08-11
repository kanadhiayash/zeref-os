from __future__ import annotations

from shiroe.memory.models import MemoryWrite
from shiroe.memory.recall import recall
from shiroe.memory.service import MemoryService


def test_write_then_recall_same_process(tmp_path):
    svc = MemoryService(tmp_path)
    svc.write(
        MemoryWrite(
            kind="decision",
            title="Limiter",
            claim="Use in-process limiter",
            source_refs=("user-input",),
        )
    )

    result = recall(tmp_path, "in-process limiter")

    assert result.abstained is False
    assert result.hits[0].record.claim == "Use in-process limiter"
