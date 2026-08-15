# ADR-0005: Policy precedence

**Status:** Accepted
**Date:** 2026-07-12

## Context

Shiroe operates at both a global root (`~/.shiroe/`) and a per-project root (`.shiroe/`), and layers in harness defaults, user grants, and runtime safety invariants. Without an explicit, ordered precedence rule, it is ambiguous which layer wins when policies conflict — e.g. whether a project-level allow can override a global deny, or whether a harness default can silently escalate what a project intended to restrict. The architecture plan (§13.3) requires one fixed order, enforced in code, not left to per-feature judgment calls.

## Decision

Fixed 7-layer precedence, highest first:

```
1. Runtime safety invariants
2. Project deny rules
3. Global deny rules
4. Explicit user grants
5. Project defaults
6. Global defaults
7. Harness defaults
```

**A lower-precedence layer may narrow access but may never widen or weaken a higher-precedence safety invariant.** Concretely: a project default cannot override a global deny; a harness default cannot re-enable something a project deny rule blocked; nothing can override a runtime safety invariant.

In addition, a hardcoded list of actions always requires explicit approval regardless of autonomy mode or which policy layer is active — the `ALWAYS_REQUIRE_APPROVAL` set:

- Push
- Merge
- Publish
- External messages
- Destructive deletion
- Secret access
- New unapproved dependencies
- Untrusted capabilities
- Permission escalation
- Budget escalation
- Sandbox escape

This list sits above all seven precedence layers and above all three autonomy modes (`suggest`, `auto-safe`, `policy-bound`) — even `policy-bound` mode, which otherwise executes everything the active policy allows, stops at these boundaries.

## Consequences

- Any permission-engine implementation must resolve policy in this exact layer order and must be covered by tests proving a lower layer cannot widen a higher layer's denial (this is the PR 3 acceptance gate per the architecture plan §20).
- `ALWAYS_REQUIRE_APPROVAL` must be enforced as code (a fixed set checked before dispatch), not documented as a convention agents are expected to remember. No policy configuration, execution policy (`lean`/`balanced`/`assured`), or autonomy mode may remove an item from this list.
- Implementation (global/project precedence resolution, permission schema, autonomy modes, runtime deny gates) lands in PR 3 per the architecture plan §20. This ADR records the decision and the gate; PR 3 is where it becomes enforced code.
- Memory-scope promotion rules (session→project, project→global) inherit this precedence model: promotion requires an evidence-and-privacy gate or explicit approval, and secret/`do_not_store` records are never promoted regardless of any policy layer.
