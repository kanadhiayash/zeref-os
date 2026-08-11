from __future__ import annotations

from shiroe.memory.models import MemoryWrite
import pytest

from shiroe.memory.service import MemoryService


def test_accepted_write_is_immediately_readable(tmp_path):
    svc = MemoryService(tmp_path)

    record = svc.write(
        MemoryWrite(
            kind="decision",
            title="Limiter",
            claim="Use in-process limiter",
            source_refs=("user-input",),
        )
    )

    assert svc.get(record.id).claim == "Use in-process limiter"


def test_supersede_and_archive_update_canonical_status(tmp_path):
    svc = MemoryService(tmp_path)
    record = svc.write(
        MemoryWrite(
            kind="decision",
            title="Limiter",
            claim="Use in-process limiter",
            source_refs=("user-input",),
        )
    )

    superseded = svc.supersede(record.id)
    assert superseded.status == "superseded"
    assert svc.get(record.id).status == "superseded"

    archived = svc.archive(record.id)
    assert archived.status == "archived"
    assert archived.archived is True
    assert svc.get(record.id).archived is True


def test_history_returns_canonical_event_envelopes(tmp_path):
    svc = MemoryService(tmp_path)
    record = svc.write(
        MemoryWrite(
            kind="decision",
            title="Limiter",
            claim="Use in-process limiter",
            source_refs=("user-input",),
        )
    )

    history = svc.history(record.id)

    assert [event.event_type for event in history] == ["memory.written"]
    assert history[0].target == record.id


def test_rejected_write_leaves_records_unchanged_and_records_rejection(tmp_path):
    svc = MemoryService(tmp_path)

    with pytest.raises(ValueError, match="source_refs required"):
        svc.write(
            MemoryWrite(
                kind="decision",
                title="Missing source",
                claim="Use canonical memory",
                source_refs=(),
            )
        )

    assert svc.list(statuses=()) == ()
    events = svc.history()
    assert [event.event_type for event in events] == ["memory.rejected"]
    assert events[0].payload["reason"] == "source_refs required"
