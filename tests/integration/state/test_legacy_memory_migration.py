from __future__ import annotations

import json
from pathlib import Path

from shiroe.memory.service import MemoryService
from shiroe.storage.importer import migrate_legacy_memory


def _seed_legacy_atom(root: Path) -> Path:
    path = root / "memory" / "l1_atoms" / "decisions.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "id": "legacy-decision",
                "type": "decision",
                "title": "Legacy limiter",
                "claim": "legacy limiter remains enforced",
            }
        ) + "\n",
        encoding="utf-8",
    )
    return path


def test_legacy_memory_migrates_without_duplicates(tmp_path: Path) -> None:
    source = _seed_legacy_atom(tmp_path)

    first = migrate_legacy_memory(tmp_path)
    assert first.imported >= 1
    assert str(source.relative_to(tmp_path)) in first.source_digests
    assert MemoryService(tmp_path).search("legacy limiter").hits

    second = migrate_legacy_memory(tmp_path)
    assert second.imported == 0
    assert second.skipped_duplicates >= 1


def test_legacy_memory_archive_moves_sources_after_import(tmp_path: Path) -> None:
    source = _seed_legacy_atom(tmp_path)

    report = migrate_legacy_memory(tmp_path, archive_legacy=True)

    assert report.imported == 1
    assert not source.exists()
    archived = tmp_path / report.archived_sources[0]
    assert archived.exists()
