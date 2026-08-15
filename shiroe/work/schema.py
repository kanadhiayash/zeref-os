"""Canonical Work Graph domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeKind(str, Enum):
    task = "task"
    decision = "decision"
    approval = "approval"
    review = "review"


class GraphStatus(str, Enum):
    draft = "draft"
    ready = "ready"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class NodeStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    running = "running"
    blocked = "blocked"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


def _coerce_enum(value: Enum | str, enum_type: type[Enum], field_name: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unknown {field_name}: {value!r}") from exc


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_s: float = 0.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_s < 0:
            raise ValueError("backoff_s must be >= 0")


@dataclass(frozen=True)
class Placement:
    mode: str = "local"
    node_id: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"local", "node"}:
            raise ValueError("unsupported placement mode")
        if self.mode == "node" and not self.node_id:
            raise ValueError("node placement requires node_id")
        if self.mode == "local" and self.node_id is not None:
            raise ValueError("local placement cannot name node_id")


@dataclass(frozen=True)
class WorkNode:
    id: str
    graph_id: str
    kind: NodeKind | str
    objective: str
    requires: tuple[str, ...] = ()
    risk: str = "low"
    approval_required: bool = False
    independent_review: bool = False
    evidence_required: bool = False
    expected_outputs: tuple[str, ...] = ()
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    placement: Placement = field(default_factory=Placement)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.id, "node id")
        _require_text(self.graph_id, "graph_id")
        _require_text(self.objective, "objective")
        object.__setattr__(self, "kind", _coerce_enum(self.kind, NodeKind, "node kind"))
        object.__setattr__(self, "requires", tuple(self.requires))
        object.__setattr__(self, "expected_outputs", tuple(self.expected_outputs))
        if not isinstance(self.retry, RetryPolicy):
            object.__setattr__(self, "retry", RetryPolicy(**self.retry))
        if not isinstance(self.placement, Placement):
            object.__setattr__(self, "placement", Placement(**self.placement))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class WorkEdge:
    graph_id: str
    src_id: str
    dst_id: str

    def __post_init__(self) -> None:
        _require_text(self.graph_id, "graph_id")
        _require_text(self.src_id, "src_id")
        _require_text(self.dst_id, "dst_id")
        if self.src_id == self.dst_id:
            raise ValueError("work edge cannot be a self-edge")


@dataclass(frozen=True)
class WorkGraph:
    id: str
    objective: str
    nodes: tuple[WorkNode, ...]
    edges: tuple[WorkEdge, ...] = ()
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    status: GraphStatus | str = GraphStatus.draft
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.id, "graph id")
        _require_text(self.objective, "objective")
        if self.version < 1:
            raise ValueError("graph version must be >= 1")
        object.__setattr__(self, "status", _coerce_enum(self.status, GraphStatus, "graph status"))
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "success_criteria", tuple(self.success_criteria))
        object.__setattr__(self, "metadata", dict(self.metadata))
        for node in self.nodes:
            if node.graph_id != self.id:
                raise ValueError(f"node {node.id!r} belongs to graph {node.graph_id!r}")
        for edge in self.edges:
            if edge.graph_id != self.id:
                raise ValueError(f"edge {edge.src_id!r}->{edge.dst_id!r} belongs to graph {edge.graph_id!r}")
