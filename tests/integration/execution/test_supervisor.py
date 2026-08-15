import json
from pathlib import Path

from shiroe.adapters.capabilities.base import AdapterResult, EnforcementLevel, HealthReport
from shiroe.adapters.capabilities.registry import register_adapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.execution.supervisor import ExecutionSupervisor
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


class EchoAdapter:
    name = "test-echo"
    enforcement_level = EnforcementLevel.embedded
    supported_types = ("test_echo",)

    def health(self):
        return HealthReport(
            adapter=self.name,
            detected_version="1",
            enforcement_level=self.enforcement_level,
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        return AdapterResult(
            ok=True,
            output={"message": inputs.get("message", "ok")},
            usage={"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
        )


def register_test_capability(root: Path, *, capability_id: str, adapter=None) -> Path:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["capability.invoke", "subprocess"]}),
        encoding="utf-8",
    )
    adapter = adapter or EchoAdapter()
    register_adapter(adapter.name, adapter)
    src = root / "capabilities" / capability_id.replace(".", "_") / "run.sh"
    src.parent.mkdir(parents=True)
    src.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    trust = inspect_source(src)
    manifest = {
        "schema": "shiroe.capability/v1",
        "id": capability_id,
        "name": capability_id,
        "type": "script",
        "version": "1",
        "source": {"kind": "local-file", "location": str(src)},
        "entrypoint": {"adapter": adapter.name, "command": [str(src)]},
        "requires": {},
    }
    store = CapabilityStore(root)
    try:
        store.upsert_capability(
            capability_id=capability_id,
            name=capability_id,
            type_="script",
            lifecycle="active",
            digest=trust.digest,
            manifest=manifest,
            source_kind="local-file",
            source_location=str(src),
        )
    finally:
        store.close()
    return src


def _seed_two_node_graph(root, capability_id):
    graph = compile_work_graph(
        {
            "id": "g-exec",
            "objective": "execute two nodes",
            "nodes": [
                {"id": "n1", "kind": "task", "objective": "first", "requires": [capability_id]},
                {"id": "n2", "kind": "task", "objective": "second", "requires": [capability_id]},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        }
    )
    WorkStore(root).create(graph)
    return graph.id


def test_supervisor_executes_ready_nodes_and_persists_outputs(tmp_path):
    capability_id = "test.echo"
    register_test_capability(tmp_path, capability_id=capability_id)
    graph_id = _seed_two_node_graph(tmp_path, capability_id=capability_id)
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "completed"
    assert WorkStore(tmp_path).get_node("n2").status.value == "completed"
    assert WorkStore(tmp_path).node_output("n2") == {"message": "ok"}
