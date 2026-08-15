"""H2.2: pin retry / timeout / attempt / duplicate-execution semantics."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path

import pytest

from shiroe.adapters.capabilities.base import AdapterResult, EnforcementLevel, HealthReport
from shiroe.adapters.capabilities.registry import register_adapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.execution.supervisor import ExecutionSupervisor
from shiroe.storage.state import StateDB
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


class _CountingAdapter:
    def __init__(self, *, ok: bool = True, name: str = "test-count"):
        self.name = name
        self.enforcement_level = EnforcementLevel.embedded
        self.supported_types = ("test_count",)
        self._ok = ok
        self.calls = 0
        self.seen_timeouts: list[int | None] = []

    def health(self):
        return HealthReport(
            adapter=self.name,
            detected_version="1",
            enforcement_level=self.enforcement_level,
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        self.calls += 1
        self.seen_timeouts.append(timeout_s)
        if self._ok:
            return AdapterResult(
                ok=True, output={"n": self.calls},
                usage={"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0},
            )
        return AdapterResult(ok=False, error="deliberate", usage={"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0})


def _register(root: Path, adapter: _CountingAdapter, capability_id: str) -> None:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["capability.invoke", "subprocess"]}),
        encoding="utf-8",
    )
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


def _seed_one(root, capability_id, *, timeout_s: int | None = None):
    metadata: dict = {}
    if timeout_s is not None:
        metadata["timeout_s"] = timeout_s
    graph = compile_work_graph(
        {
            "id": "g-exec-inv",
            "objective": "single node",
            "nodes": [
                {"id": "n1", "kind": "task", "objective": "one",
                 "requires": [capability_id], "metadata": metadata},
            ],
            "edges": [],
        }
    )
    WorkStore(root).create(graph)
    return graph.id


def _attempts(root, node_id):
    conn = sqlite3.connect(StateDB(root).path)
    try:
        rows = conn.execute(
            "SELECT id, attempt, state FROM work_attempts WHERE node_id=? ORDER BY attempt",
            (node_id,),
        ).fetchall()
    finally:
        conn.close()
    return rows


@pytest.fixture
def unique_capability():
    counter = {"n": 0}

    def _make(root: Path, *, ok: bool = True):
        counter["n"] += 1
        cap_id = f"test.exec.inv{counter['n']}"
        adapter = _CountingAdapter(ok=ok, name=f"test-count-{counter['n']}")
        _register(root, adapter, cap_id)
        return cap_id, adapter

    return _make


def test_first_successful_run_records_exactly_one_attempt(tmp_path, unique_capability):
    cap, _ = unique_capability(tmp_path)
    graph_id = _seed_one(tmp_path, cap)
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "completed"
    rows = _attempts(tmp_path, "n1")
    assert len(rows) == 1
    _, attempt_no, state = rows[0]
    assert attempt_no == 1
    assert state == "completed"


def test_failed_adapter_marks_attempt_failed_and_stops(tmp_path, unique_capability):
    cap, _ = unique_capability(tmp_path, ok=False)
    graph_id = _seed_one(tmp_path, cap)
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "failed"
    rows = _attempts(tmp_path, "n1")
    assert len(rows) == 1
    _, attempt_no, state = rows[0]
    assert attempt_no == 1
    assert state == "failed"


def test_default_timeout_is_60_seconds_when_metadata_omits_it(tmp_path, unique_capability):
    cap, adapter = unique_capability(tmp_path)
    graph_id = _seed_one(tmp_path, cap)
    ExecutionSupervisor(tmp_path).run(graph_id)
    assert adapter.seen_timeouts == [60]


def test_metadata_timeout_is_passed_through_to_adapter(tmp_path, unique_capability):
    cap, adapter = unique_capability(tmp_path)
    graph_id = _seed_one(tmp_path, cap, timeout_s=17)
    ExecutionSupervisor(tmp_path).run(graph_id)
    assert adapter.seen_timeouts == [17]


def test_completed_graph_does_not_re_execute_on_second_run(tmp_path, unique_capability):
    """No duplicate execution of a completed node."""
    cap, adapter = unique_capability(tmp_path)
    graph_id = _seed_one(tmp_path, cap)
    ExecutionSupervisor(tmp_path).run(graph_id)
    assert adapter.calls == 1

    ExecutionSupervisor(tmp_path).run(graph_id)
    assert adapter.calls == 1
    rows = _attempts(tmp_path, "n1")
    assert len(rows) == 1


def test_failed_graph_reattempt_currently_does_not_auto_retry(tmp_path, unique_capability):
    """Pin observed behaviour: supervisor does not auto-retry a failed node.

    If this ever changes (add retry with backoff), the assertion needs to
    reflect the new invariant explicitly.
    """
    cap, adapter = unique_capability(tmp_path, ok=False)
    graph_id = _seed_one(tmp_path, cap)
    ExecutionSupervisor(tmp_path).run(graph_id)
    summary2 = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary2.status == "failed"
    rows = _attempts(tmp_path, "n1")
    assert len(rows) == 1
