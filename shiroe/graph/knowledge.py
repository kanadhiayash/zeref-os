"""Knowledge-graph (Wave 6, PR28)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from shiroe.core.errors import ShiroeError


class KnowledgeGraphError(ShiroeError):
    """Raised for invalid knowledge-graph operations."""


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    attrs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    subject: str
    predicate: str
    object: str
    provenance: str


DOMAIN_RANGE: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "authored_by": (frozenset({"project", "atom"}), frozenset({"person"})),
    "depends_on": (frozenset({"project"}), frozenset({"project"})),
    "mentions": (frozenset({"atom", "doc"}), frozenset({"person", "project", "concept"})),
}


class KnowledgeGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []

    def add_node(self, node: Node) -> None:
        if node.id in self._nodes:
            existing = self._nodes[node.id]
            if existing.kind != node.kind:
                raise KnowledgeGraphError(
                    f"node {node.id!r} kind conflict: {existing.kind!r} vs {node.kind!r}"
                )
        self._nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        if not edge.provenance:
            raise KnowledgeGraphError(
                f"edge ({edge.subject}, {edge.predicate}, {edge.object}) missing provenance"
            )
        if edge.subject not in self._nodes:
            raise KnowledgeGraphError(f"edge subject unknown: {edge.subject!r}")
        if edge.object not in self._nodes:
            raise KnowledgeGraphError(f"edge object unknown: {edge.object!r}")
        dom_ran = DOMAIN_RANGE.get(edge.predicate)
        if dom_ran is None:
            raise KnowledgeGraphError(f"unknown predicate: {edge.predicate!r}")
        allowed_subject, allowed_object = dom_ran
        s_kind = self._nodes[edge.subject].kind
        o_kind = self._nodes[edge.object].kind
        if s_kind not in allowed_subject:
            raise KnowledgeGraphError(
                f"predicate {edge.predicate!r} rejects subject kind {s_kind!r}; expected {sorted(allowed_subject)}"
            )
        if o_kind not in allowed_object:
            raise KnowledgeGraphError(
                f"predicate {edge.predicate!r} rejects object kind {o_kind!r}; expected {sorted(allowed_object)}"
            )
        self._edges.append(edge)

    def merge(self, edges: Iterable[Edge]) -> int:
        snapshot = list(self._edges)
        added = 0
        try:
            for e in edges:
                self.add_edge(e)
                added += 1
            return added
        except KnowledgeGraphError:
            self._edges = snapshot
            raise

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def edges(self) -> list[Edge]:
        return list(self._edges)

    def promote_to_canonical(self, write_guard) -> list[Edge]:
        approved: list[Edge] = []
        for e in self._edges:
            write_guard(e)
            approved.append(e)
        return approved
