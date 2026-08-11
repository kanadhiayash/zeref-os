# Phase 01: Scope Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove benchmark machinery and non-operational contract surfaces before building replacement architecture, while preserving operational safety/runtime behavior needed during migration.

**Architecture:** This phase deletes surfaces that are already outside the approved product boundary. It does not remove old Mission/Team runtime yet because Work Graph execution is not operational until Phase 04.

**Tech Stack:** Python, argparse, pytest, Markdown docs.

## Global Constraints

- Baseline commit: `520dca437fa2d9f0349a26630666f1dd5221f919`.
- No benchmark or BM25 benchmark code survives this phase.
- Contract-only first-party Skills, markdown Agents, markdown Commands, and Team Pack declarations do not survive this phase.
- Do not remove existing policy/privacy/concurrency/capability tests that protect real runtime invariants.
- Do not remove Missions/Teams runtime until their replacement passes in Phase 04.

---

### Task 1: Pin the vNext core boundary in canonical documentation

**Files:**
- Create: `docs/architecture/CORE_SCOPE.md`
- Create: `docs/architecture/REMOVALS.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Test: `tests/invariant/test_core_scope.py`

**Interfaces:**
- Consumes: none.
- Produces: canonical product-boundary text used by later dead-surface checks.

- [ ] **Step 1: Write the failing scope test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_core_scope_declares_operational_only_surface():
    text = (ROOT / "docs/architecture/CORE_SCOPE.md").read_text()
    assert "declared component must be executable" in text.lower()
    assert "first-party skills: 0" in text.lower()
    assert "work graph" in text.lower()


def test_agents_spec_no_longer_declares_contract_skills_or_team_packs():
    text = (ROOT / "AGENTS.md").read_text()
    for removed in ("budget-governor", "skill-router", "fleet-activator", "pattern-to-skill", "Team Packs"):
        assert removed not in text
```

- [ ] **Step 2: Run the test and prove it fails**

```bash
pytest tests/invariant/test_core_scope.py -q
```

Expected: FAIL because `CORE_SCOPE.md` does not exist and `AGENTS.md` still declares removed surfaces.

- [ ] **Step 3: Create the core scope document with exact inventory**

Use this exact active inventory in `CORE_SCOPE.md`:

```text
First-party Skills: 0
First-party Agents: approval-advisor only when an executable reasoning capability exists
Runtime engines: State, Work Graph, Policy & Approval, Capability, Execution, Memory, Verification, Handoff & Context
Public CLI: init, status, plan, run, approve, memory, verify, handoff, doctor
Operator CLI: policy, capability, state, version
Non-operational component statuses: forbidden
```

Update `AGENTS.md` boot behavior so it refers to runtime commands and canonical state, not Skills/Agents/Team Packs. Update README to state the same boundary.

- [ ] **Step 4: Run the scope test**

```bash
pytest tests/invariant/test_core_scope.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md docs/architecture/CORE_SCOPE.md docs/architecture/REMOVALS.md tests/invariant/test_core_scope.py
git commit -m "docs(core): define operational-only vnext boundary"
```

### Task 2: Remove the current benchmark program and benchmark scorecard

**Files:**
- Delete: `benchmarks/`
- Delete: `shiroe/benchmark/`
- Delete: `shiroe/cli_benchmark.py`
- Delete: `tests/test_benchmark_adapters.py`
- Delete: `tests/test_benchmark_suite.py`
- Delete: `tests/test_benchmark_suite_ready.py`
- Delete: `tests/test_dataset_provider_integrity.py`
- Delete: `tests/test_external_harness_wave4.py`
- Delete: `tests/test_lineage_benchmarks.py`
- Delete: `tests/test_retrieval_benchmark.py`
- Delete: `tests/test_retrieval_bm25.py`
- Delete: `tests/test_vnext_pr19_benchmark_program.py`
- Delete: `tests/test_ws5_external_harness.py`
- Modify: `shiroe/cli.py`
- Modify: `README.md`
- Modify: `docs/architecture/REMOVALS.md`
- Test: `tests/invariant/test_no_benchmark_surface.py`

**Interfaces:**
- Consumes: current CLI parser.
- Produces: no benchmark product surface. Provider/capability runtime code remains only if independently operational.

- [ ] **Step 1: Write the failing absence test**

```python
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_packages_are_absent():
    assert not (ROOT / "benchmarks").exists()
    assert not (ROOT / "shiroe/benchmark").exists()
    assert not (ROOT / "shiroe/cli_benchmark.py").exists()


def test_cli_has_no_benchmark_command():
    out = subprocess.run([sys.executable, "-m", "shiroe", "--help"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    assert "benchmark" not in out.lower()
```

- [ ] **Step 2: Prove the test fails**

```bash
pytest tests/invariant/test_no_benchmark_surface.py -q
```

- [ ] **Step 3: Delete benchmark code/tests and remove CLI imports/registration**

Delete the paths exactly as listed. Remove benchmark references from CLI help, release checks, generated registries, README active-surface tables, and imports. Record the deletion reason in `REMOVALS.md`: `benchmarking will be rebuilt after vNext from the new public APIs`.

- [ ] **Step 4: Run targeted tests**

```bash
pytest tests/invariant/test_no_benchmark_surface.py tests/test_provider_capability.py tests/test_ollama_provider.py -q
```

Expected: PASS. Provider capability tests must still pass if those providers remain operational.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(scope): remove pre-vnext benchmark stack"
```

### Task 3: Remove contract-only first-party Skills, Agents, Commands and Team Packs

**Files:**
- Delete: `skills/`
- Delete: `agents/`
- Delete: `commands/`
- Delete: `team-packs/`
- Modify: `shiroe-registry.json` or delete it if no remaining consumer requires it
- Modify: `registry/shiroe-registry.schema.json` or delete it with the root registry
- Modify: `scripts/shiroe-validate.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture/REMOVALS.md`
- Test: `tests/invariant/test_no_contract_surfaces.py`

**Interfaces:**
- Consumes: active filesystem tree.
- Produces: runtime no longer advertises markdown-only product components.

- [ ] **Step 1: Write the failing absence test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_contract_directories_are_absent():
    for rel in ("skills", "agents", "commands", "team-packs"):
        assert not (ROOT / rel).exists(), rel


def test_no_contract_or_experimental_component_status_is_active():
    for path in [ROOT / "shiroe-registry.json", ROOT / "registry/components.json"]:
        if path.exists():
            text = path.read_text().lower()
            assert '"status": "contract"' not in text
            assert '"status": "experimental"' not in text
```

- [ ] **Step 2: Prove it fails**

```bash
pytest tests/invariant/test_no_contract_surfaces.py -q
```

- [ ] **Step 3: Delete the directories and remove validator assumptions**

Delete all listed directories. If `shiroe-registry.json` has no runtime consumer after benchmark/contract removal, delete it and its schema entirely. If one runtime consumer still depends on it, replace that dependency in the same task with direct runtime discovery and then delete it. Do not retain an empty compatibility registry.

- [ ] **Step 4: Remove count/inventory tests that protect deleted declarations**

Delete or rewrite tests whose only assertion is that a fixed number of Skills, Agents, Commands, or Team Packs exists. Preserve behavior tests for runtime policy, capability, memory, state, privacy and execution.

- [ ] **Step 5: Run targeted validation**

```bash
pytest tests/invariant/test_no_contract_surfaces.py tests/test_registry_parity.py -q
```

If `test_registry_parity.py` is now entirely about the deleted root registry, delete that test and replace it with `tests/invariant/test_runtime_surface_resolves.py` that checks actual Python entrypoints instead.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(scope): remove contract-only component surfaces"
```

### Task 4: Remove development lineage machinery from runtime scope

**Files:**
- Delete: `shiroe/lineage/`
- Delete: lineage-only tests under `tests/test_lineage_*.py`
- Modify: `shiroe/cli.py`
- Modify: release/doctor imports that reference lineage
- Modify: `docs/architecture/REMOVALS.md`
- Test: `tests/invariant/test_no_lineage_runtime.py`

**Interfaces:**
- Produces: lineage research is no longer a runtime product responsibility.

- [ ] **Step 1: Write failing test**

```python
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_lineage_runtime_is_absent():
    assert not (ROOT / "shiroe/lineage").exists()
    help_text = subprocess.run([sys.executable, "-m", "shiroe", "--help"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    assert "lineage" not in help_text
```

- [ ] **Step 2: Prove failure**

```bash
pytest tests/invariant/test_no_lineage_runtime.py -q
```

- [ ] **Step 3: Delete lineage runtime and detach release/doctor coupling**

Remove lineage imports from `shiroe/release/checks.py` and related tests. Do not move lineage code into another active Shiroe package. Git history is the archive.

- [ ] **Step 4: Run scope gate**

```bash
pytest tests/invariant/test_no_lineage_runtime.py tests/test_route_release_doctor.py -q
```

Rewrite doctor/release tests only to remove lineage expectations, not to relax real state/policy/privacy checks.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(scope): remove lineage from local core"
```

## Phase gate

```bash
python -m compileall -q shiroe
pytest -q
python -m shiroe --help
! test -d benchmarks
! test -d skills
! test -d agents
! test -d commands
! test -d team-packs
! test -d shiroe/benchmark
! test -d shiroe/lineage
```

Expected: all commands exit 0. Test count is intentionally not an acceptance metric.
