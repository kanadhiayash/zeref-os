# Harness Translation Map

`AGENTS.md` is the canonical instruction file. Harness-specific files are thin
shims that point back to the same runtime boot sequence.

| Harness | File |
|---|---|
| Claude Code | `CLAUDE.md` |
| Codex | `CODEX.md` and `AGENTS.md` |
| Cursor | `.cursor/rules/shiroe.mdc` |
| Windsurf | `.windsurfrules` |
| Aider | `.aider.conf.yml.example` |
| Gemini | `GEMINI.md` |
| Llama-family frontends | `LLAMA.md` |

## Required Boot

1. Read `AGENTS.md` and `SOUL.md`.
2. Discover the project root.
3. Run `python3 -m shiroe status --json`.
4. Inspect relevant Work Graph or memory state through the CLI.
5. Respect policy, approval, capability, privacy, and sharing gates.
6. Use `python3 -m shiroe handoff` for bounded continuation.

Do not duplicate canonical instructions inside host-specific files.
