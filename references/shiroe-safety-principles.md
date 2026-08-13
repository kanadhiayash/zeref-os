# Shiroe Safety Principles (v4.3)

**Shared reference — used by all skills and agents.**

These rules exist not as arbitrary restrictions but because Shiroe handles persistent project memory across long horizons. A mistake here erases knowledge that took weeks to build.

---

## Rule 1 — Single writer to flat memory/
**Why**: Concurrent writes cause silent data loss and corrupt index consistency.
**What**: Only `shiroe-runtime` writes to wiki files in flat `memory/` (`index.md`, `DECISIONS.md`, `OPEN_QUESTIONS.md`, `RISKS.md`, `CONFLICTS.md`, `MEMORY.md`, `hot.md`). Any other agent attempting to write triggers a block + violation log event.

## Rule 2 — Append-only logs
**Why**: Mutable logs destroy audit trail. Migration, debugging, and pattern detection all depend on event immutability.
**What**: `memory/patterns/PATTERNS.jsonl` is append-only. Never edit existing lines. Never delete the file. Rotate by snapshotting, never by truncating. (Historical v4.2 predecessor: `memory/archive/session-events-v4.2.jsonl`.)

## Rule 3 — Privacy mode enforcement before every write
**Why**: A single accidental write of credentials or sensitive paths poisons the wiki and any downstream sync.
**What**: Every payload passes through `privacy-guardian` per root `PRIVACY.md` mode + `REDACT.md` classes + `SHARING_POLICY.md` connector allowlist before reaching `shiroe-runtime`. Always-block patterns (credentials, `.gitignore` contents) reject regardless of mode.

## Rule 4 — Contradictions never silently resolved
**Why**: Silent resolution destroys both sides of a real disagreement and erodes user trust in the wiki as canonical state.
**What**: When `shiroe-runtime` detects a conflict, both sides go to `memory/CONFLICTS.md`. User arbitrates. `contradiction-resolution` skill orchestrates.

## Rule 5 — Boundary-first reads (per AGENTS.md §"First action every session")
**Why**: Loading full wiki pages on every operation blows the token budget and defeats progressive activation.
**What**: Always read `memory/hot.md` first (≤500 words). If insufficient, read `memory/index.md`. Find the relevant domain. Read only the named section of the named page.

## Rule 6 — Irreversible actions require explicit confirmation
**Why**: Destructive operations (file deletion outside `memory/archive/`, force-push, dropping permissions) cannot be undone from inside Shiroe.
**What**: Always prompt the user with the exact action + target + consequence before executing. Never infer approval from session context.

## Rule 7 — Evidence is graded, not inferred
**Why**: Unverified assumptions silently elevated to "fact" cause downstream decisions to compound on bad ground.
**What**: Every wiki entry carries an evidence grade (high / medium / low). `evidence-curator` re-grades on staleness. User remains the arbiter.

## Rule 8 — Never invent
**Why**: Hallucinated provenance, source references, or user metrics poison the wiki permanently.
**What**: When uncertain, label `[ASSUMPTION]`, `[UNKNOWN]`, `[RISK]`. Never present inference as fact. Preserve exact commands, paths, URLs, errors verbatim.

## Rule 9 — Review-first skill extension
**Why**: Auto-activating drafted skills creates a feedback loop where the agent invents its own scope creep.
**What**: vNext has no first-party Skills authoring path. Rule-creation still follows the Two-Strikes Rule (`references/two-strikes-rule.md`) — never codify on first occurrence; only codify after a pattern has repeated.

## Rule 10 — Honest limits declared publicly
**Why**: Overpromised capabilities erode trust when reality disappoints. Better to declare what Shiroe doesn't do.
**What**: Three honest limits in README:
1. No real-time collaborative merge
2. No hosted backend
3. No silent semantic conflict resolution (feature, not bug)

## Rule 11 — Connectors OFF by default
**Why**: Pre-enabled connectors leak project context before the user consents.
**What**: Every MCP / connector in `SHARING_POLICY.md` starts `enabled: false`. Shiroe recommends connectors only after `pattern-observer` detects repeated manual behavior (per `references/connector-advisory.md`).

## Rule 12 — Archive, never hard delete (per D9)
**Why**: Hard delete is unrecoverable. The wiki must keep an audit trail of supersession.
**What**: Superseded entries move to `memory/archive/` with a `[SUPERSEDED]` marker. The pre-v4.3 migration snapshot lives in `memory/snapshots/pre-v4.3-<iso>/`.

---

## Evidence discipline (every output)

```
Facts (verified this session):
Assumptions (labeled [ASSUMPTION: ...]):
Unknowns ([UNKNOWN: not verified]):
Risks ([RISK: potential failure]):
```
