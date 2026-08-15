# ADR-0003: FAANG-MANGOES council removal

**Status:** Accepted
**Date:** 2026-07-12

## Context

`team-packs/faang-mangoes-council.md` implemented a 12-persona architectural-review panel (one persona per FAANG-MANGOES-lettered company lens), activated on demand for load-bearing architecture decisions, with output routed to `docs/audits/council/`. It was registered as the 10th entry in `shiroe-registry.json`'s `team_packs` array and referenced from `SOUL.md` and imported-skill READMEs.

The vNext architecture plan (§3.1) requires removing it completely: persona panels are not a Shiroe team-pack type, the panel's deliberation value over simpler review was never benchmarked, and static named-persona rosters are exactly the kind of fixed-agent concept the plan's dynamic mission-compilation model (§3.3, §9) replaces.

## Decision

Remove the FAANG-MANGOES council entirely — pack, registry entry, and brand:

- Delete `team-packs/faang-mangoes-council.md`.
- Remove its `shiroe-registry.json` `team_packs` entry (array goes from 10 → 9 entries).
- Purge references from `SOUL.md` and imported-skill READMEs.
- No alias, redirect, or compatibility shim is provided — this is a hard removal, not a rename (see `removed deprecation register`, "What is not aliased").

Per the architecture plan §3.2, the *reusable* protocol ideas the council explored (blind-first independent review, problem restatement, method/provider diversity, anti-conformity instructions, dissent preservation, independent synthesis) are not lost — they are reimplemented later as runtime state transitions inside an **evaluator adapter**: `Council of High Intelligence` becomes an optional, provider-neutral evidence-system evaluator (`shiroe/evaluators/council_high_intelligence/`), experimental until it demonstrates measurable benefit over a single grader or same-model jury in the council value benchmark (PR 11).

## Consequences

- Historical references remain only in `CHANGELOG.md` — never in a runtime path, registry, or public-facing capability list.
- Any script, doc, or automation still pointing at `team-packs/faang-mangoes-council.md`, `docs/audits/council/`, or the `faang-mangoes-council` registry entry is now stale and must be updated or deleted.
- The replacement evaluator (PR 11) is explicitly optional and experimental — nothing in Shiroe may depend on it being present, and nothing may claim council-graded evidence is stronger than its underlying source evidence (evidence quality and review robustness remain separately scored per §11.1 of the plan).
- No new persona-panel-style persona panel may be introduced without amending this ADR.
