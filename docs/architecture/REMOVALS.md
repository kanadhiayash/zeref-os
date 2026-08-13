# Shiroe vNext Removals

This ledger records product surfaces deliberately removed by the vNext
overhaul. Git history remains the archive for deleted implementation details.

## Phase 01

- Current benchmark program, scorecard, external harness, and benchmark-only
  BM25 tooling. Benchmarking may be rebuilt later from the new public APIs.
- Declaration-only first-party component directories and root component
  registry. Product components must resolve to executable runtime code.
- Development lineage research runtime. Release provenance and Git history are
  retained as separate operational concerns.

Runtime retrieval remains transitional until Phase 05 replaces it with the
approved deterministic token-overlap search. Mission and Team execution remains
transitional until Phase 04 replaces it with Work Graph supervision.

## Phase 02

- Generic Knowledge Graph runtime and projection exports. Work Graph is the
  single operational graph model. Memory relationships remain canonical rows in
  `memory_relations`, not a separate graph abstraction.

## Phase 04

- Legacy Missions, Team Pack compilation, loop runtime, old runtime supervisor,
  execution policies, and task graph runtime. Operational execution now flows
  through executable capability adapters and the bounded Work Graph supervisor.

## Phase 05

- BM25, index rebuilds, query expansion, agent retrieval sessions, atom-store
  persistence, memory triples/graph projections, memory-specific cost routing,
  refinement reports, and the public guard package. Canonical memory now flows
  through SQLite records, deterministic token-overlap recall, generated views,
  and the unified Verification Engine.

## Phase 06

- Generic context packets and codec registry/runtime packages. Handoff now
  reads canonical state (Work Graph, approval, memory, verification) directly
  and renders JSON and Markdown views from it — the views remain generated,
  not canonical. Obsolete schema tables remain until the Phase 08 backup-backed
  destructive migration.

## Phase 07

- Generated runtime registry files and `shiroe.registry` generation code.
  Active CLI commands and adapters are discovered from executable Python
  registrations and CapabilityStore state instead of tracked inventories.

## Phase 08

- `shiroe/core/deprecations.py` runtime alias resolver (`resolve_alias`,
  `DEPRECATED_ALIASES`). Replaced by the explicit
  `shiroe/compat/legacy_identity.py` boundary; no runtime callers remained.
- `docs/wiki/Team-Packs.md` and `docs/wiki/Pattern-Detection.md` active-nav
  wiki pages. The surfaces they described were retired in Phases 04 and 05
  respectively; git history remains the archive.
- `tests/test_canon_consistency.py` and
  `tests/invariant/test_no_contract_surfaces.py`. Superseded by
  `tests/invariant/test_no_dead_surface_references.py` and
  `tests/test_canonical_state_contract.py`, which enforce the vNext
  active-surface invariants without depending on removed abstractions.
- The vNext one-cycle alias rows in `docs/DEPRECATIONS.md` covering the
  removed component names (capability-resolver / capability-prober /
  capability-manager and the execution-policy / reasoning-class tier
  renames). The aliased replacements themselves were retired in earlier
  phases; only the pre-rename identity boundary rows remain.
- CI workflow references to removed CLI surface: the
  `shiroe audit-privacy` step in the `privacy` job (retired in Phase 07;
  the sibling grep-based `Scan repo for committed secrets` step still
  enforces the credentials-must-not-commit invariant), and the entire
  `release-check` job (its only step invoked `python3 -m shiroe.cli
  release check`; the `shiroe/release/` package was retired in Phase 07).
  A dedicated release-readiness gate is a post-vNext follow-up.

## H4.3 (post-vNext hardening 2026-08-13) — orphan removals

Four modules with zero importers across `shiroe/` and `tests/` were
deleted under the H4.3 prove-or-delete rule:

- `shiroe/audit/traces.py` — 3-line `write_trace` helper; nothing called
  it after the audit/trace redesign.
- `shiroe/memory/render.py` — CLI-compat rendering wrapper superseded
  by `shiroe.memory.views` and used only by the pre-Phase-07 CLI.
- `shiroe/routing/policy.py` — `DEFAULT_POLICY` static config; the
  gateway does not consult it and no other module imports it.
- `shiroe/yaml_subset.py` — 160-line hand-rolled YAML parser retained
  for the retired mission / execution-policy files. No caller remains.

None are compatibility-migration files (per H4.3's "do not delete
historical compatibility migrations" rule); git history remains the
archive.
