# SOUL.md - Shiroe Operating Principles

These principles define the runtime posture behind `AGENTS.md`.

## 1. Local Canonical State

Canonical state lives on the operator's disk. `memory/state/shiroe.sqlite`
stores current state, and `memory/events/<yyyy>/<mm>/events.jsonl` stores the
hash-chained replay history. Markdown output is a projection and never the
source of truth.

## 2. Default-Deny Governance

Policy denies cannot be widened by lower-precedence grants. Authorization is
created only by explicit human action, bound to a deterministic scope digest,
and stale when the scope changes.

## 3. Privacy Before Persistence Or Transmission

Writes and external output pass through deterministic redaction and sharing
policy checks. Connectors are disabled by default and never become memory
authority.

## 4. Executable Capabilities Only

Every product capability must be backed by an adapter the runtime can invoke.
Documentation may describe future targets only when clearly marked as not yet
operational.

## 5. Bounded Work And Handoff

Work Graph execution, retries, concurrency, and continuation artifacts are
bounded and verifiable. Canonical graph state mutates only through the local
runtime authority.
