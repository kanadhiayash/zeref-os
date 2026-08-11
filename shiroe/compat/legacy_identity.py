"""Every pre-rename identifier the runtime still has to recognise (SHR-014).

privacy-audit: allow-file "Named constants for the project's own pre-rename
env-var prefix, filenames and CSV headers. No user data."

Read this before adding anything here. A constant belongs in this module only
when dropping the old spelling would **fail silently**:

- an unset environment variable falls back to a default, so a network guard
  would quietly re-arm rather than error;
- an unread database file yields no rows, which presents as total memory loss
  rather than as a missing file;

Anything whose removal *does* fail loudly is a plain rename, not a compat
alias, and does not belong here.

Each constant below states what still speaks the old name, what replaced it,
and how it goes away. ``docs/DEPRECATIONS.md`` carries the same set as a table
with owner, removal version, migration path, and the test that pins it;
``tests/test_legacy_compatibility_boundary.py`` fails the build when the two
drift, when a constant has no attribute docstring, or when a module outside
this package hardcodes one of these strings.

Owner for every entry: kanadhiayash. Removal target for every entry: 4.0.0,
i.e. the first release after the deprecation window closes. Removing one early
is a breaking change to somebody's working tree, not a cleanup.
"""

from __future__ import annotations

__all__ = [
    "LEGACY_ENV_PREFIX",
    "LEGACY_WORKSPACE_DIR",
    "LEGACY_V1_STATE_DB_NAME",
    "LEGACY_VNEXT_STATE_DB_NAME",
    "LEGACY_MEMORY_INDEX_DB_NAME",
    "LEGACY_IMPORT_BACKUP_PREFIX",
    "LEGACY_PRODUCT_NAME",
]


LEGACY_ENV_PREFIX = "ZEREF_"
"""Pre-rename environment-variable prefix, replaced by ``SHIROE_``.

Read by :func:`shiroe.env.getenv` after ``SHIROE_<name>`` misses. Using an old
name still works and emits a ``DeprecationWarning`` naming the new one.
Environment variables live in shell profiles, CI configs and systemd units
outside this repository, so the fallback outlives the file renames.
"""

LEGACY_WORKSPACE_DIR = ".zeref"
"""Pre-rename per-project workspace directory, replaced by ``.shiroe``.

Read by :mod:`shiroe.policy.loader` only when the ``.shiroe`` path holds no
file. The contents are deny rules and write scopes: if a rename made them stop
loading, nothing would raise -- the guard would simply stop denying.
"""

LEGACY_V1_STATE_DB_NAME = "zeref.sqlite"
"""Filename of the v1 memory store under ``memory/state/``.

Still the live filename of the v1 layout (:class:`shiroe.memory.core.MemoryLayout`
and :mod:`shiroe.memory_state`), and the store
:func:`shiroe.storage.importer.run_import` reads to carry v1 rows into the
vNext database.

Deliberately **not** renamed in place. ADR-0001 makes
``memory/state/shiroe.sqlite`` the canonical vNext store, so renaming this file
to a Shiroe name would either collide with a different schema or leave two
Shiroe-named databases both claiming to be current state. The resolution is
store convergence -- import the v1 rows, then drop the v1 file -- tracked as
issue #208. Until that lands, the old name stays and the importer is the
migration path.
"""

LEGACY_VNEXT_STATE_DB_NAME = "zeref2.sqlite"
"""Pre-rename filename of the vNext canonical store, now ``shiroe.sqlite``.

:class:`shiroe.storage.state.StateDB` renames this file into place on first
open, once, and only when the Shiroe-named path does not already exist. This
is canonical state rather than a cache, so leaving it behind would present as
total memory loss instead of as a rename.
"""

LEGACY_MEMORY_INDEX_DB_NAME = "zeref.sqlite"
"""Pre-rename filename of the memory index cache under ``memory/indexes/``.

Same spelling as :data:`LEGACY_V1_STATE_DB_NAME` but a different artifact with
a different fate: the index is fully derived from the JSONL atoms, so
:mod:`shiroe.compat` cleanup deletes it rather than migrating it. Keeping the
two constants separate is what stops a future cleanup from
deleting the canonical store on the strength of a matching filename.
"""

LEGACY_IMPORT_BACKUP_PREFIX = "zeref2-"
"""Pre-rename prefix of importer backup files under ``memory/state/backups/``.

Read-only now: :func:`shiroe.storage.importer.rollback` still finds backups
written before the rename, but new backups are written Shiroe-named. Dropping
this would make a pre-rename backup unrollbackable, which is exactly the moment
somebody needs it.
"""

LEGACY_PRODUCT_NAME = "zeref"
"""The pre-rename product name, lowercased for substring matching.

Kept for migration and import compatibility only. Public-claim scanning moved
out of the runtime product surface in vNext.
"""
