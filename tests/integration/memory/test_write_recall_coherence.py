from __future__ import annotations

from shiroe.memory.models import MemoryWrite
from shiroe.memory.service import MemoryService


def test_canonical_write_does_not_create_flat_atom_jsonl(tmp_path):
    svc = MemoryService(tmp_path)

    record = svc.write(
        MemoryWrite(
            kind="decision",
            title="Limiter",
            claim="Use in-process limiter",
            source_refs=("user-input",),
            privacy_class="internal",
            evidence_grade="C",
        )
    )

    assert svc.get(record.id).claim == "Use in-process limiter"
    assert not (tmp_path / "memory" / "l1_atoms" / "decisions.jsonl").exists()
