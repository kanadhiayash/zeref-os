"""SHR-112..118: knowledge-graph provenance, domain/range, merges, promotion."""

from __future__ import annotations

import pytest

from shiroe.graph import Edge, KnowledgeGraph, KnowledgeGraphError, Node


def _pop_kg() -> KnowledgeGraph:
    kg = KnowledgeGraph()
    kg.add_node(Node("alice", "person"))
    kg.add_node(Node("bob", "person"))
    kg.add_node(Node("shiroe", "project"))
    kg.add_node(Node("orb", "project"))
    kg.add_node(Node("atom-1", "atom"))
    return kg


def test_edge_without_provenance_fails() -> None:
    kg = _pop_kg()
    with pytest.raises(KnowledgeGraphError, match="missing provenance"):
        kg.add_edge(Edge("shiroe", "authored_by", "alice", ""))


def test_edge_with_provenance_lands() -> None:
    kg = _pop_kg()
    kg.add_edge(Edge("shiroe", "authored_by", "alice", "atom:a1"))
    assert kg.edge_count == 1


def test_invalid_predicate_fails() -> None:
    kg = _pop_kg()
    with pytest.raises(KnowledgeGraphError, match="unknown predicate"):
        kg.add_edge(Edge("shiroe", "worships", "alice", "atom:a1"))


def test_invalid_subject_kind_for_predicate_fails() -> None:
    kg = _pop_kg()
    with pytest.raises(KnowledgeGraphError, match="rejects subject kind 'person'"):
        kg.add_edge(Edge("alice", "authored_by", "bob", "atom:a1"))


def test_invalid_object_kind_for_predicate_fails() -> None:
    kg = _pop_kg()
    with pytest.raises(KnowledgeGraphError, match="rejects object kind 'project'"):
        kg.add_edge(Edge("shiroe", "authored_by", "orb", "atom:a1"))


def test_unknown_subject_or_object_fails() -> None:
    kg = _pop_kg()
    with pytest.raises(KnowledgeGraphError, match="subject unknown"):
        kg.add_edge(Edge("ghost", "authored_by", "alice", "atom:a1"))
    with pytest.raises(KnowledgeGraphError, match="object unknown"):
        kg.add_edge(Edge("shiroe", "authored_by", "ghost", "atom:a1"))


def test_node_kind_conflict_fails() -> None:
    kg = _pop_kg()
    with pytest.raises(KnowledgeGraphError, match="kind conflict"):
        kg.add_node(Node("alice", "project"))


def test_merge_rolls_back_on_error() -> None:
    kg = _pop_kg()
    kg.add_edge(Edge("shiroe", "authored_by", "alice", "atom:a1"))
    assert kg.edge_count == 1
    good = Edge("orb", "depends_on", "shiroe", "atom:a2")
    bad = Edge("alice", "authored_by", "bob", "atom:a3")
    with pytest.raises(KnowledgeGraphError):
        kg.merge([good, bad])
    assert kg.edge_count == 1


def test_merge_all_or_nothing_success() -> None:
    kg = _pop_kg()
    added = kg.merge([
        Edge("shiroe", "authored_by", "alice", "atom:a1"),
        Edge("orb", "depends_on", "shiroe", "atom:a2"),
    ])
    assert added == 2
    assert kg.edge_count == 2


def test_promote_runs_every_edge_through_write_guard() -> None:
    kg = _pop_kg()
    kg.add_edge(Edge("shiroe", "authored_by", "alice", "atom:a1"))
    kg.add_edge(Edge("orb", "depends_on", "shiroe", "atom:a2"))
    seen: list[Edge] = []
    def guard(e: Edge) -> None:
        seen.append(e)
    approved = kg.promote_to_canonical(guard)
    assert len(approved) == 2
    assert len(seen) == 2


def test_promote_aborts_on_guard_rejection() -> None:
    kg = _pop_kg()
    kg.add_edge(Edge("shiroe", "authored_by", "alice", "atom:a1"))
    kg.add_edge(Edge("orb", "depends_on", "shiroe", "atom:a2"))
    def reject(_e: Edge) -> None:
        raise KnowledgeGraphError("guard: policy deny")
    with pytest.raises(KnowledgeGraphError, match="policy deny"):
        kg.promote_to_canonical(reject)
