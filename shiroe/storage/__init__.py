"""Canonical storage layer (vNext ADR-0001).

Invariant enforced here:

    SQLite = canonical current state (memory/state/shiroe.sqlite)
    JSONL  = canonical append-only history (memory/events/*.jsonl)
    Markdown = generated human view (memory/views/*.md)
    TOON / Parquet = optional generated model / analytical exports

Legacy modules (``shiroe.db``, ``shiroe.memory_state``) remain as v1
compatibility layers under their own docstrings. New writes flow through this
package.
"""

from shiroe.storage.state import StateDB
from shiroe.storage.events import EventLog, EventEnvelope

__all__ = ["StateDB", "EventLog", "EventEnvelope"]
