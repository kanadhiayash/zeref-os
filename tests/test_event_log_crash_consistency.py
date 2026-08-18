"""
privacy-audit: allow-file "Tests name event-envelope schema fields only; no user data."

Crash-consistency of the canonical event log head.

A crash between the event append (fsync'd) and the head replacement must not
create an undetected or unrecoverable fork. On open the head must be
reconstructed from the true log tail after the chain validates; genuine
tampering or a head that names an event the log does not contain must fail
closed (raise) rather than silently repair.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from shiroe.storage.events import (  # noqa: E402
    EventEnvelope,
    EventLog,
    HashChainError,
)

_GENESIS = "sha256:0"


def _envelope(n: int) -> EventEnvelope:
    return EventEnvelope(
        event_type="capability.approved",
        actor="test",
        target=f"cap-{n}",
        payload={"n": n},
    )


def _seed(root: Path, count: int) -> list[dict]:
    """Append `count` events through the real API; return the sealed envelopes."""
    log = EventLog(root)
    return [log.append(_envelope(n)) for n in range(count)]


def _head_path(root: Path) -> Path:
    return root / "memory" / "events" / "head.json"


def _write_head_raw(root: Path, head: str, last_event_id: str) -> None:
    _head_path(root).write_text(
        json.dumps({"head": head, "last_event_id": last_event_id}), encoding="utf-8"
    )


def _jsonl_path(root: Path) -> Path:
    return next((root / "memory" / "events").rglob("events.jsonl"))


# ---------------------------------------------------------------------------
# A. Crash after event fsync but before head replacement.
def test_stale_head_reconstructs_to_true_tail(tmp_path: Path) -> None:
    r = _seed(tmp_path, 3)  # head.json now points at r[2]

    # Simulate the crash: the last event reached the jsonl (fsync'd) but the
    # head replacement never landed, so head still points at the prior event.
    _write_head_raw(tmp_path, r[1]["hash"], r[1]["event_id"])

    reopened = EventLog(tmp_path)
    assert reopened._load_head() == r[2]["hash"], "head not reconstructed to true tail"

    fourth = reopened.append(_envelope(3))
    assert fourth["previous_hash"] == r[2]["hash"], "next append chained off stale head"
    EventLog(tmp_path).verify_chain()


# B. Head references an event absent from the log -> fail closed.
def test_unknown_head_fails_closed(tmp_path: Path) -> None:
    _seed(tmp_path, 3)
    bogus = "sha256:" + "de" * 32  # a hash that appears nowhere in the log
    _write_head_raw(tmp_path, bogus, "evt_bogus")

    with pytest.raises(HashChainError):
        EventLog(tmp_path)._load_head()


# C. Genuine tampering must not be silently repaired.
def test_tampered_log_fails_closed(tmp_path: Path) -> None:
    _seed(tmp_path, 3)

    path = _jsonl_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    mutated = json.loads(lines[1])
    mutated["payload"]["n"] = 999  # breaks the recomputed hash of that event
    lines[1] = json.dumps(mutated, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Pre-existing guard must still fire.
    with pytest.raises(HashChainError):
        EventLog(tmp_path).verify_chain()
    # And opening/appending must fail closed rather than repair.
    with pytest.raises(HashChainError):
        EventLog(tmp_path)._load_head()


# D. Missing head + valid log -> reconstructed deterministically to the tail.
def test_missing_head_reconstructs(tmp_path: Path) -> None:
    r = _seed(tmp_path, 3)
    _head_path(tmp_path).unlink()

    reopened = EventLog(tmp_path)
    assert reopened._load_head() == r[2]["hash"]

    fourth = reopened.append(_envelope(3))
    assert fourth["previous_hash"] == r[2]["hash"]
    EventLog(tmp_path).verify_chain()


# E. Empty log -> valid genesis behaviour, no crash.
def test_empty_log_genesis(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    assert log._load_head() == _GENESIS

    first = log.append(_envelope(0))
    assert first["previous_hash"] == _GENESIS
    log.verify_chain()


# Durability: the head write must route through the atomic (fsync'd) helper.
def test_head_write_is_atomic(tmp_path: Path) -> None:
    import shiroe.storage.events as events_mod

    calls: list[Path] = []
    original = events_mod.atomic_write

    def spy(path: Path, content: str) -> None:
        calls.append(path)
        original(path, content)

    events_mod.atomic_write = spy
    try:
        EventLog(tmp_path).append(_envelope(0))
    finally:
        events_mod.atomic_write = original

    assert calls, "_write_head bypassed the atomic helper"
    assert calls[0].name == "head.json"
