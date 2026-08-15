# CODEX.md - Codex Harness Shim

Canonical operating spec: `AGENTS.md`. Codex reads that file natively; this
shim only states the current Shiroe boot sequence.

## Boot

1. Read `AGENTS.md` and `SOUL.md`.
2. Discover the project root.
3. Run `python3 -m shiroe status --json`.
4. Inspect the relevant Work Graph or memory record through the CLI.
5. Respect policy, approval, capability, privacy, and sharing gates.
6. Use `python3 -m shiroe handoff` for bounded continuation.

Do not commit, push, merge, publish, deploy, change credentials, or modify
external infrastructure without explicit user approval.
