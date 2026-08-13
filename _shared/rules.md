<!-- privacy-audit: allow-file "Shared safety spec. Documents pattern-shaped credential/PII examples as detection specifications, not real data." -->

# Shiroe — Shared Rules

Rules repeated across ≥3 skills, extracted here to reduce drift. Reference this file from individual SKILL.md Safety sections as "per `_shared/rules.md`."

---

## R1 — Single-Writer + Privacy Gate

**All writes to `memory/` must pass through `shiroe-runtime` → `privacy-guardian`.**

No skill writes directly. The chain is always:

```
skill output → shiroe-runtime (conflict check, single-write lock) → privacy-guardian (PRIVACY.md mode + REDACT.md classes) → disk
```

Applies to: wiki-maintenance, project-setup, contradiction-resolution, handoff-compiler, memory-import-export, parent-sync, pattern-to-skill.

---

## R2 — Non-Deletion (D9)

**Archive content; never hard-delete.**

- Superseded items are marked `[SUPERSEDED]` with a timestamp — they are never removed.
- Consolidated content moves to `memory/archive/` via copy-then-mark, not rename-then-delete.
- `memory/patterns/PATTERNS.jsonl` is append-only — no line ever removed.

Applies to: wiki-maintenance, budget-governor, contradiction-resolution, memory-import-export, parent-sync.

---

## R3 — Privacy Gate on External Output

**Before any external output or sync, pass the full payload through `privacy-guardian`.**

External = outbound to parent project, handoff package, MCP connector, or any tool outside the local `memory/` tree.

Reading `PRIVACY.md` mode and `REDACT.md` classes is not enough — the payload must actually be rewritten by `privacy-abstraction` when mode = `abstract`, and blocked when mode = `local-only`.

Applies to: handoff-compiler, memory-import-export, parent-sync, pattern-to-skill.

---

## R4 — Never Invent

**When a field value is unknown or the user declines to answer, leave it blank with a `# TODO` marker. Never fabricate.**

This applies to config fields, evidence grades, decision provenance, and any metadata field in `memory/`.

Applies to: project-setup, evidence-grader, contradiction-resolution, memory-import-export.

---

## R6 — Zero Context Loss (v2.6)

**Every fact, named entity, constraint, file path, repo, URL, and edge case from the raw user prompt must survive into any restructured brief, routing decision, or handoff package.**

When `prompt-context-engine` rewrites an UNSTRUCTURED prompt into a Structured Task Brief, the rewriter must verify a diff: the brief covers every entity and constraint in the raw prompt, or explicitly marks each omission with a reason.

When `skill-router` declares a stack, every domain signal extracted from the prompt must be reflected in the chosen lead / support / QA — or the unmatched signal must be named in the routing output.

When `handoff-compiler` (or future `caveman-handoff`) packages a session, the original prompt classification + brief diff + stripped-context list ride along with the handoff so the next model can reconstruct full intent.

Forward dependency: referenced by Session B model-tier routing (per-skill model audit must preserve weight signals from prompt) and the Session C `caveman-handoff` skill (must carry the brief diff across model switches).

Applies to: prompt-context-engine, skill-router, handoff-compiler, caveman-handoff (Session C).
