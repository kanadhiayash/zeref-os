from __future__ import annotations

from shiroe.memory.models import MemoryWrite
from shiroe.memory.service import MemoryService
from shiroe.memory.views import render_views


def test_generated_views_can_be_deleted_and_rebuilt(tmp_path):
    MemoryService(tmp_path).write(
        MemoryWrite(
            kind="decision",
            title="Canonical state",
            claim="Use canonical state",
            source_refs=("user-input",),
            privacy_class="internal",
            evidence_grade="C",
        )
    )
    paths = render_views(tmp_path)
    for path in paths:
        path.unlink()

    rebuilt = render_views(tmp_path)

    assert rebuilt
    assert "Use canonical state" in (tmp_path / "memory/views/decisions.md").read_text()
