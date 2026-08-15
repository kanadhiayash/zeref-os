<!-- privacy-audit: allow-file "Privacy policy defines sensitive classes and transmission rules." -->
---
mode: abstract
network_scope: device-only
connectors_default: false
external_transmission: false
---

# PRIVACY.md

`mode` controls how content is persisted. `network_scope` controls whether
runtime network access is denied, limited to tailnet transport, or allowed for
explicitly approved external destinations.

## Modes

- `exact`: store exact content after policy approval.
- `abstract`: default; scrub sensitive content before persistence or output.

## Network Scope

- `device-only`: default; no outbound network access.
- `tailnet`: permits policy-approved Tailscale transport only.
- `external`: permits policy-approved external connector access.

## Rules

- Canonical state is local: `memory/state/shiroe.sqlite` plus the hash-chained
  event log.
- Connectors are disabled by default and never become state authority.
- Every external transmission requires policy allowance, redaction, and any
  required human approval.

Related files: `REDACT.md`, `SHARING_POLICY.md`, and `.shiroe/policy/*.json`.
