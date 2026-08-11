# Phase 04: Capability and Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Mission/Team/seat execution with a Work Graph supervisor that invokes only approved executable capabilities.

**Architecture:** Capability Engine resolves runtime requirements. Execution Engine owns criticality, reasoning requirement, budget, timeout, retry, concurrency and Work Graph state transitions. No seat characters or Mission blueprints remain after the replacement passes.

**Tech Stack:** SQLite, subprocess adapters, threading/concurrency, dataclasses, pytest.

## Global Constraints

- Context-only capability adapters cannot be active.
- Capabilities declare executable entrypoints and pass health before approval/activation.
- Every invocation rechecks lifecycle/digest immediately before execution.
- Policy authorization occurs before invocation.
- Work Graph is the only execution plan.

---

### Task 1: Make capability activation executable-only

**Files:**
- Modify: `shiroe/adapters/capabilities/base.py`
- Delete: `shiroe/adapters/capabilities/generic_skill.py`
- Delete: `shiroe/adapters/capabilities/agent.py`
- Modify: `shiroe/adapters/capabilities/registry.py`
- Modify: `shiroe/capabilities/manifest.py`
- Modify: `shiroe/capabilities/gate.py`
- Test: `tests/invariant/test_executable_capabilities_only.py`

**Interfaces:**
- Produces: executable adapter registry; `assert_executable()` rejects non-invokable capability types.

- [ ] **Step 1: Write failing tests**

```python

def test_context_only_adapters_are_not_registered():
    names = set(adapter_registry().keys())
    assert "generic-skill" not in names
    assert "agent" not in names


def test_manifest_requires_executable_entrypoint_for_invokable_type():
    with pytest.raises(ManifestError, match="entrypoint"):
        validate_manifest({"name": "x", "type": "cli"})
```

- [ ] **Step 2: Delete context-only adapters and tighten manifest validation**

Active adapter `health()` must report `healthy=True` and an enforcement level that represents actual invocation. Do not keep `context_only` as an active lifecycle state.

- [ ] **Step 3: Decide MCP adapter by capability, not documentation**

Run its tests. If it only supports initialize while the manifest declares tool invocation, remove the MCP adapter from active registry in this phase. It may return later when `tools/list` and `tools/call` are implemented and tested.

- [ ] **Step 4: Run tests**

```bash
pytest tests/invariant/test_executable_capabilities_only.py tests/test_provider_capability.py tests/test_vnext_pr4_capability.py tests/test_vnext_pr5_capability_adapters.py -q
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(capabilities): ship executable adapters only"
```

### Task 2: Create Execution Engine domain and move reusable criticality/budget primitives

**Files:**
- Create: `shiroe/execution/__init__.py`
- Create: `shiroe/execution/criticality.py`
- Create: `shiroe/execution/reasoning.py`
- Create: `shiroe/execution/budget.py`
- Test: `tests/unit/execution/test_criticality.py`
- Test: `tests/unit/execution/test_budget.py`

**Interfaces:**
- Produces: provider-neutral `RiskLevel`, `ReasoningClass`, `classify_node(node)`, `BudgetTracker`.

- [ ] **Step 1: Port tests before moving code**

Copy behavior tests from current `shiroe/routing/criticality.py`, `shiroe/core/reasoning.py`, and `shiroe/runtime/budget.py` into the new test paths. Remove model-name assumptions from core tests.

- [ ] **Step 2: Run new tests and prove import failure**

```bash
pytest tests/unit/execution/test_criticality.py tests/unit/execution/test_budget.py -q
```

- [ ] **Step 3: Move the smallest provider-neutral implementation**

Keep reasoning classes exactly:

```python
class ReasoningClass(str, Enum):
    fast = "fast"
    balanced = "balanced"
    deep = "deep"
    frontier = "frontier"
```

Provider model ids remain under adapters, never in `shiroe/execution`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/execution/test_criticality.py tests/unit/execution/test_budget.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/execution tests/unit/execution
git commit -m "refactor(execution): centralize criticality and budget"
```

### Task 3: Implement Work Graph supervisor

**Files:**
- Create: `shiroe/execution/supervisor.py`
- Test: `tests/integration/execution/test_supervisor.py`
- Test: `tests/invariant/test_execution_bounds.py`
- Test: `tests/invariant/test_capability_drift_midrun.py`

**Interfaces:**
- Consumes: `WorkStore`, `PolicyService`, capability resolver/gate, `BudgetTracker`.
- Produces: `ExecutionSupervisor.run(graph_id) -> RunSummary`, `resume(graph_id)`.

- [ ] **Step 1: Write failing happy-path test with an executable test adapter**

```python
from shiroe.adapters.capabilities.base import AdapterResult, EnforcementLevel, HealthReport
from shiroe.capabilities.store import CapabilityStore
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


class EchoAdapter:
    name = "test-echo"
    enforcement_level = EnforcementLevel.embedded
    supported_types = ("test_echo",)

    def health(self):
        return HealthReport(adapter=self.name, detected_version="1", enforcement_level=self.enforcement_level, healthy=True, supported_types=self.supported_types)

    def invoke(self, *, capability_id, action, inputs, permissions=None, timeout_s=None):
        return AdapterResult(ok=True, output={"message": inputs.get("message", "ok")}, usage={"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})


def _seed_two_node_graph(root, capability_id):
    graph = compile_work_graph({
        "id": "g-exec",
        "objective": "execute two nodes",
        "nodes": [
            {"id": "n1", "kind": "task", "objective": "first", "requires": [capability_id]},
            {"id": "n2", "kind": "task", "objective": "second", "requires": [capability_id]},
        ],
        "edges": [{"from": "n1", "to": "n2"}],
    })
    WorkStore(root).create(graph)
    return graph.id


def test_supervisor_executes_ready_nodes_and_persists_outputs(tmp_path):
    capability_id = "test.echo"
    register_test_capability(tmp_path, capability_id=capability_id, adapter=EchoAdapter())
    graph_id = _seed_two_node_graph(tmp_path, capability_id=capability_id)
    summary = ExecutionSupervisor(tmp_path).run(graph_id)
    assert summary.status == "completed"
    assert WorkStore(tmp_path).get_node("n2").status.value == "completed"
```

Define `register_test_capability(root, capability_id, adapter)` in the same test module. It must insert an approved/active capability through `CapabilityStore` and register the adapter through the same adapter registry API used by production code. Do not bypass `assert_executable()` by monkeypatching the supervisor.

- [ ] **Step 2: Write invariant tests before implementation**

Required cases:

- timeout produces failed attempt and never hangs;
- `max_attempts` is respected exactly;
- budget overrun pauses before the call that would cross the limit;
- capability digest drift between nodes blocks the next invocation;
- revoked capability blocks the next invocation;
- policy `require_approval` pauses node without invoking capability;
- policy deny fails/blocks without creating fake success;
- concurrent supervisors on the same graph cannot both commit the same node;
- resume does not rerun completed nodes;
- parallel-ready nodes may overlap, dependency edges never do;
- deadlocked graph fails with pending node ids.

- [ ] **Step 3: Implement supervisor state machine**

Use per-node attempts from `work_attempts`. Before every call execute this order:

```text
load current node
recheck node state/version
resolve requirement -> capability
assert capability executable/digest current
policy authorize action
check pending approval
check projected budget
persist attempt RUNNING
invoke with timeout
validate adapter result
persist output + usage
run required verification hook
transition node
refresh graph readiness
```

Never use Mission ids, seat ids, or team assignments.

- [ ] **Step 4: Run targeted tests**

```bash
pytest tests/integration/execution/test_supervisor.py tests/invariant/test_execution_bounds.py tests/invariant/test_capability_drift_midrun.py -q
```

- [ ] **Step 5: Port current hardening tests**

Move the strongest assertions from `tests/test_step_contracts.py`, `tests/test_verification_merge.py`, `tests/test_vnext_pr8_supervisor.py`, and capability drift tests. Rewrite them against Work Graph ids/nodes rather than weakening expected outcomes.

- [ ] **Step 6: Commit**

```bash
git add shiroe/execution tests/integration/execution tests/invariant
git commit -m "feat(execution): supervise work graphs with bounded execution"
```

### Task 4: Remove Missions, Teams, old runtime supervisor, loops and old task graph runtime

**Files:**
- Delete: `missions/`
- Delete: `shiroe/missions/`
- Delete: `shiroe/teams/`
- Delete: `shiroe/runtime/`
- Delete: `shiroe/loops/`
- Delete: `shiroe/execution_policies/`
- Delete: `shiroe/graph/task_graph.py`
- Delete: `shiroe/graph/runtime.py`
- Delete: architecture-coupled tests for Missions/Teams/old loops after invariant ports
- Modify: `shiroe/graph/__init__.py` or remove `shiroe/graph/` if empty
- Modify: `docs/architecture/REMOVALS.md`
- Test: `tests/invariant/test_single_execution_model.py`

**Interfaces:**
- Produces: only `shiroe.work` + `shiroe.execution` own work execution.

- [ ] **Step 1: Write absence/import test**

```python
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def test_legacy_execution_models_are_absent():
    for rel in ("missions", "shiroe/missions", "shiroe/teams", "shiroe/runtime", "shiroe/loops", "shiroe/execution_policies"):
        assert not (ROOT / rel).exists(), rel
```

- [ ] **Step 2: Delete old packages and update imports**

Do not create compatibility import aliases. If a real runtime caller still imports an old package, migrate the caller to Work/Execution APIs in the same commit.

- [ ] **Step 3: Delete old tests only after their surviving invariants are present in new tests**

Delete:
- Mission schema/loader tests;
- Team compiler tests;
- execution-sequence compatibility tests;
- old supervisor tests whose assertions have been ported;
- prompt-handoff-loop loop-specific tests once handoff behavior is covered later.

- [ ] **Step 4: Run execution gate**

```bash
pytest tests/unit/execution tests/integration/execution tests/invariant/test_execution_bounds.py tests/invariant/test_capability_drift_midrun.py tests/invariant/test_single_execution_model.py -q
python -m compileall -q shiroe
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(execution): retire mission and team runtimes"
```

## Phase gate

```bash
pytest tests/unit/execution tests/integration/execution tests/invariant/test_execution_bounds.py tests/invariant/test_capability_drift_midrun.py tests/test_policy_export_gates.py -q
! test -d missions
! test -d shiroe/missions
! test -d shiroe/teams
! test -d shiroe/runtime
! test -d shiroe/loops
```
