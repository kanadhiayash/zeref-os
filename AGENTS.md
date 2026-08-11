<!-- privacy-audit: allow-file "Canonical operational specification; references privacy pattern classes as documentation." -->

# AGENTS.md - Shiroe Canonical Operational Spec

Shiroe is a local-first governance and continuity plane for persistent AI Work
Graphs. This file defines runtime behavior. Storage authority remains
`docs/adr/ADR-0001-canonical-store.md`.

## Session Boot

1. Read `SOUL.md`.
2. Read `config/PROJECT.md`.
3. Read `PRIVACY.md`, `REDACT.md`, and `SHARING_POLICY.md` before writes or
   external output.
4. Inspect canonical state with the executable CLI. Do not infer state from
   generated Markdown.
5. Report facts, assumptions, unknowns, risks, and conflicts separately.

## Product Boundary

Every declared component must be executable. Shiroe ships no declaration-only
product components and no `contract` or `experimental` product status.

The approved vNext runtime consists of State, Work Graph, Policy and Approval,
Capability, Execution, Memory, Verification, and Handoff and Context engines.
The sole conditional first-party agent is `approval_advisor`, which may offer a
recommendation only when an approved reasoning capability is executable. It can
never authorize, mutate policy or graph state, or execute an action.

The final public CLI target is `init`, `status`, `plan`, `run`, `approve`,
`memory`, `verify`, `handoff`, and `doctor`. Operator commands are `policy`,
`capability`, `state`, and `version`. During the phased overhaul, only commands
shown by `python -m shiroe --help` are operational. Documentation must not
present target-only commands as available before their implementation phase.

## Canonical State

- `memory/state/shiroe.sqlite` holds current state.
- `memory/events/<yyyy>/<mm>/events.jsonl` is the hash-chained append-only
  replay history.
- Markdown pages and indexes are generated projections and are not authoritative.
- State must remain rebuildable from the event log.
- Human-authored legacy memory is migrated and archived, never silently lost.

## Governance

- Policy denies cannot be widened by lower-precedence grants.
- Only an explicit human action can create an authorization record.
- Approval is bound to a deterministic scope digest and becomes stale when its
  scope changes.
- Capabilities must be executable through an adapter. Drift or revocation blocks
  invocation.
- Retries, iteration, timeout, and concurrency are bounded.
- Contradictions surface for human arbitration and are never silently resolved.
- Every canonical write passes privacy, evidence, claim, contradiction, and
  write validation required by its operation.

## Privacy And Sharing

`PRIVACY.md`, `REDACT.md`, and `SHARING_POLICY.md` govern all writes and external
transmission. Default privacy mode is `abstract`; all connectors are disabled by
default. No connector is installed or enabled on the user's behalf.

## Execution Rules

- Read before editing and touch only required scope.
- Use test-first development for behavior changes.
- Preserve policy, privacy, capability, concurrency, approval, replay, and
  atomic-write invariants through migrations.
- Never claim readiness or comparative success without executed evidence.
- Require explicit human approval before commit, push, issue or pull-request
  writes, merge, deploy, publish, send, schedule, destructive migration,
  credential changes, or external infrastructure changes.
- Never push, merge, publish, or deploy as an implicit completion step.

## Harnesses

Harness-specific files defer to this document. Shiroe is not itself a harness,
hosted service, persona, or bundled connector collection.
