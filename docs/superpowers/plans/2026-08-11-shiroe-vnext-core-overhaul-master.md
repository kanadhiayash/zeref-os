# Shiroe vNext Core Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Shiroe's overlapping skill/agent/team/mission/benchmark architecture with one operational Work Graph governance plane whose declared surfaces all execute and are tested.

**Architecture:** The overhaul uses a strangler sequence. Old runtime owners remain only until the replacement engine passes its targeted invariant and integration gates, then the obsolete owner and its architecture-coupled tests are deleted in the same wave. Benchmarking is not part of the implementation acceptance gate and is removed before the core migration.

**Tech Stack:** Python 3.11-3.13, stdlib-first SQLite, JSON/JSONL, argparse CLI, existing Shiroe policy/privacy/capability foundations, pytest.

## Global Constraints

- Source baseline: `520dca437fa2d9f0349a26630666f1dd5221f919`.
- Read `AGENTS.md`, `SOUL.md`, `config/PROJECT.md`, `PRIVACY.md`, and `REDACT.md` before editing.
- No benchmark implementation, BM25 implementation, benchmark score, benchmark fixture, or benchmark CLI remains in active vNext scope.
- No first-party standalone Skills remain in Local Core.
- No markdown-only Agent or Command is a shipped feature.
- No `contract` or `experimental` product component may remain in the active product surface.
- Every registered capability must resolve to an executable adapter and pass its health check.
- Human authorization is deterministic runtime state. No agent or model may write an approved decision.
- User memory must be preserved through verified migration. Generated views are disposable.
- Hardening tests for privacy, policy precedence, approval, state integrity, concurrency, capability drift, retries, and timeouts must not be weakened.
- Never change a failing test to accept a broader result merely to make the suite green.
- Delete a test only when its product behavior is intentionally deleted or it is replaced by a stronger vNext invariant test.
- Do not add compatibility aliases unless they protect user state migration.
- Do not push, merge, publish, deploy, or send externally without explicit human approval.
- Use small task-level commits. One task must be independently reviewable and revertible.

---

## Codex execution protocol

1. Create an isolated worktree or branch named `refactor/shiroe-vnext-core`.
2. Copy this plan set into `docs/superpowers/plans/` before code changes.
3. Execute phase files in numeric order. Do not skip a phase gate.
4. Within each task use strict red-green-refactor: failing test, prove failure, minimal code, prove pass, targeted regression, commit.
5. At each phase gate run the exact gate commands listed in that phase.
6. If a phase exposes an undocumented dependency on a deleted surface, stop that task, add a failing regression that reproduces the dependency, then resolve it without restoring the deleted abstraction.
7. Do not restore `contract`, `experimental`, Team Packs, Missions, first-party Skills, benchmark machinery, BM25, or markdown-only features as a workaround.
8. Record every intentionally deleted product surface in `docs/architecture/REMOVALS.md` with its replacement or `none`.
9. Record schema changes in an ADR only when the decision changes canonical state, approval authority, or Work Graph semantics.
10. After each phase, review `git diff --stat`, `git diff --check`, and `git status --short` before continuing.

## Final target inventory

| Surface | Target |
|---|---:|
| First-party Skills | 0 |
| First-party Agents | 1 operational Approval Advisor, conditional on an executable reasoning capability |
| Work orchestration models | 1 Work Graph |
| Runtime engines | 8 |
| Public CLI groups | 9 |
| Operator CLI groups | 3 plus `version` |
| Team Packs | 0 |
| Missions | 0 |
| Contract components | 0 |
| Experimental product components | 0 |
| Benchmark systems | 0 during overhaul |
| BM25 implementations | 0 during overhaul |
| Canonical memory stores | 1 SQLite current state + 1 append-only event history |

## Phase order

### Phase 01: Scope reset

Plan: `01_SCOPE_RESET.md`

Delivers:
- benchmark and benchmark-score removal;
- removal of contract-only Skills/Agents/Commands/Team Packs;
- updated canonical identity and scope docs;
- removal of component-count/contract registry assumptions;
- no reduction in current safety invariants.

### Phase 02: State + Work Graph foundation

Plan: `02_STATE_WORK_GRAPH.md`

Delivers:
- Work Graph schema and store;
- graph compiler and readiness logic;
- persisted graph/node/edge lifecycle;
- graph versioning and deterministic state transitions;
- removal of generic Knowledge Graph.

### Phase 03: Policy + Approval

Plan: `03_POLICY_APPROVAL.md`

Delivers:
- approval request/decision schema;
- action, strategic, and exception approvals;
- deterministic scope digests and stale approval invalidation;
- human-only authorization path;
- approval nodes integrated with Work Graph readiness.

### Phase 04: Capability + Execution

Plan: `04_CAPABILITY_EXECUTION.md`

Delivers:
- executable-only capability lifecycle;
- removal of context-only Skill/Agent adapters;
- Work Graph supervisor;
- criticality, reasoning requirement, budget, retry, timeout, concurrency and resume;
- removal of Missions, Teams, old runtime supervisor, loops and old task graph runtime.

### Phase 05: Memory + Verification

Plan: `05_MEMORY_VERIFICATION.md`

Delivers:
- one SQLite-backed memory service;
- one simple deterministic search path with no BM25 or alternate backend;
- immediate write-to-recall coherence;
- unified verification report;
- generated views only;
- removal of atom-store split, FTS/index/query expansion and duplicate guards.

### Phase 06: Approval Advisor + Handoff

Plan: `06_APPROVAL_ADVISOR_HANDOFF.md`

Delivers:
- one operational first-party Approval Advisor with no authorization privilege;
- independent review as Verification Engine mode;
- target-aware handoff from canonical Work Graph + memory + approval state;
- removal of generic codec/context abstractions not required by JSON/JSONL/Markdown.

### Phase 07: CLI + product surface convergence

Plan: `07_CLI_SURFACE.md`

Delivers:
- modular real CLI;
- exactly the approved public/operator command families;
- no slash-command contract directory;
- no tracked component registry that can advertise non-executable behavior;
- developer-only release/claim/lineage helpers removed from runtime package.

### Phase 08: Migration + hardening + final purge

Plan: `08_MIGRATION_HARDENING.md`

Delivers:
- safe legacy memory migration and archive;
- destructive removal of obsolete schema tables only after backup;
- adversarial policy/approval/privacy/state/capability tests;
- fresh-project E2E;
- no dead references to removed architecture;
- no benchmark suite yet.

## Master acceptance gate

All of the following must pass before calling the overhaul complete:

```bash
python -m compileall -q shiroe
pytest -q
python -m shiroe doctor --json
python -m shiroe version
```

Create a temporary fresh project and prove the public lifecycle:

```bash
TMP="$(mktemp -d)"
python -m shiroe init "$TMP" --name smoke --privacy abstract --tier auto
cd "$TMP"
python -m shiroe status --json
python -m shiroe plan --from-json /path/to/fixtures/simple_work_graph.json
python -m shiroe run --graph graph_smoke --dry-run
python -m shiroe memory write --from /path/to/fixtures/simple_memory.json
python -m shiroe memory recall "single node smoke" --json
python -m shiroe verify --graph graph_smoke --json
python -m shiroe handoff human --graph graph_smoke --json
python -m shiroe state verify --json
```

The smoke fixture must be created by Phase 07 under `tests/fixtures/vnext/`; replace `/path/to/fixtures/` with the repository fixture path when executing the gate.

The final repository must also satisfy:

```bash
! test -d skills
! test -d agents
! test -d commands
! test -d team-packs
! test -d missions
! test -d benchmarks
! test -d shiroe/missions
! test -d shiroe/teams
! test -d shiroe/loops
! test -d shiroe/benchmark
! test -f shiroe-registry.json
! grep -R "status.*contract\|status.*experimental" -n shiroe registry docs/architecture AGENTS.md
! grep -R "pattern-to-skill\|fleet-activator\|caveman-handoff\|parent-sync\|skill-router\|budget-governor" -n shiroe AGENTS.md README.md
! grep -R "bm25\|BM25" -n shiroe tests
```

Exceptions are permitted only inside `docs/architecture/REMOVALS.md`, migration notes, or Git history references. The gate command should exclude those paths rather than weakening the rule.

## Verification philosophy

This overhaul is complete when the smaller architecture works. It is not complete because a test count, coverage number, internal score, or benchmark score looks impressive. Benchmarking is a separate post-overhaul program.
