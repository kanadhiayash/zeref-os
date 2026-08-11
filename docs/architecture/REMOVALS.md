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
  compiles canonical JSON/Markdown directly from Work Graph, approval, memory,
  and verification state. Obsolete schema tables remain until the Phase 08
  backup-backed destructive migration.

## Phase 07

- Generated runtime registry files and `shiroe.registry` generation code.
  Active CLI commands and adapters are discovered from executable Python
  registrations and CapabilityStore state instead of tracked inventories.
