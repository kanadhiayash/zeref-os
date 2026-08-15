from __future__ import annotations

import json
from pathlib import Path

from shiroe.adapters.capabilities.base import AdapterResult, EnforcementLevel, HealthReport
from shiroe.adapters.capabilities.registry import register_adapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.execution.supervisor import ExecutionSupervisor
from shiroe.nodes.store import NodeStore
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


class FailingLocalAdapter:
    name = "test-failing-local"
    enforcement_level = EnforcementLevel.embedded
    supported_types = ("script",)

    def health(self):
        return HealthReport(
            adapter=self.name,
            detected_version="1",
            enforcement_level=self.enforcement_level,
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        raise AssertionError("local adapter must not run for node placement")


class FakeRemoteExecutor:
    def __init__(self) -> None:
        self.packages: list[dict] = []

    def __call__(self, root, *, node, package, transport):
        self.packages.append(package)
        return AdapterResult(
            ok=True,
            output={"remote": node.id, "input": package["inputs"]["message"]},
            usage={"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        )


def _register_capability(root: Path, capability_id: str) -> str:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["capability.invoke", "subprocess"]}),
        encoding="utf-8",
    )
    adapter = FailingLocalAdapter()
    register_adapter(adapter.name, adapter)
    src = root / "capabilities" / "remote" / "run.sh"
    src.parent.mkdir(parents=True)
    src.write_text("#!/bin/sh\necho remote\n", encoding="utf-8")
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
    return trust.digest


def test_remote_placement_uses_node_dispatcher_not_local_adapter(tmp_path: Path) -> None:
    capability_id = "test.remote.exec"
    digest = _register_capability(tmp_path, capability_id)
    node_store = NodeStore(tmp_path, id_factory=lambda: "node_worker")
    node = node_store.register_candidate(
        name="Node1",
        role="worker",
        transport_host="node1.tailnet.ts.net",
        ssh_user="shiroe_worker",
        capability_digest=digest,
    )
    node_store.trust_node(node.id, trusted=True)
    graph = compile_work_graph(
        {
            "id": "g-remote",
            "objective": "remote",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "task",
                    "objective": "run remote",
                    "requires": [capability_id],
                    "placement": {"mode": "node", "node_id": "node_worker"},
                    "metadata": {"inputs": {"message": "hello"}},
                }
            ],
        }
    )
    WorkStore(tmp_path).create(graph)
    remote = FakeRemoteExecutor()

    summary = ExecutionSupervisor(tmp_path, remote_executor=remote).run("g-remote")

    assert summary.status == "completed"
    assert WorkStore(tmp_path).node_output("n1") == {"remote": "node_worker", "input": "hello"}
    assert remote.packages[0]["worker_node_id"] == "node_worker"
    assert NodeStore(tmp_path).leases_for_work_node("n1", state="completed")
