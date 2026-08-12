# Deprecations — Shiroe legacy-identity register

<!-- privacy-audit: allow-file "Documents pre-rename identifier constants only; no user data." -->

Every row below is a single pre-rename identifier the runtime still recognises
because dropping it would fail *silently* (an unset env var falling back to a
default, an unread database presenting as total memory loss). Removing an old
spelling that would fail loudly is a plain rename, not a compat alias, and
does not belong here.

Source of truth: `shiroe/compat/legacy_identity.py`. Every constant in that
module's `__all__` has a row here; the alignment gate is
`tests/test_legacy_compatibility_boundary.py`. If the table and the module
drift, the code wins and the test fails the build.

Vestigial vNext one-cycle aliases from the 2.0.0-alpha era were removed in
Phase 08: the aliased replacements themselves were retired by the vNext core
overhaul (see `docs/architecture/REMOVALS.md`). Only the pre-rename identity
boundary remains.

## Register

| constant | replacement | deprecation warning | owner | removed in | migration path | test |
|---|---|---|---|---|---|---|
| `LEGACY_ENV_PREFIX` | `SHIROE_` env-var prefix | `DeprecationWarning` from `shiroe.env.getenv` after `SHIROE_<name>` misses | kanadhiayash | 4.0.0 | Rename `ZEREF_<name>` variables to `SHIROE_<name>` in shell profiles, CI configs, and systemd units | `test_runtime_never_hardcodes_a_legacy_string` |
| `LEGACY_WORKSPACE_DIR` | `.shiroe/` per-project workspace | `DeprecationWarning` from `shiroe.policy.loader` when `.zeref/` is read as fallback | kanadhiayash | 4.0.0 | Move `.zeref/` policy files into `.shiroe/` in each project working tree | `test_runtime_never_hardcodes_a_legacy_string` |
| `LEGACY_V1_STATE_DB_NAME` | `memory/state/shiroe.sqlite` (via importer) | Read-only path; `shiroe.storage.importer.run_import` logs the import | kanadhiayash | 4.0.0 | Run `shiroe` once to trigger `run_import`, then delete `memory/state/zeref.sqlite` after `state verify` passes | `test_legacy_sqlite_store_round_trips_through_the_importer` |
| `LEGACY_VNEXT_STATE_DB_NAME` | `memory/state/shiroe.sqlite` | One-shot rename by `shiroe.storage.state.StateDB` on first open when the Shiroe-named path is absent | kanadhiayash | 4.0.0 | No user action needed; the first `shiroe` invocation performs the atomic rename | `test_new_state_database_is_shiroe_named` |
| `LEGACY_MEMORY_INDEX_DB_NAME` | Derived index (rebuilt from canonical rows) | Silently deleted by `shiroe.compat` cleanup; the index is disposable | kanadhiayash | 4.0.0 | No user action needed; the index rebuilds from JSONL atoms on next recall | `test_runtime_never_hardcodes_a_legacy_string` |
| `LEGACY_IMPORT_BACKUP_PREFIX` | `shiroe-` importer-backup prefix | `DeprecationWarning` reserved for the future; today `rollback()` accepts both prefixes silently | kanadhiayash | 4.0.0 | Rename backups under `memory/state/backups/` from `zeref2-*` to `shiroe-*` once a Shiroe-named backup exists | `test_rollback_still_finds_a_pre_rename_backup` |
| `LEGACY_PRODUCT_NAME` | `shiroe` | Substring-match only; no runtime warning path | kanadhiayash | 4.0.0 | No user action needed; retained solely for the identity boundary and importer text matching | `test_runtime_never_hardcodes_a_legacy_string` |

## What is not aliased

- Command names, CLI flags, and Python module paths were renamed hard: an
  import failure or `argparse` "unknown option" is a loud failure that reveals
  itself immediately. There is no alias layer for these.
- The component names retired by the vNext core overhaul are not deprecations
  — the entire product surface they described was removed. See
  `docs/architecture/REMOVALS.md`.
- The council-family removal (`ADR-0003`) is a hard removal by explicit
  decision, not a rename.

The 4.0.0 removal target applies to every row above. Cutting an entry earlier
is a breaking change to somebody's working tree, not a cleanup.
