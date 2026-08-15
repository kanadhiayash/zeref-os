# Stack

Shiroe is the local governance and continuity runtime. Other tools may be used
alongside it, but they are not bundled and are not authority unless an
executable Shiroe adapter routes work through policy and approval gates.

## Runtime Layers

- Canonical state: SQLite and hash-chained JSONL.
- Work Graph: dependency-ordered execution state.
- Policy and approval: default-deny checks and human authorization records.
- Capability: adapter-backed executable invocation.
- Verification: graph, memory, state, and doctor checks.
- Handoff: bounded continuation artifacts.

## External Tools

External harnesses and connectors remain operator choices. Shiroe does not
install, enable, or claim control over them unless the active runtime path can
prove it.
