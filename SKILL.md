---
name: shiroe
version: 3.0.0-alpha.1
description: Shiroe is a local-first governance and continuity runtime for AI-assisted work graphs.
---

# Shiroe

Shiroe is a local-first governance and continuity plane. It provides canonical
state, Work Graph execution, policy and approval gates, capability invocation,
verification, memory, and bounded handoff through executable runtime commands.

Shiroe is not a hosted service, harness persona, bundled connector collection,
or source of model inference.

## Runtime Entry

Use the installed CLI as the executable surface:

```bash
python3 -m shiroe --help
python3 -m shiroe status --json
python3 -m shiroe doctor --json
```

Public commands are `init`, `status`, `plan`, `run`, `approve`, `memory`,
`verify`, `handoff`, and `doctor`. Operator commands are `policy`,
`capability`, `state`, and `version`.

## Harness Boot

1. Read `AGENTS.md` and `SOUL.md`.
2. Discover the project root.
3. Run `python3 -m shiroe status --json`.
4. Inspect the relevant Work Graph or memory record through the CLI, not
   generated Markdown as authority.
5. Respect current policy, approval, capability, privacy, and sharing gates.
6. Use `python3 -m shiroe handoff` for bounded continuation.

## Authority

`AGENTS.md` is the canonical operational specification.
`docs/adr/ADR-0001-canonical-store.md` defines storage authority. Markdown
projections are readable context, not canonical state.
