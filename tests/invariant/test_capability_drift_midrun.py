from shiroe.capabilities import revoke
from shiroe.execution.supervisor import ExecutionSupervisor
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore

from tests.integration.execution.test_supervisor import register_test_capability


def _graph(root, capability_id):
    graph = compile_work_graph(
        {
            "id": "g-drift",
            "objective": "drift",
            "nodes": [
                {"id": "n1", "kind": "task", "objective": "first", "requires": [capability_id]},
            ],
        }
    )
    WorkStore(root).create(graph)
    return graph.id


def test_capability_digest_drift_blocks_invocation(tmp_path):
    capability_id = "test.echo"
    src = register_test_capability(tmp_path, capability_id=capability_id)
    graph_id = _graph(tmp_path, capability_id)
    src.write_text("#!/bin/sh\necho drift\n", encoding="utf-8")
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "failed"
    assert "digest drift" in (summary.reason or "")


def test_revoked_capability_blocks_invocation(tmp_path):
    capability_id = "test.echo"
    register_test_capability(tmp_path, capability_id=capability_id)
    revoke(tmp_path, capability_id)
    graph_id = _graph(tmp_path, capability_id)
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "failed"
    assert "lifecycle" in (summary.reason or "")
