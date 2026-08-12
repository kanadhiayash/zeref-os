<!-- privacy-audit: allow-file "Llama harness stub references AGENTS.md + example paths." -->

# LLAMA.md — Llama-family harness shim (Shiroe)

**Canonical spec: `AGENTS.md`** — read it first. This file only adds
Llama-specific notes (Ollama, llama.cpp, llamafile, vLLM, LM Studio,
Open WebUI, and any harness that fronts a Llama-family model).

## Llama-specific

- These harnesses generally have no built-in concept of "skill" or
  "agent". Shiroe still works — the memory layer is plain Markdown and
  reading-order is enforced by `AGENTS.md`.
- Recommended invocation: point the model's system prompt at `AGENTS.md`
  via a wrapper script or the harness's prompt-template feature.
- For tool-calling harnesses (Open WebUI, vLLM with function calling),
  expose `shiroe` as a subprocess tool: `python3 -m shiroe status`,
  `python3 -m shiroe memory write …`, `python3 -m shiroe doctor --json`.

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

See `references/shiroe-safety-principles.md`. Irreversible actions always
require explicit user confirmation. Local Llama harnesses do **not**
exempt you from this rule — confirmation prompts must still surface in
the wrapping UI.
