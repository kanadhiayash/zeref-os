"""Wave 2b Part 1: bounded retry / max_attempts / backoff / restart-safety.

Previously the supervisor never retried a failed node (the attempt count
serialized in the store was inert). These pin the REAL bounded-retry
lifecycle:

* max_attempts=3, scripted fail/fail/success -> node completes with three
  distinct canonical attempts recorded.
* three failures -> terminal failure after EXACTLY three attempts, no 4th.
* each attempt has a unique id, a persisted attempt number, and (on
  failure) a persisted failure reason.
* ``backoff_s`` is honored between attempts and is bounded (injected sleep,
  so the suite never actually waits).
* restart/resume does NOT reset the consumed attempt count -- attempts
  already spent (persisted in ``work_attempts``) stay spent.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
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


class _ScriptedAdapter:
    """Adapter whose per-call outcome comes from a scripted list of bools."""

    def __init__(self, outcomes, *, name: str):
        self.name = name
        self.enforcement_level = EnforcementLevel.embedded
        self.supported_types = ("test_script",)
        self._outcomes = list(outcomes)
        self.calls = 0

    def health(self):
        return HealthReport(
            adapter=self.name,
            detected_version="1",
            enforcement_level=self.enforcement_level,
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        idx = self.calls
        self.calls += 1
        ok = self._outcomes[idx] if idx < len(self._outcomes) else self._outcomes[-1]
        usage = {"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}
        if ok:
            return AdapterResult(ok=True, output={"n": self.calls}, usage=usage)
        return AdapterResult(ok=False, error=f"scripted fail {self.calls}", usage=usage)


def _register(root: Path, adapter: _ScriptedAdapter, capability_id: str) -> None:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["capability.invoke", "subprocess"]}), encoding="utf-8"
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


def _seed(root: Path, capability_id: str, *, max_attempts: int, backoff_s: float = 0.0) -> str:
    graph = compile_work_graph(
        {
            "id": "g-retry",
            "objective": "retry node",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "task",
                    "objective": "retryable",
                    "requires": [capability_id],
                    "retry": {"max_attempts": max_attempts, "backoff_s": backoff_s},
                }
            ],
            "edges": [],
        }
    )
    WorkStore(root).create(graph)
    return graph.id


def _attempts(root: Path, node_id: str):
    conn = sqlite3.connect(StateDB(root).path)
    try:
        return conn.execute(
            "SELECT id, attempt, state, error FROM work_attempts WHERE node_id=? ORDER BY attempt",
            (node_id,),
        ).fetchall()
    finally:
        conn.close()


@pytest.fixture
def cap_counter():
    counter = {"n": 0}

    def _make(root: Path, outcomes):
        counter["n"] += 1
        cap_id = f"test.retry{counter['n']}"
        adapter = _ScriptedAdapter(outcomes, name=f"test-retry-{counter['n']}")
        _register(root, adapter, cap_id)
        return cap_id, adapter

    return _make


def test_third_attempt_success_completes_with_three_attempts(tmp_path, cap_counter):
    cap, adapter = cap_counter(tmp_path, [False, False, True])
    graph_id = _seed(tmp_path, cap, max_attempts=3)
    sup = ExecutionSupervisor(tmp_path)
    sup._sleep = lambda _s: None
    summary = sup.run(graph_id)

    assert summary.status == "completed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "completed"
    assert adapter.calls == 3
    rows = _attempts(tmp_path, "n1")
    assert [r[1] for r in rows] == [1, 2, 3]  # persisted attempt numbers
    assert [r[2] for r in rows] == ["failed", "failed", "completed"]
    assert len({r[0] for r in rows}) == 3  # unique attempt ids


def test_three_failures_are_terminal_with_no_fourth_attempt(tmp_path, cap_counter):
    cap, adapter = cap_counter(tmp_path, [False, False, False])
    graph_id = _seed(tmp_path, cap, max_attempts=3)
    sup = ExecutionSupervisor(tmp_path)
    sup._sleep = lambda _s: None
    summary = sup.run(graph_id)

    assert summary.status == "failed"
    assert WorkStore(tmp_path).get_node("n1").status.value == "failed"
    assert adapter.calls == 3  # exactly three, no fourth
    rows = _attempts(tmp_path, "n1")
    assert [r[1] for r in rows] == [1, 2, 3]
    assert all(r[2] == "failed" for r in rows)
    assert all(r[3] for r in rows)  # every failure reason persisted


def test_backoff_is_honored_between_attempts_and_bounded(tmp_path, cap_counter):
    cap, _ = cap_counter(tmp_path, [False, False, True])
    graph_id = _seed(tmp_path, cap, max_attempts=3, backoff_s=0.25)
    sup = ExecutionSupervisor(tmp_path)
    slept: list[float] = []
    sup._sleep = lambda s: slept.append(s)
    summary = sup.run(graph_id)

    assert summary.status == "completed"
    # one backoff between attempt1->2 and attempt2->3, none after final success
    assert slept == [0.25, 0.25]


def test_backoff_is_capped(tmp_path, cap_counter):
    from shiroe.execution.supervisor import _MAX_BACKOFF_S

    cap, _ = cap_counter(tmp_path, [False, True])
    graph_id = _seed(tmp_path, cap, max_attempts=2, backoff_s=10_000.0)
    sup = ExecutionSupervisor(tmp_path)
    slept: list[float] = []
    sup._sleep = lambda s: slept.append(s)
    sup.run(graph_id)

    assert slept == [_MAX_BACKOFF_S]


def test_restart_does_not_reset_consumed_attempt_count(tmp_path, cap_counter):
    """Two attempts already spent (persisted) + a mid-retry crash left the
    node pending. Resume must only spend the ONE remaining attempt."""
    cap, adapter = cap_counter(tmp_path, [False, False, False])
    graph_id = _seed(tmp_path, cap, max_attempts=3)

    # Simulate a prior interrupted run: two failed attempts persisted, node
    # still pending (crash happened between attempts, before terminal fail).
    conn = sqlite3.connect(StateDB(tmp_path).path)
    try:
        for n in (1, 2):
            conn.execute(
                "INSERT INTO work_attempts(id, graph_id, node_id, attempt, capability_id, state, error, started_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                ("wa_" + uuid.uuid4().hex[:16], graph_id, "n1", n, cap, "failed", "prior", "t"),
            )
        conn.commit()
    finally:
        conn.close()

    sup = ExecutionSupervisor(tmp_path)
    sup._sleep = lambda _s: None
    summary = sup.run(graph_id)

    assert summary.status == "failed"
    assert adapter.calls == 1  # only the single remaining attempt, not a fresh 3
    rows = _attempts(tmp_path, "n1")
    assert [r[1] for r in rows] == [1, 2, 3]  # spent stays spent, one added -> 3 total
