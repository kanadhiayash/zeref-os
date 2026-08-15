"""Canonical storage layer (ADR-0001).

Invariant enforced here:

    SQLite = canonical current state (memory/state/shiroe.sqlite)
    JSONL  = canonical append-only history (memory/events/*.jsonl)
    Markdown = generated human view (memory/views/*.md)
    TOON / Parquet = optional generated model / analytical exports.
"""

from shiroe.storage.state import StateDB
from shiroe.storage.events import EventLog, EventEnvelope

__all__ = ["StateDB", "EventLog", "EventEnvelope"]
