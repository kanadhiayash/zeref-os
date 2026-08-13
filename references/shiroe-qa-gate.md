# Shiroe 4.0 QA Gate

**Run before every wiki write and every handoff package.**

A single quality bar shared by all skills and agents.

---

## Gate checks

### 1. Evidence separation
Output explicitly separates:
- Facts (verified this session)
- Assumptions (labeled `[ASSUMPTION: ...]`)
- Unknowns (labeled `[UNKNOWN: not verified]`)
- Risks (labeled `[RISK: ...]`)

### 2. Provenance
Every wiki write carries: source event hash, session ts, agent that produced it.

### 3. Privacy mode applied
Payload passed through `privacy-guardian` per current root `PRIVACY.md` mode + `REDACT.md` classes + `SHARING_POLICY.md` connector allowlist. Transformation logged if mode = abstract.

### 4. Boundary-first compliance
Reads happened via `memory/hot.md` → `memory/index.md` → page section (per AGENTS.md §"First action every session"), not full pages. Skill outputs ≤ skill's declared `max_turns` token equivalent.

### 5. Anti-hallucination
No invented file paths, metrics, user research, citations, repo state, or build results. Exact commands / paths / URLs / errors preserved verbatim.

### 6. Single-writer compliance
Wiki writes routed through `shiroe-runtime`. No skill or agent attempts direct write to flat `memory/` wiki files (`index.md`, `DECISIONS.md`, `OPEN_QUESTIONS.md`, `RISKS.md`, `CONFLICTS.md`, `MEMORY.md`, `hot.md`).

### 7. Contradiction handling
If conflict detected: halt write, append to `CONFLICTS.md`, surface to user. Never silent resolve.

### 8. Evidence grade attached
Every entry destined for `DECISIONS.md` carries a grade (high / medium / low) from `evidence-curator`.

### 9. Irreversible action confirmation
Any destructive op (file delete, force push, permission grant) confirmed explicitly by user in this session.

### 10. Token discipline
Output respects current model tier verbosity. No filler. No motivational text. Compact tables over prose where they reduce ambiguity.

---

## Fail mode

If any check fails:
1. Halt the write or output
2. Surface the failure reason to the user
3. Offer corrective action (re-grade, request user confirmation, abstract more, etc.)
4. Never silently downgrade and proceed
