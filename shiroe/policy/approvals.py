"""Scope-bound human approval domain types."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ApprovalType(str, Enum):
    action = "action"
    strategic = "strategic"
    exception = "exception"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    revise = "revise"
    deferred = "deferred"
    stale = "stale"


def scope_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    approval_type: ApprovalType | str
    requested_action: str
    scope: Mapping[str, Any]
    reason: str
    risk: str
    graph_id: str | None = None
    node_id: str | None = None
    action_kind: str | None = None
    options: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    status: ApprovalStatus | str = ApprovalStatus.pending
    requested_at: str = ""
    decided_at: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("approval id must be non-empty")
        if not self.requested_action.strip():
            raise ValueError("requested_action must be non-empty")
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")
        object.__setattr__(self, "approval_type", ApprovalType(self.approval_type))
        object.__setattr__(self, "status", ApprovalStatus(self.status))
        object.__setattr__(self, "scope", dict(self.scope))
        object.__setattr__(self, "options", tuple(self.options))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "digest", scope_digest(self.scope))


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    status: ApprovalStatus | str
    actor: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ApprovalStatus(self.status))
