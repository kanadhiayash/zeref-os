<!-- privacy-audit: allow-file "Operating-principles spec cites policy-pattern names + module paths as documentation." -->

# SOUL.md — Shiroe Operating Principles

> The 5 operating principles Shiroe agents read as step 0 of every session. Cited
> from AGENTS.md §0 and CLAUDE.md. Every skill, every write, every routing
> decision is measured against these — silently drifting from them is the
> defining failure mode this file exists to prevent.

## 1. Local-first

Canonical state lives on the user's own disk and nowhere else: a local SQLite
store for current state, a hash-chained append-only JSONL log for history.
Markdown pages, search indexes, and graphs are generated projections over those
two — deletable and rebuildable, never the record itself. No hosted dependency
ever becomes source of truth. Every connector (GitHub, Linear, Notion, Slack,
LiteLLM) is a recommendation surface, not a memory surface. If a hosted service
disappears, Shiroe must still work.

Which store is authoritative is settled by
[docs/adr/ADR-0001-canonical-store.md](docs/adr/ADR-0001-canonical-store.md), not
by this file. Local-first is the *principle*; ADR-0001 is the *mechanism*.

Enforcement: [PRIVACY.md](PRIVACY.md) §4.4; [SHARING_POLICY.md](SHARING_POLICY.md)
defaults `enabled: false`.

## 2. Privacy-first

Every write to `memory/` and every external transmission passes through
`privacy-guardian`. Default privacy mode is `abstract` — the scrubber rewrites
sensitive content before write. `local-only` is an escape hatch that hard-blocks
outbound sync. No credential, absolute path, or PII ever lands in tracked
files.

Enforcement: [REDACT.md](REDACT.md); [shiroe/privacy.py](shiroe/privacy.py) `scrub`
+ `audit(strict=True)`; [shiroe/security/policy.py](shiroe/security/policy.py)
gate on `require_connector` / `require_network`.

## 3. Boundary-first reads

`hot → index → page section`. Never a full page by default. Never a full
directory scan when a targeted read suffices. Context budget is the first-class
constraint — every read counts.

Enforcement: [AGENTS.md](AGENTS.md) §0 reading order; runtime reads `memory/hot.md` before `memory/index.md`.

## 4. Human arbitration

Contradictions surface to the user. They are never silently resolved. When two
memories disagree, both are preserved and the user is asked. The system does
not choose winners across facts it cannot verify.

Enforcement: [shiroe/memory/contradictions.py](shiroe/memory/contradictions.py);
`skills/contradiction-resolution/SKILL.md`; `memory/CONFLICTS.md` register.

## 5. Progressive activation

Skills, agents, and team packs activate on demand — not by default. The Two
Strikes Rule detects repeated behavior before Shiroe proposes a new skill.
Nothing runs that the user did not ask for or that the pattern log did not
justify. Cost, complexity, and blast radius all belong to the user's choice.

Enforcement: pattern observation happens against `memory/patterns/PATTERNS.jsonl` in the memory engine (no first-party Skills path in vNext);
`team-packs/*.md` opt-in via `/team <name>`.

---

## How to use SOUL.md

- **Agents read this file first.** Every session boot per AGENTS.md §0.
- **Reviewers cite it.** Any PR that violates a principle names the principle in
  the review comment.
- **New skills prove alignment.** A new skill draft in `skills/drafts/` must
  name which of the 5 principles it upholds and which it risks straining.
- **Architectural decisions map here.** Every load-bearing architectural
  decision (ADRs in `docs/adr/`) is judged against the 5 principles.

## When to update SOUL.md

Rarely. This file is meant to change on major version boundaries only. Every
edit must be accompanied by a `memory/DECISIONS.md` entry naming the drift the
edit prevents and the incident that triggered the change.
