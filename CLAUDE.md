# CLAUDE.md — Claude harness shim (Shiroe)

**Canonical spec: `AGENTS.md`** — read it first. This file only adds Claude-specific notes.

## Claude-specific

- Use Claude Code's Skill tool to invoke skills as `shiroe:<skill-name>` (post-install).
- Slash commands resolve under `/shiroe:<command>` namespace.
- Sub-agents (Task tool) are not required — Shiroe uses lightweight markdown agents.
- Prefer Haiku for `shiroe-runtime` writes; Sonnet for `project-setup` interview; Opus only when the caller explicitly requests it.
- Per-harness quirks live in `config/claude-overrides.md`.

## First action every session

Identical to AGENTS.md §"First action every session":
1. Read `config/PROJECT.md`
2. Read `memory/hot.md` (≤500 words)
3. Read `memory/index.md` if hot insufficient
4. Read `PRIVACY.md` (root) — before any write or tool use
5. Read `REDACT.md` (root) — before any external output
6. Tail last 3 entries of `memory/patterns/PATTERNS.jsonl`
7. Report state

## Safety

See `references/shiroe-safety-principles.md`. Irreversible actions always require explicit user confirmation.
