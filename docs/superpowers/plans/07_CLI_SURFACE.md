# Phase 07: CLI and Product Surface Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose only real vNext operations through a small modular CLI and remove runtime registries/dev surfaces that can drift from executable reality.

**Architecture:** Split the monolithic `shiroe/cli.py` into command modules. Python imports and CapabilityStore are runtime truth. Generated/tracked component inventories do not define product behavior.

**Tech Stack:** argparse, Python modules, JSON output, pytest subprocess E2E.

## Global Constraints

- Public commands: `init`, `status`, `plan`, `run`, `approve`, `memory`, `verify`, `handoff`, `doctor`.
- Operator commands: `policy`, `capability`, `state`, `version`.
- Every command supports deterministic exit codes and machine-readable JSON where state is returned.
- No `write-decision`, `grade`, `audit-privacy`, `audit`, `db-status`, top-level `recall`, `explain-search`, `cost`, `factguard`, `evidence`, `facts`, `contradictions`, `privacy`, `route`, `team`, `release`, `claims`, `prompt`, `loop`, `lineage`, or `benchmark` top-level group remains.

---

### Task 1: Create modular CLI package and core parser

**Files:**
- Replace: `shiroe/cli.py` with package `shiroe/cli/`
- Create: `shiroe/cli/__init__.py`
- Create: `shiroe/cli/main.py`
- Create command modules: `init.py`, `status.py`, `plan.py`, `run.py`, `approve.py`, `memory.py`, `verify.py`, `handoff.py`, `doctor.py`, `policy.py`, `capability.py`, `state.py`, `version.py`
- Modify: `shiroe/__main__.py`
- Test: `tests/e2e/test_cli_surface.py`

**Interfaces:**
- Produces: `shiroe.cli.main.main(argv=None) -> int`.

- [ ] **Step 1: Write exact top-level command test without parsing formatted help**

```python
from shiroe.cli.main import registered_command_names

EXPECTED = {"init", "status", "plan", "run", "approve", "memory", "verify", "handoff", "doctor", "policy", "capability", "state", "version"}


def test_cli_exposes_exact_top_level_surface():
    assert set(registered_command_names()) == EXPECTED
```

`registered_command_names()` returns the module names from the same fixed registration tuple consumed by `build_parser()`, so the test does not depend on argparse help formatting.

- [ ] **Step 2: Prove failure**

```bash
pytest tests/e2e/test_cli_surface.py -q
```

- [ ] **Step 3: Implement parser with command modules**

Each module exports:

```python
def register(subparsers: argparse._SubParsersAction) -> None: ...
def run(args: argparse.Namespace) -> int: ...
```

`main.py` imports the 13 modules, registers them in a fixed tuple, parses args, and returns `args.handler(args)`.

- [ ] **Step 4: Run CLI test**

```bash
pytest tests/e2e/test_cli_surface.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/cli shiroe/__main__.py tests/e2e/test_cli_surface.py
git rm shiroe/cli.py
git commit -m "refactor(cli): expose the vnext operational surface"
```

### Task 2: Implement public Work Graph commands

**Files:**
- Modify: `shiroe/cli/plan.py`
- Modify: `shiroe/cli/run.py`
- Modify: `shiroe/cli/status.py`
- Test: `tests/e2e/test_work_graph_cli.py`
- Create: `tests/fixtures/vnext/simple_work_graph.json`

**Interfaces:**
- `shiroe plan --from-json PATH`
- `shiroe run --graph ID [--dry-run]`
- `shiroe status [--graph ID] --json`

- [ ] **Step 1: Add fixture**

```json
{
  "id": "graph_smoke",
  "objective": "Verify one-node work graph",
  "constraints": [],
  "success_criteria": ["node completes"],
  "nodes": [
    {"id": "node_smoke", "kind": "task", "objective": "Run smoke capability", "requires": ["test.echo"], "expected_outputs": ["message"]}
  ],
  "edges": []
}
```

- [ ] **Step 2: Write subprocess E2E**

Plan must persist graph; status must report it; dry-run must show selected node/capability/policy without invoking the capability.

- [ ] **Step 3: Implement and run**

```bash
pytest tests/e2e/test_work_graph_cli.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/cli tests/e2e/test_work_graph_cli.py tests/fixtures/vnext/simple_work_graph.json
git commit -m "feat(cli): operate work graphs"
```

### Task 3: Implement approval CLI with explicit human decision path

**Files:**
- Modify: `shiroe/cli/approve.py`
- Test: `tests/e2e/test_approval_cli.py`

**Interfaces:**

```text
shiroe approve list --json
shiroe approve show APPROVAL_ID --json
shiroe approve advise APPROVAL_ID --capability CAPABILITY_ID --json
shiroe approve decide APPROVAL_ID --decision approved|rejected|revise|deferred --reason TEXT
```

- [ ] **Step 1: Write tests proving `advise` does not approve**

Run `advise`, then `show`: status must remain pending. Run `decide --decision approved`: status becomes approved with human actor metadata.

- [ ] **Step 2: Implement CLI**

`decide` is the only command that calls `ApprovalService.decide_human`. `advise` calls only `ApprovalAdvisor.advise`.

- [ ] **Step 3: Run tests**

```bash
pytest tests/e2e/test_approval_cli.py tests/invariant/test_human_approval_authority.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/cli/approve.py tests/e2e/test_approval_cli.py
git commit -m "feat(cli): expose explicit human approval flow"
```

### Task 4: Converge memory/verification/handoff CLI

**Files:**
- Modify: `shiroe/cli/memory.py`
- Modify: `shiroe/cli/verify.py`
- Modify: `shiroe/cli/handoff.py`
- Test: `tests/e2e/test_memory_verify_handoff_cli.py`
- Create: `tests/fixtures/vnext/simple_memory.json`

**Interfaces:**

```text
shiroe memory write --from PATH
shiroe memory recall QUERY --json
shiroe memory list --json
shiroe memory show ID --json
shiroe memory supersede OLD --with NEW
shiroe memory archive ID
shiroe memory views

shiroe verify --graph ID --json
shiroe verify --memory ID --json

shiroe handoff TARGET --graph ID --json
```

- [ ] **Step 1: Create memory fixture**

```json
{
  "kind": "decision",
  "title": "Smoke decision",
  "claim": "Use a single node smoke graph",
  "source_refs": ["user-input"],
  "privacy_class": "internal",
  "evidence_grade": "C"
}
```

- [ ] **Step 2: Write E2E proving immediate recall and handoff**

- [ ] **Step 3: Implement and run**

```bash
pytest tests/e2e/test_memory_verify_handoff_cli.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/cli tests/e2e/test_memory_verify_handoff_cli.py tests/fixtures/vnext/simple_memory.json
git commit -m "feat(cli): converge memory verification and handoff"
```

### Task 5: Replace runtime registry files with executable discovery

**Files:**
- Delete: `shiroe-registry.json` if still present
- Delete: `registry/components.json`
- Delete: `registry/missions.json`
- Delete: `registry/codecs.json`
- Delete: `registry/adapters.json` if generated from code and not needed as input
- Delete/refactor: `shiroe/registry/`
- Keep CapabilityStore SQLite as capability registry
- Test: `tests/invariant/test_runtime_surface_resolves.py`

**Interfaces:**
- Produces: doctor/introspection reads actual Python command registrations and adapter registry.

- [ ] **Step 1: Write runtime resolution test**

```python

def test_every_registered_cli_handler_is_callable():
    for command, handler in iter_registered_commands():
        assert callable(handler), command


def test_every_registered_adapter_is_invokable_and_healthy():
    for name, adapter in adapter_registry().items():
        assert callable(adapter.invoke), name
        assert adapter.health().healthy is True
```

- [ ] **Step 2: Delete generated component registry machinery**

Do not replace it with another tracked inventory file. Runtime truth is code plus CapabilityStore.

- [ ] **Step 3: Run tests**

```bash
pytest tests/invariant/test_runtime_surface_resolves.py -q
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(registry): derive active surface from executable code"
```

### Task 6: Move repo-development release/claim checks out of runtime product surface

**Files:**
- Remove top-level CLI groups already absent
- Move or delete `shiroe/release/claim_gate.py`, release-report tooling and repo-only audit reports
- Keep `doctor` only for installed runtime health
- Move repo-only checks to `scripts/` or `devtools/` if still valuable
- Test: `tests/e2e/test_doctor_runtime_only.py`

- [ ] **Step 1: Write doctor expectations**

Doctor checks only:

```text
canonical state opens/migrates
hash chain verifies
policy stack parses
capability store opens
active adapters health-check
active work graph state is internally consistent
memory canonical tables are readable
no stale approval is treated as approved
```

- [ ] **Step 2: Refactor doctor and remove repo-development coupling**

README link checks, public claim scans, lineage checks, benchmark freshness and release artifact manifests are not installed-runtime doctor checks.

- [ ] **Step 3: Run tests**

```bash
pytest tests/e2e/test_doctor_runtime_only.py -q
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(cli): separate runtime health from repo maintenance"
```

## Phase gate

```bash
python -m shiroe --help
pytest tests/e2e tests/invariant/test_runtime_surface_resolves.py -q
```
