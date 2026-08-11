# Phase 02: State and Work Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a persisted Work Graph the single operational work model before replacing legacy Mission/Team execution.

**Architecture:** The Work Graph package owns schema, compilation, persistence, readiness and graph lifecycle. Execution remains outside this package and is replaced in Phase 04.

**Tech Stack:** dataclasses, enums, SQLite, JSON, pytest.

## Global Constraints

- Allowed node kinds: `task`, `decision`, `approval`, `review` only.
- Graphs declare capability requirements, not agent seats.
- Graph joins use predecessor edges. Retries/iterations use bounded node policy.
- No generic Knowledge Graph survives this phase.
- Graph persistence uses canonical StateDB.

---

### Task 1: Define Work Graph domain types

**Files:**
- Create: `shiroe/work/__init__.py`
- Create: `shiroe/work/schema.py`
- Test: `tests/unit/work/test_schema.py`

**Interfaces:**
- Produces: `NodeKind`, `GraphStatus`, `NodeStatus`, `RetryPolicy`, `WorkNode`, `WorkEdge`, `WorkGraph`.

- [ ] **Step 1: Write failing schema tests**

```python
import pytest
from shiroe.work.schema import NodeKind, RetryPolicy, WorkNode


def test_retry_policy_rejects_unbounded_attempts():
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)


def test_work_node_rejects_unknown_kind():
    with pytest.raises(ValueError):
        WorkNode(id="n1", graph_id="g1", kind="worker", objective="x")


def test_work_node_defaults_are_bounded():
    node = WorkNode(id="n1", graph_id="g1", kind=NodeKind.task, objective="x")
    assert node.retry.max_attempts == 1
    assert node.requires == ()
```

- [ ] **Step 2: Prove failure**

```bash
pytest tests/unit/work/test_schema.py -q
```

- [ ] **Step 3: Implement exact domain skeleton**

```python
class NodeKind(str, Enum):
    task = "task"
    decision = "decision"
    approval = "approval"
    review = "review"

class GraphStatus(str, Enum):
    draft = "draft"
    ready = "ready"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

class NodeStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    running = "running"
    blocked = "blocked"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_s: float = 0.0

@dataclass(frozen=True)
class WorkNode:
    id: str
    graph_id: str
    kind: NodeKind | str
    objective: str
    requires: tuple[str, ...] = ()
    risk: str = "low"
    approval_required: bool = False
    independent_review: bool = False
    evidence_required: bool = False
    expected_outputs: tuple[str, ...] = ()
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    metadata: dict[str, Any] = field(default_factory=dict)
```

Add `WorkEdge` and `WorkGraph` with immutable tuples for nodes/edges and explicit version integer starting at 1. Validate non-empty ids/objectives and positive graph version in `__post_init__`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/work/test_schema.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/work tests/unit/work/test_schema.py
git commit -m "feat(work): add canonical work graph domain"
```

### Task 2: Add Work Graph tables to canonical state

**Files:**
- Create: `shiroe/migrations/m0003_work_graph.py`
- Test: `tests/integration/state/test_work_graph_migration.py`

**Interfaces:**
- Consumes: `StateDB.migrate()`.
- Produces tables: `work_graphs`, `work_nodes`, `work_edges`, `work_attempts`.

- [ ] **Step 1: Write migration test**

```python
from shiroe.storage.state import StateDB


def test_work_graph_migration_creates_required_tables(tmp_path):
    with StateDB(tmp_path) as db:
        db.migrate()
        tables = set(db.tables())
    assert {"work_graphs", "work_nodes", "work_edges", "work_attempts"} <= tables
```

- [ ] **Step 2: Prove failure**

```bash
pytest tests/integration/state/test_work_graph_migration.py -q
```

- [ ] **Step 3: Implement schema**

Use these required columns:

```sql
CREATE TABLE work_graphs (
    id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    success_criteria_json TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE work_nodes (
    id TEXT PRIMARY KEY,
    graph_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    objective TEXT NOT NULL,
    requires_json TEXT NOT NULL,
    risk TEXT NOT NULL,
    approval_required INTEGER NOT NULL DEFAULT 0,
    independent_review INTEGER NOT NULL DEFAULT 0,
    evidence_required INTEGER NOT NULL DEFAULT 0,
    expected_outputs_json TEXT NOT NULL,
    retry_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    status TEXT NOT NULL,
    output_json TEXT,
    state_version INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(graph_id) REFERENCES work_graphs(id)
);

CREATE TABLE work_edges (
    graph_id TEXT NOT NULL,
    src_id TEXT NOT NULL,
    dst_id TEXT NOT NULL,
    PRIMARY KEY(graph_id, src_id, dst_id),
    FOREIGN KEY(graph_id) REFERENCES work_graphs(id),
    FOREIGN KEY(src_id) REFERENCES work_nodes(id),
    FOREIGN KEY(dst_id) REFERENCES work_nodes(id)
);

CREATE TABLE work_attempts (
    id TEXT PRIMARY KEY,
    graph_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    capability_id TEXT,
    state TEXT NOT NULL,
    input_digest TEXT,
    output_digest TEXT,
    error TEXT,
    usage_json TEXT,
    started_at TEXT,
    ended_at TEXT,
    FOREIGN KEY(graph_id) REFERENCES work_graphs(id),
    FOREIGN KEY(node_id) REFERENCES work_nodes(id)
);
```

Add indexes on graph status, node graph/status and attempt node.

- [ ] **Step 4: Run migration tests plus existing StateDB tests**

```bash
pytest tests/integration/state/test_work_graph_migration.py tests/test_vnext_pr2_storage.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/migrations/m0003_work_graph.py tests/integration/state/test_work_graph_migration.py
git commit -m "feat(state): persist work graphs and attempts"
```

### Task 3: Implement Work Graph persistence and optimistic state transitions

**Files:**
- Create: `shiroe/work/store.py`
- Test: `tests/unit/work/test_store.py`
- Test: `tests/invariant/test_work_graph_concurrency.py`

**Interfaces:**
- Produces: `WorkStore.create(graph)`, `WorkStore.get(graph_id)`, `WorkStore.set_graph_status(...)`, `WorkStore.set_node_status(...)`, `WorkStore.record_output(...)`.

- [ ] **Step 1: Write failing persistence tests**

```python
from shiroe.work.store import WorkStore
from shiroe.work.schema import WorkGraph, WorkNode, NodeKind


def test_create_then_get_round_trips(tmp_path):
    graph = WorkGraph(id="g1", objective="ship", nodes=(WorkNode(id="n1", graph_id="g1", kind=NodeKind.task, objective="inspect"),))
    store = WorkStore(tmp_path)
    store.create(graph)
    assert store.get("g1").objective == "ship"


def test_node_transition_is_compare_and_swap(tmp_path):
    store = WorkStore(tmp_path)
    graph = WorkGraph(id="g1", objective="ship", nodes=(WorkNode(id="n1", graph_id="g1", kind=NodeKind.task, objective="inspect"),))
    store.create(graph)
    version = store.node_state_version("n1")
    store.set_node_status("n1", "running", expected_version=version)
    with pytest.raises(ConcurrentWorkUpdate):
        store.set_node_status("n1", "completed", expected_version=version)
```

- [ ] **Step 2: Prove failure**

```bash
pytest tests/unit/work/test_store.py tests/invariant/test_work_graph_concurrency.py -q
```

- [ ] **Step 3: Implement store with transactions and CAS**

Every state update must use:

```sql
UPDATE work_nodes
SET status=?, state_version=state_version+1
WHERE id=? AND state_version=?
```

Raise `ConcurrentWorkUpdate` when `rowcount != 1`. Serialize JSON with sorted keys and compact separators for deterministic digests.

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/work/test_store.py tests/invariant/test_work_graph_concurrency.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/work/store.py tests/unit/work/test_store.py tests/invariant/test_work_graph_concurrency.py
git commit -m "feat(work): persist graph lifecycle with cas"
```

### Task 4: Implement graph compiler and readiness calculation

**Files:**
- Create: `shiroe/work/compiler.py`
- Create: `shiroe/work/readiness.py`
- Test: `tests/unit/work/test_compiler.py`
- Test: `tests/unit/work/test_readiness.py`

**Interfaces:**
- Produces: `compile_work_graph(spec: dict) -> WorkGraph`, `ready_node_ids(graph, statuses) -> tuple[str, ...]`.

- [ ] **Step 1: Write failure-mode tests**

Cover exact rejections:

```python
@pytest.mark.parametrize("spec, fragment", [
    ({"id": "g", "objective": "x", "nodes": []}, "nodes"),
    ({"id": "g", "objective": "x", "nodes": [{"id": "a", "kind": "task", "objective": "x"}, {"id": "a", "kind": "task", "objective": "y"}]}, "duplicate"),
    ({"id": "g", "objective": "x", "nodes": [{"id": "a", "kind": "task", "objective": "x"}], "edges": [{"from": "a", "to": "missing"}]}, "unknown"),
])
def test_compile_rejects_invalid_graph(spec, fragment):
    with pytest.raises(WorkGraphError, match=fragment):
        compile_work_graph(spec)
```

Also test cycle rejection and approval node validity.

- [ ] **Step 2: Prove failure**

```bash
pytest tests/unit/work/test_compiler.py tests/unit/work/test_readiness.py -q
```

- [ ] **Step 3: Implement compiler**

Compiler requirements:

- normalize node/edge order by id;
- reject unknown node kind;
- reject duplicate node id;
- reject unknown edge endpoint;
- reject self-edge;
- reject graph cycles;
- require `approval_required=True` for `approval` nodes;
- require every retry `max_attempts >= 1`;
- return immutable `WorkGraph`.

Readiness rule: a pending node is ready only when every predecessor is `completed` or `skipped`; approval nodes additionally remain blocked until an approval record is approved in Phase 03.

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/work/test_compiler.py tests/unit/work/test_readiness.py -q
```

- [ ] **Step 5: Port surviving old task-graph compiler invariants**

Move meaningful cases from `tests/test_task_graph_compiler.py` into the new tests. Do not preserve old node-kind or Mission semantics.

- [ ] **Step 6: Commit**

```bash
git add shiroe/work/compiler.py shiroe/work/readiness.py tests/unit/work
git commit -m "feat(work): compile and schedule canonical graphs"
```

### Task 5: Remove generic Knowledge Graph

**Files:**
- Delete: `shiroe/graph/knowledge.py`
- Delete: `shiroe/graph/exports.py`
- Delete: `tests/test_knowledge_graph.py`
- Delete: `tests/test_graph_exports.py`
- Modify: `shiroe/graph/__init__.py`
- Modify: `docs/architecture/REMOVALS.md`
- Test: `tests/invariant/test_single_graph_model.py`

**Interfaces:**
- Produces: Work Graph is the only operational graph package; knowledge relations remain in `memory_relations`.

- [ ] **Step 1: Write absence test**

```python
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def test_no_generic_knowledge_graph_runtime():
    assert not (ROOT / "shiroe/graph/knowledge.py").exists()
    assert not (ROOT / "shiroe/graph/exports.py").exists()
```

- [ ] **Step 2: Delete files and detach imports**

Do not create a replacement generic graph abstraction. Memory relationship export, if needed later, must be implemented from `memory_relations` as a Memory Engine view.

- [ ] **Step 3: Run phase tests**

```bash
pytest tests/unit/work tests/integration/state/test_work_graph_migration.py tests/invariant/test_work_graph_concurrency.py tests/invariant/test_single_graph_model.py -q
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(graph): converge on work graph only"
```

## Phase gate

```bash
python -m compileall -q shiroe
pytest tests/unit/work tests/integration/state tests/invariant/test_work_graph_concurrency.py tests/invariant/test_single_graph_model.py -q
```
