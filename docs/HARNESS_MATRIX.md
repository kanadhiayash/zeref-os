# Harness Matrix — Shiroe

Portability evidence per harness. Evidence-state (not ✅ marks) per [SHR-AUDIT-022] +
D7 (ratified 2026-07-10): only harnesses with a host-observed boot log are `verified`.
Everything else is `documented-only` until a host log ships.

Evidence states:

- **verified** — host executed the boot sequence AND memory-read AND handoff AND privacy-scan
  during a recorded session; log path cited.
- **partially-verified** — one or two of the four stages executed; others documented-only.
- **documented-only** — stubs shipped and CLI wiring exists, but no host log observed.
- **unsupported** — the host cannot boot Shiroe reliably; explicit exclusion.
- **blocked** — host unavailable in the audit environment; state unknown.

| Harness | Stub | Boot | Memory read | Tool surface | Handoff | Evidence state | Log reference |
|---|---|:---:|:---:|:---:|:---:|:---|:---|
| Claude Code | `CLAUDE.md` | yes | yes | yes | yes | **verified** | verified against a host log; record maintained outside this repository |
| Codex | `CODEX.md` | doc | doc | via `python3 -m shiroe` | doc | **documented-only** | stubs present; no host log |
| Cursor | `.cursor/rules/shiroe.mdc` | doc | doc | via `python3 -m shiroe` | doc | **documented-only** | stubs present; no host log |
| Windsurf | `.windsurfrules` | doc | doc | via `python3 -m shiroe` | doc | **documented-only** | stubs present; no host log |
| Aider | `.aider.conf.yml.example` | doc | doc | via `python3 -m shiroe` | doc | **documented-only** | stub `.example` only — user must copy to `.aider.conf.yml` |
| Gemini CLI / Antigravity | `GEMINI.md` | doc | doc | via `python3 -m shiroe` | doc | **documented-only** | stubs present; no host log |
| Llama family (Ollama, vLLM, Open WebUI) | `LLAMA.md` | doc | doc | via `python3 -m shiroe` | doc | **documented-only** | system-prompt wrapper approach; requires host testing |
| Hermes, Amp, Zed, Perplexity | none (reads `AGENTS.md`) | doc | doc | via `python3 -m shiroe` | doc | **documented-only** | no dedicated stub |

## Three different things, often confused (issue #149)

"Supported" has meant three unrelated things in this repo. They are listed
separately here because a reader could not otherwise tell which one applies.

**1. Handoff targets** — a Python module that formats a session handoff for
that destination. Source of truth: `shiroe/handoff/`.

`claude` · `codex` · `cursor` · `github` · `human`

**2. Harness adapters** — a Python module that emits harness-shaped context.
Source of truth: `shiroe/adapters/harnesses/`.

`claude_code` · `codex` · `gemini_cli` · `hermes` · `kimi_code` · `odysseus`

**3. Stub-only integrations** — a rules or config file pointing the harness at
`AGENTS.md`. No Python module; the harness reads the spec as context and is
asked, not compelled, to follow it.

`.windsurfrules` (Windsurf) · `.aider.conf.yml.example` (Aider)

The three lists genuinely differ. Cursor is a handoff target with no adapter.
Gemini CLI, Hermes, Kimi, and Odysseus are adapters with no handoff target.
Windsurf and Aider are neither — they are context-only, which is the weakest
tier and should never be described as equivalent to the others.

The table below records *evidence state* — whether a host was observed
booting — which is a separate axis again. A harness can have an adapter and
still be `documented-only` because nobody has run it and kept the log.


## Boot-sequence verification (per [AGENTS.md](../AGENTS.md) §0)

Recorded in the Shiroe project memory of the harness under `memory/patterns/PATTERNS.jsonl`
as a `harness-boot-verified` event. Fields:

```
{"ts": "...", "harness": "<name>", "version": "<host-version>",
 "steps_verified": ["soul", "project", "hot", "index", "privacy", "redact", "memory", "patterns"],
 "signature": "sha256:<log-hash>"}
```

An entry with all 8 steps + a signed log promotes the harness to `verified`.

## Verification commands (per host)

```bash
# in any harness, from your project root:
python3 scripts/harness-probe.py                       # file-presence check (does not prove boot)
python3 -m shiroe status --json                        # discovery + memory read
python3 -m shiroe memory write --from smoke.json       # single-writer + scrub + audit log
python3 -m shiroe doctor --json                        # runtime health
python3 -m shiroe handoff --graph <graph-id> claude    # cross-model packager
```

The `harness-probe.py` file-presence check alone does NOT constitute a `verified` state
per D7 — a `verified` row requires the four smoke commands executed in the host's
terminal pane, with the PATTERNS.jsonl `harness-boot-verified` event as evidence.

## How to add a new harness

1. Create the stub file (`<HARNESS>.md` or host-specific rule file).
2. Boot the host in a Shiroe-initialized project.
3. Run the four smoke commands above.
4. Verify a `harness-boot-verified` event lands in `memory/patterns/PATTERNS.jsonl`.
5. Add the row to this matrix with the log reference.
6. Update `docs/HARNESS_MATRIX.md` in the same PR as the stub file.

## Legacy note

The prior `v1.0.0` matrix used ✅/⚠ marks that were self-attested — this file replaces
that convention with the evidence-state schema described here (per SHR-AUDIT-022 finding).
