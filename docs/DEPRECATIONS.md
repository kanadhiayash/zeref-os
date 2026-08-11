# Deprecations — Shiroe vNext

One-cycle alias map introduced by the vNext architecture reset (2.0.0-alpha.1). Aliases resolve today; removal target is **2.1.0**.

## Alias map

| Old name | New name | Category | Alias removed in |
|---|---|---|---|
| `small` | `lean` | execution-policy | 2.1.0 |
| `medium` | `balanced` | execution-policy | 2.1.0 |
| `enterprise` | `assured` | execution-policy | 2.1.0 |
| `skill-router` | `capability-resolver` | component | 2.1.0 |
| `fleet-activator` | `capability-prober` | component | 2.1.0 |
| `skill-importer` | `capability-manager` | component | 2.1.0 |
| `haiku` | `fast` | reasoning-class | 2.1.0 |
| `sonnet` | `balanced` | reasoning-class | 2.1.0 |
| `opus` | `deep` | reasoning-class | 2.1.0 |

Source of truth: `shiroe/core/deprecations.py` (`DEPRECATED_ALIASES`). This table must stay in sync with that dict — if they drift, the code wins.

## The `resolve_alias` mechanism

`shiroe.core.deprecations.resolve_alias(name)`:

- Looks up `name` in `DEPRECATED_ALIASES`. If not deprecated, returns `name` unchanged.
- If deprecated, emits a `DeprecationWarning` **once per process** (tracked in an in-memory `_warned` set — repeated calls with the same name don't re-warn) pointing at this file and the 2.1.0 removal target.
- Always returns the canonical replacement, never the old name. Callers should route every user-facing or config-facing name through this function rather than hardcoding old-name fallbacks.

This is a warn-and-translate layer, not a hard failure — old configs, scripts, and registry entries referencing pre-2.0 names keep working through 2.0.x.

## Migration guidance

- **Execution policies**: legacy Mission/Team execution policies were removed in vNext Phase 04. New execution constraints live on Work Graph nodes and the Execution Engine budget/criticality primitives.
- **Component names**: replace `skill-router` → `capability-resolver`, `fleet-activator` → `capability-prober`, `skill-importer` → `capability-manager` in any script, doc, or automation that names these components directly. The renamed components take on a broader lifecycle scope (all capability types, not just skills) — don't treat this as a pure find-and-replace if you're extending behavior, only if you're referencing the name.
- **Model-tier names**: replace `haiku`/`sonnet`/`opus` with the provider-neutral `fast`/`balanced`/`deep` reasoning classes anywhere a task specifies how much reasoning it needs. Concrete provider model ids (e.g. which model `deep` resolves to) now live only under `shiroe/adapters/providers/<provider>.json` — never hardcode a model id in a mission, skill, or config file again.
- **Team-pack file renames are closed.** Team Packs and Missions are removed product surfaces. Do not add compatibility aliases for them.

## Legacy-identity aliases (SHR-014 / SHR-015)

The project shipped under a different name before the rename. A handful of those spellings are an **external contract** this repository cannot rewrite — they live in shell profiles, in other people's working trees, and in a hand-maintained CSV that is not in this repo. Dropping them would fail *silently*: an unset variable falls back to its default, an unread database yields no rows, an unrecognised CSV header drops a column.

Every one of them is now a named constant in `shiroe/compat/legacy_identity.py`. That module is the only place in the package allowed to spell an old name; `scripts/check-active-identity.py` fails CI on any other active surface, and `tests/test_legacy_compatibility_boundary.py` fails CI if a constant is added here without a row below.

**The old spellings themselves are deliberately not repeated in this table.** Duplicating them would defeat the boundary. The literal values live in the constant docstrings and, for operators, in `MIGRATION.md`.

| Constant | Replacement | Deprecation warning | Owner | Removed in | Migration path | Test |
|---|---|---|---|---|---|---|
| `LEGACY_ENV_PREFIX` | `SHIROE_` prefix | `DeprecationWarning`: "…is deprecated; use SHIROE_&lt;name&gt;." | kanadhiayash | 4.0.0 | `MIGRATION.md` §Environment variables — re-export with the new prefix | `tests/test_env_compat.py::test_legacy_name_still_works_and_warns` |
| `LEGACY_WORKSPACE_DIR` | `.shiroe/` | `DeprecationWarning`: "…/ is deprecated; move it to .shiroe/" | kanadhiayash | 4.0.0 | `MIGRATION.md` §Workspace directory — `mv` the directory | `tests/test_db_rename_migration.py::test_legacy_workspace_policy_still_loads` |
| `LEGACY_V1_STATE_DB_NAME` | `memory/state/shiroe.sqlite` via store convergence | None — silent by design; the file is still the live v1 filename, so warning on every read would fire constantly. Issue #208 owns the convergence. | kanadhiayash | 4.0.0 (blocked on issue #208) | `MIGRATION.md` §Memory store — `shiroe.storage.importer.run_import` copies v1 rows into the vNext store | `tests/test_legacy_compatibility_boundary.py::test_legacy_sqlite_store_round_trips_through_the_importer` |
| `LEGACY_VNEXT_STATE_DB_NAME` | `memory/state/shiroe.sqlite` | `DeprecationWarning`: "…is deprecated; renaming it to shiroe.sqlite" | kanadhiayash | 4.0.0 | `MIGRATION.md` §Memory store — automatic, renamed in place on first open | `tests/test_db_rename_migration.py::test_legacy_database_is_adopted` |
| `LEGACY_MEMORY_INDEX_DB_NAME` | `memory/indexes/shiroe.sqlite` | None — silent by design; the cache is fully derived from the JSONL atoms and is deleted, so there is nothing an operator could act on | kanadhiayash | 4.0.0 | `MIGRATION.md` §Memory index — automatic, deleted and rebuilt | `tests/test_legacy_compatibility_boundary.py::test_legacy_memory_index_cache_is_deleted_not_migrated` |
| `LEGACY_IMPORT_BACKUP_PREFIX` | `shiroe-` backup prefix | None — silent by design; it is read only during a rollback, and warning there would add noise to a recovery | kanadhiayash | 4.0.0 | `MIGRATION.md` §Memory store — new backups are already Shiroe-named; old ones stay rollback-able | `tests/test_legacy_compatibility_boundary.py::test_rollback_still_finds_a_pre_rename_backup` |
| `LEGACY_PRODUCT_NAME` | `shiroe` | None — silent by design; this is a scanner pattern, not something an operator configures. Warning would fire on other people's copy. | kanadhiayash | no fixed date — retires when no reachable public copy uses the old name | `MIGRATION.md` §Product name — nothing to do; the gate matches both | `tests/test_legacy_compatibility_boundary.py::test_claim_gate_matches_the_pre_rename_product_name` |

Removing any of these early is a breaking change to somebody's working tree, not a cleanup.

## What is not aliased

- `faang-mangoes-council` has no alias — it is a hard removal, not a rename. See `docs/adr/ADR-0003-council-removal.md`.
- The v1 memory store is **not** renamed in place. ADR-0001 makes `memory/state/shiroe.sqlite` the canonical vNext store, so renaming the v1 file to a Shiroe name would either collide with a different schema or leave two Shiroe-named databases both claiming to be current state. The resolution is store convergence — import the v1 rows, then drop the v1 file — tracked as **issue #208**, owner **kanadhiayash**. Until it lands, the importer is the migration path and the old filename stays.
