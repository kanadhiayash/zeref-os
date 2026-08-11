"""Canonical handoff packet schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SCHEMA = "shiroe.handoff-packet/v1"


@dataclass(frozen=True)
class HandoffPacket:
    schema: str
    graph: dict
    pending_nodes: tuple[dict, ...]
    pending_approvals: tuple[dict, ...]
    active_decisions: tuple[dict, ...]
    open_risks: tuple[dict, ...]
    verification: tuple[dict, ...]
    relevant_files: tuple[str, ...]
    next_actions: tuple[str, ...]
    generated_at: str

    def to_dict(self) -> dict:
        return _json_ready(asdict(self))


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value
