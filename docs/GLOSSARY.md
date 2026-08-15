# Glossary

| Term | Definition |
|---|---|
| **Canonical state** | SQLite canonical current state in `memory/state/shiroe.sqlite`; ADR-0001 is the storage authority. |
| **Event log** | JSONL canonical append-only history under `memory/events/`; hash-chained and replayable per ADR-0001. |
| **Generated projection** | Markdown generated human-readable view rebuilt from canonical current state and append-only history. It is not authority. |
| **Work Graph** | Persisted execution graph with nodes, edges, attempts, approvals, and state. |
| **Policy stack** | Runtime policy layers loaded from `.shiroe/policy/` and deny/allow precedence rules. |
| **Approval** | Human authorization bound to a deterministic scope digest. |
| **Capability** | An executable adapter-backed unit the runtime can invoke after policy and approval checks. |
| **Execution Supervisor** | Runtime that selects ready Work Graph nodes, checks gates, invokes capabilities, and records attempts. |
| **Doctor** | Semantic runtime health gate exposed by `python3 -m shiroe doctor --json`. |
| **Handoff** | Bounded continuation artifact compiled from canonical runtime state. |
| **Default deny** | The policy fallback when no explicit allow applies. |
| **Connector** | External integration surface. Connectors are disabled by default and never become canonical memory. |
