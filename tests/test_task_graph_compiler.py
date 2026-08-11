"""SHR-103, 104, 109: task-graph compiler refuses malformed specs."""

from __future__ import annotations

from pathlib import Path

import pytest

from shiroe.graph import TaskGraphError, compile_task_graph


def _ok_spec() -> dict:
    return {
        "nodes": [
            {"id": "a", "kind": "action"},
            {"id": "b", "kind": "action"},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }


def test_compiles_valid_spec() -> None:
    g = compile_task_graph(_ok_spec())
    assert g["node_count"] == 2
    assert g["edge_count"] == 1


def test_missing_nodes_key_fails() -> None:
    with pytest.raises(TaskGraphError, match="non-empty list"):
        compile_task_graph({"edges": []})


def test_unknown_node_kind_fails() -> None:
    with pytest.raises(TaskGraphError, match="unknown kind 'ritual'"):
        compile_task_graph({"nodes": [{"id": "a", "kind": "ritual"}]})


def test_duplicate_node_id_fails() -> None:
    with pytest.raises(TaskGraphError, match="duplicate node id"):
        compile_task_graph({"nodes": [{"id": "x"}, {"id": "x"}], "edges": []})


def test_fake_edge_target_fails() -> None:
    with pytest.raises(TaskGraphError, match="references unknown node"):
        compile_task_graph({
            "nodes": [{"id": "a"}],
            "edges": [{"from": "a", "to": "phantom"}],
        })


def test_fake_edge_source_fails() -> None:
    with pytest.raises(TaskGraphError, match="references unknown node"):
        compile_task_graph({
            "nodes": [{"id": "a"}],
            "edges": [{"from": "phantom", "to": "a"}],
        })


def test_self_loop_fails() -> None:
    with pytest.raises(TaskGraphError, match="self-loop"):
        compile_task_graph({
            "nodes": [{"id": "a"}],
            "edges": [{"from": "a", "to": "a"}],
        })


def test_missing_artifact_fails(tmp_path: Path) -> None:
    spec = {"nodes": [{"id": "a", "artifacts": ["missing.txt"]}]}
    with pytest.raises(TaskGraphError, match="artifact missing"):
        compile_task_graph(spec, artifact_root=tmp_path)


def test_present_artifact_passes(tmp_path: Path) -> None:
    (tmp_path / "there.txt").write_text("ok", encoding="utf-8")
    spec = {"nodes": [{"id": "a", "artifacts": ["there.txt"]}]}
    g = compile_task_graph(spec, artifact_root=tmp_path)
    assert g["nodes"][0]["artifacts"] == ["there.txt"]


def test_unguarded_irreversible_node_fails() -> None:
    with pytest.raises(TaskGraphError, match="irreversible but not guarded"):
        compile_task_graph({
            "nodes": [{"id": "wipe", "irreversible": True}],
            "edges": [],
        })


def test_guarded_irreversible_node_passes() -> None:
    g = compile_task_graph({
        "nodes": [{"id": "wipe", "irreversible": True, "guarded": True}],
        "edges": [],
    })
    assert g["nodes"][0]["irreversible"] is True
    assert g["nodes"][0]["guarded"] is True


def test_spec_not_dict_fails() -> None:
    with pytest.raises(TaskGraphError, match="spec must be a dict"):
        compile_task_graph("not a dict")


def test_edges_not_list_fails() -> None:
    with pytest.raises(TaskGraphError, match="spec.edges must be a list"):
        compile_task_graph({"nodes": [{"id": "a"}], "edges": "not a list"})


def test_node_missing_id_fails() -> None:
    with pytest.raises(TaskGraphError, match="missing string id"):
        compile_task_graph({"nodes": [{"kind": "action"}]})
