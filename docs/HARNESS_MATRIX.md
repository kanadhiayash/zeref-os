# Harness Matrix

Harness files are instruction shims. They do not create enforcement by
themselves. Shiroe enforcement exists only where work is routed through the
runtime CLI, controlled subprocesses, or approved adapters.

| Harness | File | Evidence State | Runtime Surface |
|---|---|---|---|
| Claude Code | `CLAUDE.md` | documented | `python3 -m shiroe` |
| Codex | `CODEX.md` / `AGENTS.md` | documented | `python3 -m shiroe` |
| Cursor | `.cursor/rules/shiroe.mdc` | documented | `python3 -m shiroe` |
| Windsurf | `.windsurfrules` | documented | `python3 -m shiroe` |
| Aider | `.aider.conf.yml.example` | documented | `python3 -m shiroe` |
| Gemini | `GEMINI.md` | documented | `python3 -m shiroe` |
| Llama-family frontends | `LLAMA.md` | documented | `python3 -m shiroe` |

## Boot Sequence

1. Read `AGENTS.md` and `SOUL.md`.
2. Discover the project root.
3. Run `python3 -m shiroe status --json`.
4. Inspect the relevant Work Graph or memory record through the CLI.
5. Respect policy, approval, capability, privacy, and sharing gates.
6. Use `python3 -m shiroe handoff` for bounded continuation.

## Verification

```bash
python3 -m shiroe status --json
python3 -m shiroe doctor --json
python3 -m shiroe state verify --json
```

A harness row is `verified` only after a host-observed session records the boot
sequence and runtime commands with durable evidence.
