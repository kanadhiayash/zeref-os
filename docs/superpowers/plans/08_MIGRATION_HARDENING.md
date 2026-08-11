# Phase 08: Migration, Hardening and Final Purge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve user-authored memory, remove obsolete schema/runtime residue, and prove the smaller architecture survives adversarial and failure conditions before later benchmark work begins.

**Architecture:** Migration is explicit and verified. Legacy user data is archived after import; obsolete execution/benchmark tables are removed after backup. Final hardening uses invariant/E2E tests, not benchmark scores.

**Tech Stack:** SQLite backup API, JSONL hash verification, pytest, subprocess E2E.

## Global Constraints

- User memory is never silently deleted.
- Destructive schema migration requires a verified backup.
- No benchmark suite or BM25 is reintroduced here.
- No compatibility shim may recreate a deleted product abstraction.

---

### Task 1: Add pre-destructive database backup and migration metadata

**Files:**
- Modify: `shiroe/migrations/__init__.py`
- Modify: `shiroe/storage/state.py`
- Create: `tests/invariant/test_destructive_migration_backup.py`

**Interfaces:**
- Produces: migrations may declare `DESTRUCTIVE = True`; `StateDB.migrate()` creates backup before first destructive migration.

- [ ] **Step 1: Write backup test with explicit setup and verification**

```python
import sqlite3
from shiroe.storage.state import StateDB


def _seed_schema_v2_database(root):
    with StateDB(root) as db:
        db.migrate(target_version=2)
    return root / "memory/state/shiroe.sqlite"


def _integrity_check(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def test_destructive_migration_creates_verifiable_backup(tmp_path):
    _seed_schema_v2_database(tmp_path)
    StateDB(tmp_path).migrate()
    backups = list((tmp_path / "memory/state/backups").glob("shiroe.sqlite.*.bak"))
    assert backups
    assert _integrity_check(backups[0]) == "ok"
```

This task also adds optional `target_version: int | None = None` to `migrate()` and `StateDB.migrate()` so tests can construct a pre-destructive schema deterministically. Production callers omit it and migrate to latest.

- [ ] **Step 2: Implement migration metadata**

Migration runner reads module-level `DESTRUCTIVE = True`. Before the first pending destructive migration, use `sqlite3.Connection.backup()` into `memory/state/backups/` and run `PRAGMA integrity_check` on the backup. Abort migration if backup verification is not `ok`.

- [ ] **Step 3: Run tests**

```bash
pytest tests/invariant/test_destructive_migration_backup.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/migrations shiroe/storage/state.py tests/invariant/test_destructive_migration_backup.py
git commit -m "feat(state): back up before destructive migrations"
```

### Task 2: Migrate legacy user memory into canonical records and archive sources

**Files:**
- Rewrite: `shiroe/storage/importer.py`
- Create: `tests/integration/state/test_legacy_memory_migration.py`
- Keep only required readers under `shiroe/compat/`

**Interfaces:**
- Produces: `migrate_legacy_memory(root, *, archive_legacy=False) -> MigrationReport`.

- [ ] **Step 1: Write fixture migration test**

Seed a project with a legacy atom JSONL decision and legacy state DB. After migration:

```python
report = migrate_legacy_memory(tmp_path)
assert report.imported >= 1
assert MemoryService(tmp_path).search("legacy limiter").hits
assert report.source_digests
```

- [ ] **Step 2: Implement idempotent import**

Use content digests and source provenance. A second migration must import zero duplicates. `archive_legacy=True` moves legacy files only after canonical counts/digests verify.

- [ ] **Step 3: Run tests**

```bash
pytest tests/integration/state/test_legacy_memory_migration.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/storage/importer.py shiroe/compat tests/integration/state/test_legacy_memory_migration.py
git commit -m "feat(state): migrate legacy memory without loss"
```

### Task 3: Drop obsolete execution/benchmark schema tables

**Files:**
- Create: `shiroe/migrations/m0006_remove_legacy_runtime_tables.py`
- Test: `tests/integration/state/test_legacy_table_removal.py`

**Interfaces:**
- Produces: clean schema without Mission/Team/benchmark evaluator tables.

- [ ] **Step 1: Write failing table absence test**

```python
OBSOLETE = {"missions", "team_runs", "team_assignments", "execution_steps", "capability_benchmarks", "evaluator_runs"}

def test_obsolete_runtime_tables_removed(tmp_path):
    with StateDB(tmp_path) as db:
        db.migrate()
        assert OBSOLETE.isdisjoint(set(db.tables()))
```

- [ ] **Step 2: Mark migration destructive and drop in dependency order**

```python
DESTRUCTIVE = True

def up(conn):
    for table in ("team_assignments", "execution_steps", "team_runs", "missions", "capability_benchmarks", "evaluator_runs"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
```

If foreign-key enforcement blocks a drop, rebuild dependent tables correctly. Do not disable foreign keys and ignore errors.

- [ ] **Step 3: Run migration tests**

```bash
pytest tests/invariant/test_destructive_migration_backup.py tests/integration/state/test_legacy_table_removal.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/migrations/m0006_remove_legacy_runtime_tables.py tests/integration/state/test_legacy_table_removal.py
git commit -m "refactor(state): remove obsolete runtime tables"
```

### Task 4: Build final adversarial governance suite

**Files:**
- Create: `tests/invariant/test_approval_bypass_adversarial.py`
- Create: `tests/invariant/test_policy_precedence_adversarial.py`
- Create: `tests/invariant/test_event_chain_adversarial.py`
- Create: `tests/invariant/test_concurrent_execution_adversarial.py`
- Rehome current privacy adversarial tests under `tests/invariant/privacy/`

**Interfaces:**
- Produces: non-benchmark hardening gate.

- [ ] **Step 1: Encode approval bypass payloads**

For every always-approval ActionKind test contexts including:

```python
{"approved": True}
{"approval_required": False}
{"override": True}
{"skip_approval": True}
{"emergency": True, "signed_off": True}
{"actor": "approval-advisor"}
```

Expected: no payload changes `require_approval` into allow.

- [ ] **Step 2: Add scope mutation tests**

Mutate file list, command args, tag/version, target branch, graph node metadata and artifact digest after approval. Every mutation must make the request stale before invocation.

- [ ] **Step 3: Add event-chain tamper tests**

Modify payload/hash/previous_hash/remove middle event/reorder two events. `state verify` must fail and name the first invalid event.

- [ ] **Step 4: Add concurrency tests**

Two supervisors race same node; exactly one invocation may commit. Two memory writes to different ids may both succeed. Same-id conflicting write must surface deterministically.

- [ ] **Step 5: Run invariant suite**

```bash
pytest tests/invariant -q
```

- [ ] **Step 6: Commit**

```bash
git add tests/invariant
git commit -m "test(hardening): add vnext adversarial invariants"
```

### Task 5: Build fresh-project end-to-end acceptance test

**Files:**
- Create: `tests/e2e/test_fresh_project_lifecycle.py`
- Reuse: `tests/fixtures/vnext/simple_work_graph.json`
- Reuse: `tests/fixtures/vnext/simple_memory.json`

**Interfaces:**
- Proves installed runtime lifecycle without benchmark dependencies.

- [ ] **Step 1: Implement subprocess lifecycle**

The E2E must:

1. `shiroe init` a temp project;
2. register/seed an executable fake local capability through the same CapabilityStore API used in production tests;
3. `shiroe plan` the fixture;
4. `shiroe status --json` sees graph;
5. `shiroe run --graph graph_smoke` completes safe node;
6. create a second graph with publish action and prove it pauses for approval;
7. `shiroe approve decide ... approved` resumes only matching scope;
8. `shiroe memory write` then recall succeeds immediately;
9. `shiroe verify` returns no block for the good graph;
10. delete generated views, rebuild them, confirm canonical state unchanged;
11. `shiroe handoff human --graph ... --json` includes graph id/version/pending approvals/decisions;
12. `shiroe state verify --json` passes.

- [ ] **Step 2: Run E2E five times to catch nondeterminism**

```bash
for i in 1 2 3 4 5; do pytest tests/e2e/test_fresh_project_lifecycle.py -q || exit 1; done
```

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_fresh_project_lifecycle.py
git commit -m "test(e2e): prove fresh vnext governance lifecycle"
```

### Task 6: Final dead-surface purge and documentation convergence

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/architecture/CORE_SCOPE.md`
- Modify: `docs/architecture/REMOVALS.md`
- Delete stale docs that describe removed active architecture
- Test: `tests/invariant/test_no_dead_surface_references.py`

- [ ] **Step 1: Write dead-reference test**

Search active docs/code for:

```text
pattern-to-skill
skill-importer
fleet-activator
caveman-handoff
parent-sync
skill-router
budget-governor
Team Packs
Mission seats
BM25
benchmark score
status: contract
status: experimental
```

Allow these strings only in `docs/architecture/REMOVALS.md` and historical changelog/archive paths.

- [ ] **Step 2: Remove stale active docs/imports**

Do not keep superseded docs in active navigation. Git history is sufficient unless a migration note is required for users.

- [ ] **Step 3: Run complete verification**

```bash
python -m compileall -q shiroe
pytest -q
python -m shiroe doctor --json
python -m shiroe --help
git diff --check
git status --short
```

- [ ] **Step 4: Verify forbidden trees are gone**

```bash
! test -d skills
! test -d agents
! test -d commands
! test -d team-packs
! test -d missions
! test -d benchmarks
! test -d shiroe/missions
! test -d shiroe/teams
! test -d shiroe/runtime
! test -d shiroe/loops
! test -d shiroe/benchmark
! test -d shiroe/lineage
```

Note: `shiroe/agents/` is allowed only if it is the Python package created in Phase 06. The root markdown `agents/` directory must be absent.

- [ ] **Step 5: Commit final convergence**

```bash
git add -A
git commit -m "refactor(core): complete shiroe vnext convergence"
```

## Final gate

```bash
python -m compileall -q shiroe
pytest -q
python -m shiroe doctor --json
for i in 1 2 3 4 5; do pytest tests/e2e/test_fresh_project_lifecycle.py -q || exit 1; done
```

Do not start external benchmarks after this gate as part of the same branch. Benchmark design and installation is a separate post-overhaul program.
