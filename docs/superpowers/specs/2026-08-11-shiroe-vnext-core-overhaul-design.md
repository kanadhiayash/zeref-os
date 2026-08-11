# Shiroe vNext Core Overhaul Design

**Source baseline:** `kanadhiayash/shiroe` at `520dca437fa2d9f0349a26630666f1dd5221f919`  
**Design date:** 2026-08-11  
**Status:** Approved direction, implementation not started

## Objective

Rebuild Shiroe as a local-first governance and continuity plane for persistent AI Work Graphs. Shiroe owns graph state, policy, approvals, capability control, execution supervision, verification, memory, and cross-harness continuation. It does not ship speculative surfaces, markdown-only features, benchmark machinery, or parallel orchestration abstractions.

## Product boundary

Shiroe exists to answer seven questions:

1. What work is being attempted?
2. What must happen before that work may execute?
3. Which approved capability may perform it?
4. What evidence proves the result?
5. What requires human approval?
6. What durable state should survive the current harness or model?
7. How does the same work continue elsewhere without restating decisions?

Anything that cannot map directly to those questions is outside Local Core.

## Non-negotiable architecture rules

1. **One canonical execution object:** Work Graph.
2. **One canonical state store:** `memory/state/shiroe.sqlite` plus hash-chained append-only events.
3. **One canonical memory write path:** proposal -> verification -> canonical write -> event -> generated views.
4. **No component contracts:** a declared component is executable or it does not ship.
5. **No `contract` or `experimental` product status:** active surfaces may be `runtime` or `adapter` only.
6. **No first-party standalone Skills:** Local Core ships zero Skills. External Skills may be treated as capabilities only when an adapter can actually invoke them.
7. **No markdown-only Agents or Commands:** first-party agent behavior must be Python-backed and callable. Public commands are real CLI commands.
8. **No Team Packs, Missions, Seats, or parallel orchestration model:** Work Graph replaces them.
9. **No generic Knowledge Graph:** Work Graph handles work; memory relations handle knowledge relationships.
10. **No current benchmark stack in active scope:** remove current internal scorecard, external harness, benchmark program, and BM25 benchmark tooling. Rebuild benchmarking later from a clean boundary.
11. **No BM25 in the initial vNext Memory Engine:** use one simple deterministic retrieval implementation with no alternate ranking backend.
12. **Hardening continues during the overhaul:** preserve safety, atomicity, privacy, approval, capability, and replay invariants.
13. **No public success claim without executed evidence:** docs describe only operational surfaces.
14. **No external push, merge, publish, or deployment without explicit human approval.**

## Final active product surface

### Runtime engines

| Engine | Responsibility |
|---|---|
| State Engine | SQLite schema, migrations, event chain, replay, generated state projections |
| Work Graph Engine | Work orders, nodes, edges, readiness, graph versioning and lifecycle |
| Policy & Approval Engine | policy precedence, autonomy, approval requests, scope digests, authorization records |
| Capability Engine | discovery, inspection, approval, lifecycle, health, resolution, invocation |
| Execution Engine | criticality, reasoning requirement, budget, retries, timeout, concurrency, supervision |
| Memory Engine | durable records, sources, relations, recall, supersession, contradiction candidates, views |
| Verification Engine | privacy, evidence, unsupported claims, contradictions, write validation, independent review requests |
| Handoff & Context Engine | minimal target-aware continuation packet from active graph and canonical state |

### First-party agents

Only one first-party agent is allowed initially:

- `approval_advisor`: semantic recommendation over a pending approval request. It may recommend `approve`, `reject`, `revise`, or `defer`. It may never authorize an action, mutate policy, mutate the Work Graph, or execute the approved action.

The Approval Advisor is registered as operational only when an approved reasoning capability is available. Without such a capability, the Policy & Approval Engine remains fully operational and human approvals still work.

Independent review is not a permanent Agent identity. It is a Verification Engine mode that may invoke a separate approved reasoning capability when required.

### First-party Skills

**Zero.**

Former skill responsibilities move as follows:

- project setup -> `shiroe init`
- wiki maintenance -> generated State/Memory views
- contradiction resolution -> Memory + Verification
- privacy abstraction -> Verification/Handoff
- memory import/export -> State maintenance
- budget governance -> Execution Engine
- skill routing -> Capability Engine
- prompt normalization -> Work Graph planning
- handoff compile -> Handoff Engine
- evidence grading -> Verification Engine

### Public CLI

Everyday commands:

```text
shiroe init
shiroe status
shiroe plan
shiroe run
shiroe approve
shiroe memory
shiroe verify
shiroe handoff
shiroe doctor
```

Operator commands:

```text
shiroe policy
shiroe capability
shiroe state
shiroe version
```

There is no markdown `commands/` contract directory in the final tree.

## Work Graph model

Allowed node kinds:

- `task`
- `decision`
- `approval`
- `review`

Graph execution uses dependencies plus bounded retry/iteration metadata. Joins are represented by multiple predecessors. Loops are represented by retry/iteration policy, not a separate orchestration subsystem.

A Work Node declares requirements, not agent characters:

```json
{
  "id": "node_release_review",
  "kind": "review",
  "objective": "Verify release candidate against declared success criteria",
  "requires": ["repository.read", "tests.execute"],
  "risk": "high",
  "approval_required": false,
  "independent_review": true,
  "expected_outputs": ["verification_report"],
  "retry": {"max_attempts": 1}
}
```

## Approval model

Approval types:

- `action`: irreversible or externally visible operation
- `strategic`: user-selected direction or boundary in the Work Graph
- `exception`: explicit override of a warning, budget threshold, or evidence deficiency

Approval statuses:

- `pending`
- `approved`
- `rejected`
- `revise`
- `deferred`
- `stale`

Every approval is bound to a deterministic `scope_digest`. A changed node, artifact set, action parameters, or policy-relevant input invalidates the old approval and changes status to `stale`.

No LLM output can create an authorization record. Only the approval service called by an explicit human action may write an approved decision.

## Memory model

Canonical memory lives in SQLite. The event log is the replayable history. Markdown is generated output only.

The first vNext search algorithm deliberately stays simple:

1. normalize query and candidate text with NFKC + lowercase;
2. filter by status/type/scope first;
3. score by unique query-token overlap across title, claim, summary, and tags;
4. current valid records outrank superseded, archived, or temporally invalid records;
5. higher token overlap wins;
6. newer `updated_at` breaks ties;
7. record id is the final stable tie-breaker;
8. zero overlap means abstain.

No SQLite FTS/BM25, JSONL BM25 fallback, query expansion, or alternate backend exists in this version.

## Verification model

The Verification Engine exposes one report with checks:

- `privacy`
- `evidence`
- `claims`
- `contradictions`
- `write`
- optional `independent_review`

Each check returns `pass`, `warn`, or `block`. A write or Work Graph transition declares which checks are mandatory. Verification does not silently convert warnings into success claims.

## Capability model

A capability ships only when it can be invoked through an adapter. Context-only adapters are not active capabilities.

Initial acceptable adapter classes:

- embedded CLI/script
- repository tool
- fully implemented MCP tool/server invocation
- model/provider/harness adapter with an actual invocation path

Current `generic-skill` and markdown-only `agent` adapters are removed. The existing MCP adapter must either implement the declared operational action or be removed until it does.

## Migration rule

User memory is never silently discarded. Legacy state may be imported and archived, but runtime reads and writes converge on the new canonical path.

Legacy execution state, team state, benchmark state, and obsolete generated registries may be dropped after a pre-migration backup because they are development/runtime scaffolding, not user-authored memory.

## Test model

Final test layout:

```text
tests/
  unit/
  invariant/
  integration/
  e2e/
```

No benchmark score is part of the overhaul acceptance gate.

Invariant tests preserve the hardest current guarantees:

- policy denies cannot be widened by lower-precedence grants;
- always-approval actions cannot bypass human approval;
- changed approval scope becomes stale;
- an agent cannot authorize itself;
- capability digest drift/revocation blocks invocation;
- timeouts and retries are bounded;
- concurrent canonical writers cannot silently lose state;
- event hash-chain corruption is detected;
- privacy and credential bypass cases block;
- Work Graph dependencies, joins, retries, resume, and deadlock handling are deterministic;
- memory write is immediately recallable;
- generated Markdown can be deleted and rebuilt from canonical state;
- handoff can reconstruct active graph state without relying on generated Markdown.

## Explicitly removed architecture

- `skills/`
- markdown `agents/`
- markdown `commands/`
- `team-packs/`
- `missions/`
- `shiroe/missions/`
- `shiroe/teams/`
- old `shiroe/runtime/` team supervisor
- `shiroe/loops/`
- generic `shiroe/graph/knowledge.py`
- generic `shiroe/graph/exports.py`
- old task-graph runtime after Work Graph replacement is operational
- current BM25/FTS/JSONL ranking stack
- current query expansion
- current benchmark tree and benchmark program
- current lineage benchmark/research machinery from runtime
- contract/experimental registry entries
- generic codec registry and formats not required by canonical JSON/JSONL/Markdown output
- pattern observation and skill-generation architecture
- parent sync architecture

## Success condition

Shiroe vNext is ready for later benchmark work only when a fresh project can:

1. initialize;
2. create and persist a Work Graph;
3. resolve only approved executable capabilities;
4. execute safe nodes;
5. pause correctly for human approval;
6. invalidate stale approvals;
7. verify outputs;
8. persist and immediately recall durable memory;
9. resume a partially completed graph;
10. hand the same active graph to another target;
11. rebuild generated views from canonical state;
12. pass adversarial policy, privacy, concurrency, and state-replay tests;
13. expose no contract-only, experimental, or dead public surface.
