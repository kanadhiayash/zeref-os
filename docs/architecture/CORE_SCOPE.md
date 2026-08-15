# Shiroe vNext Core Scope

Shiroe is a local-first governance and continuity plane for persistent AI Work
Graphs. A declared component must be executable or it does not ship.

## Approved Final Inventory

- First-party Skills: 0
- First-party Agents: approval-advisor only when an executable reasoning capability exists
- Runtime engines: State, Work Graph, Policy and Approval, Capability, Execution, Memory, Verification, Handoff and Context
- Public CLI: init, status, plan, run, approve, memory, verify, handoff, doctor
- Operator CLI: policy, capability, state, version
- Non-operational component statuses: forbidden

## Current Transition Rule

This inventory is the approved vNext target. During the phased overhaul, a
command or component is operational only when it resolves to executable Python
and appears in the current CLI or runtime discovery. Target-only interfaces must
not be advertised as currently available.

Work Graph is the sole final execution object. SQLite current state plus the
hash-chained append-only event log is the canonical state model. Generated
Markdown and indexes are rebuildable views, not sources of truth.

Safety, privacy, policy precedence, human approval, capability drift and
revocation, bounded execution, atomic writes, and replay integrity are active.
Private operational transport tooling is excluded from the public product
inventory and does not create public readiness claims.
