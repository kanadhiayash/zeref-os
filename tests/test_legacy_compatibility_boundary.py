"""SHR-014/015/016/027 — the legacy-compatibility boundary.

The project shipped under a different name. Some legacy spellings are an
*external* contract the repo cannot rewrite: env vars live in shell profiles, on-disk
database filenames live in other people's working trees. Deleting those readers would not fail loudly —
an unset variable falls back to a default and an unread file simply yields
nothing — so they stay.

What must not stay is the *scatter*. Every one of those spellings now lives in
exactly one place, `shiroe/compat/legacy_identity.py`, with a documented owner
and removal plan. This file is the gate on that: the runtime may not hardcode a
legacy string, an undocumented alias fails CI, and the identity allowlist may
not regrow.

Nothing here is a hand-copied list. The legacy strings come from the compat
module itself and the exempt paths come from the identity gate's own tables, so
adding a constant or an allowlist entry is picked up automatically.
"""

from __future__ import annotations

import ast
import importlib.util
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_SCRIPT = REPO_ROOT / "scripts" / "check-active-identity.py"
DEPRECATIONS = REPO_ROOT / "docs" / "DEPRECATIONS.md"
COMPAT_REL = "shiroe/compat/legacy_identity.py"

# The allowlist is an exception register. This PR (SHR-014) shrank it by moving
# every runtime reader behind shiroe/compat/. Growing it back is the failure
# mode this ceiling exists to catch: raise it only with a written reason in the
# same diff, never to make a red build green.
#
# 16 → 17 (SHR-029/031, security/shr-redaction-manifest): the history-redaction
# manifest quotes historical file paths and commit subjects verbatim, three of
# which are spelled with the pre-rename identity. Redacting them would falsify
# the evidence the rewrite decision rests on, so the file is allowlisted and the
# ceiling moves by exactly one. It is one file entry, not a docs/security/
# prefix, so a second file in that directory does not inherit the exemption.
MAX_ALLOWLISTED_PATHS = 17


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _load_identity_gate():
    spec = importlib.util.spec_from_file_location("_cai_boundary", IDENTITY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compat_module():
    from shiroe.compat import legacy_identity

    return legacy_identity


def _exported_names() -> list[str]:
    mod = _compat_module()
    names = list(mod.__all__)
    assert names, f"{COMPAT_REL} exports nothing"
    return names


def _legacy_strings() -> dict[str, list[str]]:
    """Every literal legacy string the compat module owns, by constant name.

    Handles both plain strings and the mapping constants (CSV header aliases),
    so a new alias needs no change here.
    """
    mod = _compat_module()
    out: dict[str, list[str]] = {}
    for name in _exported_names():
        value = getattr(mod, name)
        if isinstance(value, str):
            out[name] = [value]
        elif isinstance(value, dict):
            out[name] = [v for v in value.values() if isinstance(v, str)]
        elif isinstance(value, (tuple, list, frozenset, set)):
            out[name] = [v for v in value if isinstance(v, str)]
        else:  # pragma: no cover - a new constant kind needs a decision
            pytest.fail(f"{name}: unsupported constant type {type(value)!r}")
    return out


def _python_sources() -> list[Path]:
    """Importable runtime Python that is *not* the boundary itself.

    `scripts/` is deliberately out of scope: those files run standalone with no
    package on `sys.path` (`scripts/fetch-benchmark-data.py` is stdlib-only by
    contract), so they cannot import the boundary and stay allowlisted instead.
    """
    return [
        p for p in sorted((REPO_ROOT / "shiroe").rglob("*.py"))
        if "compat" not in p.relative_to(REPO_ROOT).parts
    ]


# --------------------------------------------------------------------------- #
# SHR-014 — the boundary exists and is the only place legacy names are spelled
# --------------------------------------------------------------------------- #

def test_compat_package_is_importable() -> None:
    from shiroe.compat import legacy_identity  # noqa: F401


def test_every_exported_constant_carries_a_docstring() -> None:
    """A bare legacy string is unreadable six months from now. Each constant
    states what spoke the old name, and what replaced it."""
    tree = ast.parse((REPO_ROOT / COMPAT_REL).read_text(encoding="utf-8"))
    documented: set[str] = set()
    previous_targets: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            documented.update(previous_targets)
            previous_targets = []
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            previous_targets = [t.id for t in targets if isinstance(t, ast.Name)]
        else:
            previous_targets = []

    undocumented = sorted(set(_exported_names()) - documented)
    assert not undocumented, (
        f"{COMPAT_REL}: no attribute docstring for {undocumented}. Put a string "
        f"literal directly beneath the assignment."
    )


def test_runtime_never_hardcodes_a_legacy_string() -> None:
    """The point of the boundary: one spelling, one place."""
    offenders: list[str] = []
    for name, values in _legacy_strings().items():
        for value in values:
            for path in _python_sources():
                if value in path.read_text(encoding="utf-8"):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel} hardcodes {value!r} (use {name})")
    assert not offenders, "\n".join(sorted(offenders))


def test_no_runtime_module_needs_the_identity_allowlist() -> None:
    """`shiroe/**` is active surface. After SHR-014 the only package path that
    may carry a legacy token is the compat boundary itself."""
    allowlist = _load_identity_gate().ALLOWLIST
    leaked = sorted(
        p for p in allowlist
        if p.startswith("shiroe/") and not p.startswith("shiroe/compat/")
    )
    assert not leaked, (
        f"still allowlisted instead of routed through {COMPAT_REL}: {leaked}"
    )


def test_identity_allowlist_does_not_regrow() -> None:
    allowlist = _load_identity_gate().ALLOWLIST
    assert len(allowlist) <= MAX_ALLOWLISTED_PATHS, (
        f"allowlist grew to {len(allowlist)} paths (ceiling "
        f"{MAX_ALLOWLISTED_PATHS}); move the reader behind {COMPAT_REL} "
        f"instead of exempting its file"
    )


# --------------------------------------------------------------------------- #
# SHR-015 — an undocumented alias fails CI
# --------------------------------------------------------------------------- #

def test_every_exported_constant_has_a_deprecations_row() -> None:
    text = DEPRECATIONS.read_text(encoding="utf-8")
    missing = [name for name in _exported_names() if f"`{name}`" not in text]
    assert not missing, (
        f"docs/DEPRECATIONS.md has no row for {missing}. Every alias needs an "
        f"owner, a warning, a removal version, a migration path and a test."
    )


def test_deprecations_rows_state_owner_removal_and_test() -> None:
    """A row with no owner and no removal version is a permanent alias wearing
    a deprecation label."""
    rows = [
        line for line in DEPRECATIONS.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `LEGACY_")
    ]
    assert rows, "no legacy-identity rows found in docs/DEPRECATIONS.md"
    columns = ("constant", "replacement", "deprecation warning", "owner",
               "removed in", "migration path", "test")
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == len(columns), (
            f"row has {len(cells)} cells, need {len(columns)}: {row}"
        )
        for index, label in enumerate(columns):
            assert cells[index] and cells[index] != "-", f"{label} empty in: {row}"
        assert "test_" in cells[6], f"test cell names no test: {row}"


# --------------------------------------------------------------------------- #
# SHR-016 — a legacy store still imports; new state is Shiroe-named
# --------------------------------------------------------------------------- #

def test_new_state_database_is_shiroe_named() -> None:
    from shiroe.storage.state import DB_RELPATH

    assert DB_RELPATH.name == "shiroe.sqlite", DB_RELPATH


def test_legacy_sqlite_store_round_trips_through_the_importer(tmp_path: Path) -> None:
    """SHR-016. A pre-rename v1 store must still be readable, or upgrading is
    silent data loss. The importer copies it into the Shiroe-named vNext store;
    the legacy file is left untouched for the operator to remove."""
    from shiroe.compat.legacy_identity import LEGACY_V1_STATE_DB_NAME
    from shiroe.storage.importer import run_import
    from shiroe.storage.state import DB_RELPATH

    state = tmp_path / "memory" / "state"
    state.mkdir(parents=True)
    legacy = state / LEGACY_V1_STATE_DB_NAME
    conn = sqlite3.connect(legacy)
    conn.execute("CREATE TABLE memory_cards (id TEXT, title TEXT, claim TEXT)")
    conn.execute(
        "INSERT INTO memory_cards VALUES ('card_1', 'v1 card', 'survives the rename')"
    )
    conn.commit()
    conn.close()

    manifest = run_import(tmp_path, dry_run=False)

    assert manifest.sources_scanned["legacy_sqlite"] == 1, manifest.to_json()
    assert manifest.records_written >= 1, manifest.to_json()
    assert legacy.exists(), "the legacy store was consumed instead of read"

    new_db = tmp_path / DB_RELPATH
    assert new_db.is_file(), "new state did not land under the Shiroe name"
    rows = sqlite3.connect(new_db).execute(
        "SELECT claim FROM memory_records"
    ).fetchall()
    assert ("survives the rename",) in rows, rows


# --------------------------------------------------------------------------- #
# SHR-027 — nothing live depends on the archived v4.x canon bundle
# --------------------------------------------------------------------------- #

ARCHIVED_CANON_PREFIX = "references/" + "v4x-canon/"


def test_validator_does_not_require_the_archived_canon_bundle() -> None:
    """The validator failing because an *archived* bundle is missing makes the
    archive undeletable. SHR-027 cuts that dependency."""
    text = (REPO_ROOT / "scripts" / "shiroe-validate.py").read_text(encoding="utf-8")
    assert ARCHIVED_CANON_PREFIX not in text, (
        "scripts/shiroe-validate.py still checks the archived canon bundle"
    )


def test_claim_gate_does_not_scan_the_archived_canon_bundle(tmp_path: Path) -> None:
    """Same exclusion the gate already applies to docs/adr/ and CHANGELOG.md:
    a frozen record cannot be edited to satisfy a gate without falsifying it."""
    from shiroe.release.claim_gate import scan_public_claims

    canon = tmp_path / "references" / "v4x-canon"
    canon.mkdir(parents=True)
    (canon / "MODEL_DEBATE.md").write_text(
        "| Privacy | 9.5 | Shiroe is best-in-class. |\n", encoding="utf-8",
    )
    assert not scan_public_claims(tmp_path), (
        "the claim gate still derives findings from the archived canon bundle"
    )
    # The other half of the pair — that excluding the archive did not reopen
    # the rest of references/ — is
    # tests/test_claim_gate.py::test_superiority_claim_under_references_is_caught.



# --------------------------------------------------------------------------- #
# One pin per alias — SHR-015's "link to its test" column points here
# --------------------------------------------------------------------------- #

def test_new_import_backups_are_shiroe_named(tmp_path: Path) -> None:
    """SHR-016: artifacts this code *creates* carry the Shiroe name, even
    though the store it reads still carries the old one."""
    from shiroe.storage.importer import BACKUP_PREFIX, run_import

    (tmp_path / "memory").mkdir()
    run_import(tmp_path, dry_run=False)
    backups = list((tmp_path / "memory" / "state" / "backups").glob("*.sqlite"))
    assert backups, "no backup was written"
    assert all(p.name.startswith(BACKUP_PREFIX) for p in backups), backups


def test_rollback_still_finds_a_pre_rename_backup(tmp_path: Path) -> None:
    """A backup written before the rename is exactly the one somebody reaches
    for when an upgrade went wrong."""
    from shiroe.compat.legacy_identity import LEGACY_IMPORT_BACKUP_PREFIX
    from shiroe.storage.importer import rollback
    from shiroe.storage.state import DB_RELPATH, StateDB

    db = StateDB(tmp_path)
    db.migrate()
    db.connect().execute(
        "INSERT INTO memory_records (id, kind, title, claim, summary, status, "
        "confidence, evidence_grade, privacy_class, authority, scope, "
        "created_at, updated_at, owner, schema_version, archived) "
        "VALUES ('m1','note','t','c','s','active','unknown','unknown',"
        "'internal',0.0,'project','t0','t0','o',2,0)"
    )
    db.connect().commit()
    db.close()

    backup_dir = tmp_path / "memory" / "state" / "backups"
    backup_dir.mkdir(parents=True)
    backup = backup_dir / f"{LEGACY_IMPORT_BACKUP_PREFIX}20250101T000000.sqlite"
    backup.write_bytes((tmp_path / DB_RELPATH).read_bytes())
    (tmp_path / DB_RELPATH).write_bytes(b"")

    assert rollback(tmp_path) == backup
    rows = sqlite3.connect(tmp_path / DB_RELPATH).execute(
        "SELECT id FROM memory_records"
    ).fetchall()
    assert rows == [("m1",)]


def test_legacy_memory_index_cache_is_deleted_not_migrated(tmp_path: Path) -> None:
    """The index is derived from the JSONL atoms, so the pre-rename cache is
    removed on rebuild rather than carried forward."""
    from shiroe.compat.legacy_identity import LEGACY_MEMORY_INDEX_DB_NAME
    from shiroe.memory.indexer import INDEX_PATH, rebuild_index

    legacy = tmp_path / "memory" / "indexes" / LEGACY_MEMORY_INDEX_DB_NAME
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"stale cache")

    rebuild_index(tmp_path)

    assert not legacy.exists(), "the pre-rename index cache survived a rebuild"
    assert (tmp_path / INDEX_PATH).is_file()


def test_claim_gate_matches_the_pre_rename_product_name(tmp_path: Path) -> None:
    """Docs in flight and third-party copy still use the old product name. A
    gate that stopped matching it would let an overclaim through."""
    from shiroe.compat.legacy_identity import LEGACY_PRODUCT_NAME
    from shiroe.release.claim_gate import scan_public_claims

    (tmp_path / "README.md").write_text(
        f"{LEGACY_PRODUCT_NAME.title()} is best-in-class.\n", encoding="utf-8",
    )
    findings = scan_public_claims(tmp_path)
    assert any(f.constraint == "unverified_superiority_claim" for f in findings)
