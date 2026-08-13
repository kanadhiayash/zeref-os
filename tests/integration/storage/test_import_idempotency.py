"""H3.3: import idempotency and interruption safety.

Two invariants:
  1. Running run_import twice on the same source produces zero new
     canonical records the second time -- every atom is deduped by
     (source_type, source_ref, content_hash).
  2. Malformed source input (invalid JSON line, missing fields) cannot
     partially masquerade as success: valid lines around it still
     import, the malformed line is silently skipped, and the record
     count reflects only well-formed input.
"""

from __future__ import annotations

import json

from shiroe.storage import StateDB
from shiroe.storage.importer import run_import


def _atom_dir(tmp_path):
    d = tmp_path / "memory" / "l1_atoms"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_count(tmp_path) -> int:
    db = StateDB(tmp_path)
    db.migrate()
    conn = db.connect()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0])
    finally:
        db.close()


def _seed_valid_atoms(tmp_path, count: int = 3, filename: str = "seed.jsonl"):
    d = _atom_dir(tmp_path)
    lines = [
        json.dumps({"type": "fact", "title": f"t{i}", "claim": f"c{i}"})
        for i in range(count)
    ]
    (d / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_dry_run_does_not_touch_canonical_state(tmp_path):
    _seed_valid_atoms(tmp_path, count=3)
    manifest = run_import(tmp_path, dry_run=True)
    assert manifest.dry_run is True
    assert manifest.records_written == 3
    assert _record_count(tmp_path) == 0


def test_second_import_creates_zero_new_records(tmp_path):
    _seed_valid_atoms(tmp_path, count=3)

    first = run_import(tmp_path, dry_run=False)
    assert first.records_written == 3
    assert first.records_skipped_duplicate == 0
    assert _record_count(tmp_path) == 3

    second = run_import(tmp_path, dry_run=False)
    assert second.records_written == 0
    assert second.records_skipped_duplicate == 3
    assert _record_count(tmp_path) == 3


def test_third_import_stays_stable(tmp_path):
    """Convergence: N repeated imports plateau at the same row count."""
    _seed_valid_atoms(tmp_path, count=5)
    for _ in range(3):
        run_import(tmp_path, dry_run=False)
    assert _record_count(tmp_path) == 5


def test_malformed_line_does_not_partially_masquerade_as_success(tmp_path):
    d = _atom_dir(tmp_path)
    lines = [
        json.dumps({"type": "fact", "title": "good1", "claim": "c1"}),
        "{ NOT VALID JSON HERE",
        json.dumps({"type": "fact", "title": "good2", "claim": "c2"}),
    ]
    (d / "mixed.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = run_import(tmp_path, dry_run=False)

    # Only well-formed lines produce records; malformed line is skipped
    # cleanly (no half-written row, no crash).
    assert manifest.records_written == 2
    assert _record_count(tmp_path) == 2


def test_missing_source_directory_imports_nothing_without_error(tmp_path):
    # No memory/l1_atoms directory at all -- importer must not crash.
    manifest = run_import(tmp_path, dry_run=False)
    assert manifest.records_written == 0
    assert _record_count(tmp_path) == 0
