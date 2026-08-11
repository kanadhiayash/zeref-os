from shiroe.execution.supervisor import ExecutionSupervisor
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore

from tests.integration.execution.test_supervisor import register_test_capability


def test_budget_overrun_pauses_before_invocation(tmp_path):
    capability_id = "test.echo"
    register_test_capability(tmp_path, capability_id=capability_id)
    graph = compile_work_graph(
        {
            "id": "g-budget",
            "objective": "budget",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "task",
                    "objective": "first",
                    "requires": [capability_id],
                    "metadata": {"budget_projection": {"cost_usd": 2.0}},
                }
            ],
        }
    )
    WorkStore(tmp_path).create(graph)
    summary = ExecutionSupervisor(tmp_path, usd_max=1.0).run(graph.id)
    assert summary.status == "paused"
    assert summary.reason == "budget"
    assert WorkStore(tmp_path).get_node("n1").status.value == "blocked"
