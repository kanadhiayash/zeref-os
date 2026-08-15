# GEMINI.md - Gemini Harness Shim

Canonical operating spec: `AGENTS.md`. This file keeps Gemini-oriented
sessions aligned with Shiroe's executable runtime.

## Boot

1. Read `AGENTS.md` and `SOUL.md`.
2. Discover the project root.
3. Run `python3 -m shiroe status --json`.
4. Inspect the relevant Work Graph or memory record through the CLI.
5. Respect policy, approval, capability, privacy, and sharing gates.
6. Use `python3 -m shiroe handoff` for bounded continuation.

Large context windows do not change authority: generated Markdown can aid
reading, but canonical state is inspected through the runtime.
