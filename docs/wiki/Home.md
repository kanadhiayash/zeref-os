# Shiroe

Shiroe is a local-first governance and continuity plane for AI-assisted work.
It gives a project a durable Work Graph, canonical state, deterministic memory,
explicit approval boundaries, and handoff artifacts that survive model and
harness changes.

## Read these first

- [[Architecture]]
- [[Memory-Model]]
- [[Privacy-Model]]
- [[Installation]]
- [[FAQ]]

## What the runtime does

| Surface | Behavior |
|---|---|
| Work Graph | Persists nodes, dependencies, readiness, attempts, and lifecycle state. |
| Policy and Approval | Enforces denial precedence and human-only scope-bound approval. |
| Capability | Runs only executable, digest-current capabilities through adapters. |
| Execution | Supervises bounded graph runs and records attempts. |
| Memory | Writes canonical SQLite records and hash-chained events. |
| Verification | Centralizes privacy, evidence, fact, contradiction, semantic, write, and graph checks. |
| Handoff | Renders scrubbed JSON and Markdown views over canonical state. |

## Operating posture

- Shiroe does not perform inference. The harness calls the model.
- Markdown memory files are generated views, not authoritative state.
- Public claims require executed evidence.
- Connector sharing is off by default.

## Where to start

| If you want to... | Read |
|---|---|
| Install and verify | [[Installation]] |
| Understand the system | [[Architecture]] then [[Memory-Model]] |
| Lock down privacy first | [[Privacy-Model]] |
| Get a direct answer | [[FAQ]] |

---

[`README`](https://github.com/kanadhiayash/shiroe) ·
[`AGENTS.md`](https://github.com/kanadhiayash/shiroe/blob/main/AGENTS.md) ·
[`SECURITY.md`](https://github.com/kanadhiayash/shiroe/blob/main/SECURITY.md)
