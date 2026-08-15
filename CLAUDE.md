# CLAUDE.md - Claude Harness Shim

Canonical operating spec: `AGENTS.md`. This file only keeps Claude-specific
boot guidance aligned with the current Shiroe runtime.

## Boot

1. Read `AGENTS.md` and `SOUL.md`.
2. Discover the project root.
3. Run `python3 -m shiroe status --json`.
4. Inspect the relevant Work Graph or memory record through the CLI.
5. Respect policy, approval, capability, privacy, and sharing gates.
6. Use `python3 -m shiroe handoff` for bounded continuation.

## Claude Notes

Use Claude Code tools only inside the permissions granted by the current task
and Shiroe policy. Irreversible actions require explicit user approval.
