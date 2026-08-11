import json

import pytest

from shiroe.storage import EventEnvelope, EventLog, StateDB
from shiroe.storage.events import HashChainError


def _log(tmp_path):
    (tmp_path / "REDACT.md").write_text("# minimal\n", encoding="utf-8")
    db = StateDB(tmp_path)
    db.migrate()
    return EventLog(tmp_path, redact_md=tmp_path / "REDACT.md", mirror_conn=db.connect())


def test_deleted_middle_event_breaks_hash_chain(tmp_path):
    log = _log(tmp_path)
    for i in range(3):
        log.append(EventEnvelope(event_type="memory.written", actor="test", payload={"i": i}))

    path = next((tmp_path / "memory" / "events").rglob("events.jsonl"))
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")

    with pytest.raises(HashChainError, match="chain break"):
        log.verify_chain()


def test_head_rewind_breaks_hash_chain_even_when_events_are_untouched(tmp_path):
    log = _log(tmp_path)
    first = log.append(EventEnvelope(event_type="memory.written", actor="test", payload={"i": 1}))
    log.append(EventEnvelope(event_type="memory.written", actor="test", payload={"i": 2}))

    head_path = tmp_path / "memory" / "events" / "head.json"
    head_path.write_text(
        json.dumps({"head": first["hash"], "last_event_id": first["event_id"]}),
        encoding="utf-8",
    )

    with pytest.raises(HashChainError, match="head marker"):
        log.verify_chain()
