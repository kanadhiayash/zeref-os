# Shiroe Safety Principles

1. Canonical writes go through the runtime service path.
2. Event history is append-only and hash-chained.
3. Privacy redaction runs before persistence or external output.
4. Policy is default deny unless an explicit allow applies.
5. Only explicit human action creates authorization.
6. Canonical graph state mutates only through the local runtime authority.
7. Work packages, artifacts, and receipts are digest-verified.
8. Connectors are disabled by default and never become authority.
9. Unsupported claims stay labeled as unknown or assumption.
10. Destructive operations require explicit user approval.

Use `python3 -m shiroe doctor --json` and `python3 -m shiroe state verify --json`
as executable safety checks.
