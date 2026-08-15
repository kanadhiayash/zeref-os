# LLAMA.md - Llama-Family Harness Shim

Canonical operating spec: `AGENTS.md`. This file applies to local or hosted
Llama-family frontends that can read project instructions and optionally call
the Shiroe CLI.

## Boot

1. Read `AGENTS.md` and `SOUL.md`.
2. Discover the project root.
3. Run `python3 -m shiroe status --json`.
4. Inspect the relevant Work Graph or memory record through the CLI.
5. Respect policy, approval, capability, privacy, and sharing gates.
6. Use `python3 -m shiroe handoff` for bounded continuation.

Shiroe does not supply local inference. Any model runtime remains an external
harness choice, subject to the same policy and approval gates.
