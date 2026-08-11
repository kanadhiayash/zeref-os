# Operations and maintenance (SHR-130..136)

One-stop map for who owns every maintenance surface in this repository,
and on what cadence each is expected to be reviewed. Closing surface of
the SHR hardening sprint.

## The maintenance surfaces

| Surface | Owner | Review cadence | Where to look |
|---|---|---|---|
| Canonical store (SQLite) | @kanadhiayash | on every schema migration | `shiroe/storage/state.py`, `shiroe/migrations/` |
| Registry (`shiroe-registry.json`, `registry/*.json`) | @kanadhiayash | weekly + on new component landing | validator: `scripts/shiroe-validate.py` |
| Trust registry (visuals + imported refs) | @kanadhiayash | quarterly, or when a visual/URL changes | `docs/canon/TRUST_REGISTRY.json` + `scripts/check-trust-registry.py` |
| Provider adapters (`shiroe/adapters/providers/*.json`) | @kanadhiayash | monthly, or on new model release | tests: `tests/test_dataset_provider_integrity.py` |
| Release evidence blobs | release-check runner | one per release SHA | `docs/audits/release-evidence/` |
| Rollback runbook | @kanadhiayash | after each rehearsal | `docs/security/HISTORY_REWRITE_RUNBOOK.md` |
| Task graph + knowledge graph | @kanadhiayash | on new node kind / predicate | `shiroe/graph/` |
| Privacy scanner | @kanadhiayash | on new sensitive-class fixture | `shiroe/privacy.py`, `tests/test_privacy_pr17_bypass.py` |
| Policy precedence (ADR-0005) | @kanadhiayash | on new layer or predicate | `docs/adr/ADR-0005-policy-precedence.md` |
| Superseded navigation | see table below | on every deprecation | this document |

## Superseded surfaces (must not appear in current navigation)

Anything listed here is retained for historical reference only. The
current navigation (README, `docs/GETTING_STARTED.md`,
`docs/GLOSSARY.md`) must not link to it as a live document.

- `assets/archive/` — historical brand assets; superseded by
  `assets/*.svg` + `assets/*.png` documented in `assets/README.md`.
- `docs/BENCHMARK_REPORT.md` — historical snapshot; live report is
  `benchmarks/results.json`.

## Escalation and review

- Anything that fails the per-PR gate blocks merge automatically. The
  gate scripts (`scripts/check-canon-consistency.py`,
  `scripts/check-active-identity.py`, `scripts/shiroe-validate.py`,
  `scripts/check-version-consistency.py`,
  `scripts/check-trust-registry.py`, `shiroe audit-privacy --strict`,
  `shiroe release check`) are exhaustive; do not add human-only checks
  that duplicate them.
- Every maintenance surface in the table above must have a named owner
  and a real review cadence. `tests/test_operations_owners.py` fails
  loudly when a row breaks either invariant.

## The rollback path (rehearsal)

Every release must have completed a rollback rehearsal before
approval. The rehearsal script lives at
`docs/security/HISTORY_REWRITE_RUNBOOK.md`; run it in a scratch clone
and record the outcome in the release-evidence blob.
