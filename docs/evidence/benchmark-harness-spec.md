<!-- privacy-audit: allow-file "Frozen benchmark methodology spec. No credentials, no user data." -->

# Benchmark Harness Spec (Frozen Methodology)

Frozen, immutable methodology for the Shiroe local benchmark. This document is **evidence and
methodology only** — Shiroe deliberately ships no benchmark product surface (no `benchmarks/`
package, no `shiroe/benchmark`, no `benchmark` CLI command; enforced by
`tests/invariant/test_no_benchmark_surface.py`). Benchmark entry remains **CLOSED** (owner-parked
private operational qualification); see `docs/evidence/benchmark-entry-audit.md`.

## Freeze identity

| Field | Value |
|---|---|
| candidate_sha | `3ecce2a5b8ad9ab2b1eff71c2125261e766b76c7` (hardened tree; this doc's SHA-fill lands in the freeze commit) |
| benchmark_version | `1.0.0` |
| frozen_at | 2026-08-18 |
| entry_status | CLOSED (do not run before local gate green **and** owner re-opens qualification) |

## Environment (measurement host of record)

| Field | Value |
|---|---|
| python | 3.14.4 |
| os | Darwin 25.3.0 (macOS, arm64) |
| cpu | 10 cores (arm64) |
| memory | 16 GiB |
| runtime dependencies | none (stdlib-only; `pyproject.toml` `dependencies = []`) |
| optional extras | llm, duckdb, yaml, tokenizer (excluded from the core benchmark) |

## Execution parameters

| Field | Value |
|---|---|
| random_seed | 0 (routing classifier is deterministic — no RNG in the scored path; seed pinned for any future sampling) |
| warmup_count | 1 |
| repetition_count | 3 |
| per-task timeout | 5 s (classifier); 600 s (any full-suite gate step) |
| raw_output location | `docs/evidence/benchmark-runs/<benchmark_run_id>.json` (append-only; never overwritten) |

## Corpora (frozen)

| Corpus | File | Size | Role |
|---|---|---|---|
| routing_heldout v1 | `tests/fixtures/routing_corpus_heldout.jsonl` | 68 tasks | blind held-out; authored before reading the classifier |
| routing_internal v1 | `tests/fixtures/routing_corpus.jsonl` | 48 tasks | internal-consistency regression |

Row schema: `{id, task, label, rationale, ambiguous, debatable}`. Labels: LOW / MEDIUM / HIGH /
CRITICAL. Corpora are frozen at freeze time; do **not** tune against the held-out corpus.

## Categories (machine-scored)

A Work-Graph correctness · B state integrity · C memory correctness · D policy & approval ·
E capability execution · F verification · G handoff · H privacy/security · I routing ·
J performance · K resource efficiency · L recovery/restart · M CLI correctness.

**Excluded (parked, out of scope):** live Node0/Node1 execution, live Tailscale connectivity,
cross-device throughput.

## Scoring

**Routing (category I):** accuracy; precision/recall/F1 per class; confusion matrix; under-route rate;
over-route rate; CRITICAL recall; unnecessary-HIGH and unnecessary-CRITICAL rates.
- Definitions: under-route = predicted class strictly less severe than label; over-route = strictly
  more severe.
- Historical comparison points only (not current results): accuracy ~72.1%, CRITICAL recall 100%,
  under-route 0%, over-route ~27.9%, unnecessary-frontier ~13.2%.

**Safety invariants (hard, not averaged):**
- CRITICAL under-route rate = **0** (a single CRITICAL under-route fails the safety gate).
- Security/privacy expected-outcome correctness = **100%** (a single authorization/redaction bypass
  keeps benchmark entry CLOSED).

**Success thresholds (open-gate preconditions):** all local gate rows green (`release_ready.py`
PASS 14/14, 3× clean pytest, critical coverage ≥90% line / ≥80% branch); CRITICAL under-route = 0;
security/privacy correctness = 100%.

**Failure thresholds:** any CRITICAL under-route; any authorization/redaction bypass; any local gate
row red. Efficiency goal (non-gating): reduce over-route rate without lowering CRITICAL recall.

## Run receipt (machine-readable, append-only)

```json
{
  "benchmark_run_id": "<uuid>",
  "candidate_sha": "<frozen sha>",
  "benchmark_version": "1.0.0",
  "environment": { "python": "3.14.4", "os": "Darwin 25.3.0 arm64", "cpu": "10", "memory_gib": 16 },
  "started_at": "<iso>",
  "finished_at": "<iso>",
  "raw_results": {},
  "aggregate_results": {},
  "failures": [],
  "skips": []
}
```

Raw benchmark data must never be overwritten. Freeze this spec before any benchmark run begins.
