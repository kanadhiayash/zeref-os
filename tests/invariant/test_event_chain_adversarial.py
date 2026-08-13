"""H3.1: event-chain corruption matrix.

Baseline (2 cases) covered deleted-middle event and head-rewind. This
file extends coverage so every mutation category the design cares about
is rejected deterministically (HashChainError) or surfaced as a
schema/validation failure -- never silently accepted.

Matrix (H3.1):
  - modified payload             (fabricated re-hash also detects)
  - modified stored hash field
  - broken previous_hash chain
  - truncated final event         (partial JSON line at EOF)
  - duplicate event line
  - invalid ordering              (swap two adjacent events)
  - missing required event field  (schema/JSON error)
"""

import json

import pytest

from shiroe.storage import EventEnvelope, EventLog, StateDB
from shiroe.storage.events import HashChainError


def _log(tmp_path):
    (tmp_path / "REDACT.md").write_text("# minimal\n", encoding="utf-8")
    db = StateDB(tmp_path)
    db.migrate()
    return EventLog(tmp_path, redact_md=tmp_path / "REDACT.md", mirror_conn=db.connect())


def _events_path(tmp_path):
    return next((tmp_path / "memory" / "events").rglob("events.jsonl"))


def _seed(tmp_path, count=3):
    log = _log(tmp_path)
    for i in range(count):
        log.append(EventEnvelope(event_type="memory.written", actor="test", payload={"i": i}))
    return log


def test_deleted_middle_event_breaks_hash_chain(tmp_path):
    log = _seed(tmp_path)
    path = _events_path(tmp_path)
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


def test_modified_payload_is_detected_as_hash_mismatch(tmp_path):
    log = _seed(tmp_path)
    path = _events_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    env = json.loads(lines[1])
    env["payload"]["i"] = 999  # tamper with content, do NOT recompute hash
    lines[1] = json.dumps(env, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(HashChainError, match="hash mismatch"):
        log.verify_chain()


def test_modified_stored_hash_field_is_detected_as_hash_mismatch(tmp_path):
    log = _seed(tmp_path)
    path = _events_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    env = json.loads(lines[1])
    env["hash"] = "sha256:" + "d" * 64
    lines[1] = json.dumps(env, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # The tampered hash either fails recompute at this event or breaks
    # the next event's previous_hash pointer. Either is a deterministic
    # HashChainError.
    with pytest.raises(HashChainError):
        log.verify_chain()


def test_broken_previous_hash_field_breaks_chain(tmp_path):
    log = _seed(tmp_path)
    path = _events_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    env = json.loads(lines[2])
    env["previous_hash"] = "sha256:" + "0" * 64  # dangling pointer
    lines[2] = json.dumps(env, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(HashChainError, match="chain break"):
        log.verify_chain()


def test_truncated_final_event_is_rejected(tmp_path):
    log = _seed(tmp_path)
    path = _events_path(tmp_path)
    text = path.read_text(encoding="utf-8")
    # Drop the last N chars so the closing brace of the tail line is
    # missing. iter_events feeds each non-empty line to json.loads; a
    # partial JSON line raises JSONDecodeError -- loud, not silent.
    path.write_text(text[: len(text) - 8], encoding="utf-8")

    with pytest.raises((json.JSONDecodeError, HashChainError)):
        log.verify_chain()


def test_duplicate_event_line_breaks_chain(tmp_path):
    log = _seed(tmp_path)
    path = _events_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    # Re-emit the middle line to simulate an accidental double-write.
    duplicated = lines[:2] + [lines[1]] + lines[2:]
    path.write_text("\n".join(duplicated) + "\n", encoding="utf-8")

    with pytest.raises(HashChainError, match="chain break"):
        log.verify_chain()


def test_swapped_event_order_breaks_chain(tmp_path):
    log = _seed(tmp_path)
    path = _events_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    # Swap events 1 and 2 -- each still hashes correctly on its own,
    # but the chain now points at the wrong previous hash.
    reordered = [lines[0], lines[2], lines[1]]
    path.write_text("\n".join(reordered) + "\n", encoding="utf-8")

    with pytest.raises(HashChainError, match="chain break"):
        log.verify_chain()


def test_missing_required_field_is_rejected(tmp_path):
    log = _seed(tmp_path)
    path = _events_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    env = json.loads(lines[1])
    env.pop("event_type", None)  # required field per validate_envelope
    lines[1] = json.dumps(env, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises((HashChainError, KeyError, ValueError)):
        log.verify_chain()
