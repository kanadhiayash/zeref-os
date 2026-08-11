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
