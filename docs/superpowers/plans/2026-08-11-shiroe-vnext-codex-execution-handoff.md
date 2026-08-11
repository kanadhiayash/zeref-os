# Codex Execution Handoff: Shiroe vNext Core Overhaul

## Read first

1. `00_DESIGN_SPEC.md`
2. `00_MASTER_EXECUTION_PLAN.md`
3. Phase plans `01` through `08` in order
4. Repository `AGENTS.md`, `SOUL.md`, `PRIVACY.md`, `REDACT.md`

## Execution rule

Do not implement the overhaul as one giant patch. Execute one task at a time with red-green-refactor and a commit after each independently reviewable task.

Use Superpowers `subagent-driven-development` if available. A fresh worker should receive exactly one task plus its declared interfaces. Review spec compliance first, then code quality, before moving to the next task.

## Non-negotiable prohibitions

Do not:

- restore benchmark machinery or BM25 during the overhaul;
- preserve a deleted surface only because an old test expects it;
- keep `contract` or `experimental` product entries;
- create first-party standalone Skills;
- recreate Team Packs, Missions, seats, or a second graph model;
- let the Approval Advisor write approval decisions;
- use generated Markdown as canonical memory;
- introduce a second memory retrieval backend;
- weaken policy/privacy/concurrency tests to get green;
- push, merge, publish or deploy without explicit human approval.

## Escalation condition

Stop the current task and surface a blocking design conflict only when all three are true:

1. the plan requires deleting or changing user-authored canonical memory;
2. no lossless migration path exists with the current schema;
3. proceeding would risk irreversible data loss.

For ordinary implementation uncertainty, make the smallest choice consistent with `00_DESIGN_SPEC.md`, add a test that fixes the interpretation, and continue.

## Completion evidence

Return:

- commit list by task;
- files added/modified/deleted by phase;
- exact test commands and results;
- final `doctor --json` result;
- final CLI help surface;
- migration verification results;
- remaining risks, if any;
- confirmation that no benchmark was run or claimed.
