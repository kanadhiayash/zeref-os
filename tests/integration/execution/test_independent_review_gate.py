"""Wave 2b Part 2: independent_review must gate node completion.

The infra (`run_independent_review`) existed and was unit-tested, but the
supervisor never invoked it -- the field was persisted only. These pin the
wired behaviour:

* independent_review=True with a PASSING reviewer -> node completes.
* independent_review=True with a FAILING (block) reviewer -> node does not
  complete.
* independent_review=True with NO reviewer configured (review cannot
  happen) -> node does not complete.
"""

from __future__ import annotations

import json
from pathlib import Path

from shiroe.adapters.capabilities.base import AdapterResult, EnforcementLevel, HealthReport
from shiroe.adapters.capabilities.registry import register_adapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.execution.supervisor import ExecutionSupervisor
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


class _FixedAdapter:
    """Executor adapter: always succeeds with a fixed output."""

    enforcement_level = EnforcementLevel.embedded
    supported_types = ("test_exec",)

    def __init__(self, name: str):
        self.name = name
        self.calls = 0

    def health(self):
        return HealthReport(
            adapter=self.name, detected_version="1",
            enforcement_level=self.enforcement_level, healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        self.calls += 1
        return AdapterResult(
            ok=True, output={"message": "done"},
            usage={"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        )


class _ReviewerAdapter:
    """Reviewer adapter: returns a fixed verdict (pass/block)."""

    enforcement_level = EnforcementLevel.embedded
    supported_types = ("test_review",)

    def __init__(self, name: str, verdict: str):
        self.name = name
        self.verdict = verdict

    def health(self):
        return HealthReport(
            adapter=self.name, detected_version="1",
            enforcement_level=self.enforcement_level, healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        return AdapterResult(ok=True, output=json.dumps({"verdict": self.verdict, "findings": []}))


def _write_policy_defaults(root: Path) -> None:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["capability.invoke", "subprocess"]}), encoding="utf-8"
    )


def _register(root: Path, capability_id: str, adapter) -> None:
    _write_policy_defaults(root)
    register_adapter(adapter.name, adapter)
    src = root / "capabilities" / capability_id.replace(".", "_") / "run.sh"
    src.parent.mkdir(parents=True, exist_ok=True)
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


def _seed(root: Path, node: dict) -> str:
    graph = compile_work_graph(
        {"id": "g-review", "objective": "review gate", "nodes": [node], "edges": []}
    )
    WorkStore(root).create(graph)
    return graph.id


def test_independent_review_passing_completes(tmp_path):
    _register(tmp_path, "test.exec", _FixedAdapter("exec-pass"))
    _register(tmp_path, "test.rev", _ReviewerAdapter("rev-pass", "pass"))
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "reviewed",
        "requires": ["test.exec"], "independent_review": True,
        "metadata": {"reviewer_capability_id": "test.rev"},
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "completed"


def test_independent_review_failing_does_not_complete(tmp_path):
    _register(tmp_path, "test.exec", _FixedAdapter("exec-block"))
    _register(tmp_path, "test.rev", _ReviewerAdapter("rev-block", "block"))
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "reviewed",
        "requires": ["test.exec"], "independent_review": True,
        "metadata": {"reviewer_capability_id": "test.rev"},
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status != "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value != "completed"


def test_independent_review_missing_reviewer_does_not_complete(tmp_path):
    _register(tmp_path, "test.exec", _FixedAdapter("exec-none"))
    graph_id = _seed(tmp_path, {
        "id": "n1", "kind": "task", "objective": "reviewed",
        "requires": ["test.exec"], "independent_review": True,
        # no reviewer_capability_id -> review cannot happen
    })
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status != "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value != "completed"
