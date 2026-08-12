#!/usr/bin/env python3
"""
check-active-identity.py — Fail CI on legacy identity leaking onto an active surface.

SHR-032. The project shipped as Zeref before the rename (see MIGRATION.md).
Some surfaces must keep the old names forever — the changelog, the migration
guide, accepted ADRs, the compat shims, legacy fixtures, and the archived v4.x
canon are *about* the old identity, and rewriting them would falsify a record.
Every other surface is active and must read as Shiroe.

This script draws that line and enforces it. Anything not listed in ARCHIVED or
ALLOWLIST is active: a `Zeref`/`ZRF` token there is a failure. Adding a path to
ALLOWLIST costs a written reason and shows up in the diff, which is the point —
the list is a reviewed exception register, never a way to go green.

Scope note: this is an identity scan, not a rename tool. The runtime still
deliberately *reads* legacy names so old workspaces keep working — but since
SHR-014 every one of those spellings is a named constant in
`shiroe/compat/legacy_identity.py`, and no other module under `shiroe/` may
appear below. `tests/test_legacy_compatibility_boundary.py` enforces both that
rule and a ceiling on the length of ALLOWLIST.

Exit code:
    0  no legacy identity on an active surface
    1  at least one active-surface reference (prints path:line)
    2  the root does not exist or cannot be scanned

Usage:
    python3 scripts/check-active-identity.py [--root <repo-root>] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# `\b` before the token keeps hex digests and base64 blobs from tripping the
# scan while still catching `ZRF_64_...`, `zeref-registry.json`, `ZEREF_HOME`.
LEGACY_RE = re.compile(r"\bzeref|\bzrf", re.IGNORECASE)

MAX_SCAN_BYTES = 2_000_000
PRUNE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".claude"}
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".woff", ".woff2", ".ttf", ".otf", ".sqlite", ".db", ".mp4", ".svg",
}

# Surfaces that are *about* the pre-rename project. Excluded wholesale.
ARCHIVED: dict[str, str] = {
    "CHANGELOG.md": "Release history. Renaming the entries would falsify what shipped under which name.",
    "MIGRATION.md": "The rename guide itself; it has to name what it renames.",
    "docs/archive/": "Retired documents, kept verbatim as a record.",
    "docs/adr/": "Accepted decision records are dated and immutable; they cite the names in force when decided.",
    "docs/plans/": "Superseded planning snapshots, marked as such in their own first lines.",
    "docs/audits/": "Recorded audit evidence. Out of bounds for this PR and immutable by policy.",
    "references/v4x-canon/": "Archived v4.x canon per docs/canon/SOURCE_AUTHORITY.md.",
    "assets/archive/": "Legacy artwork, retained as history and barred from active surfaces by its own README.",
    "shiroe/compat/": "The compat package exists to speak the old names.",
    "tests/fixtures/legacy/": "Fixtures reproducing pre-rename input.",
}

# Active surfaces carrying a justified legacy reference. Each entry is a single
# path (or a narrow prefix) plus the reason it is exempt. Read before adding.
ALLOWLIST: dict[str, str] = {
    # --- migration readers that cannot import the compat boundary -----------
    # Everything under shiroe/ moved behind shiroe/compat/legacy_identity.py in
    # SHR-014 and is gone from this list.
    "memory/state/schema.json": "Generated at runtime from shiroe/memory/core.py STATE_SCHEMA; records the v1 store filename it was generated for. Gitignored, so it exists only in working trees.",
    "skills/memory-import-export/SKILL.md": "Names the v3/v4.2 Zeref OS layouts its migration scripts convert from.",
    "docs/DEPRECATIONS.md": "Legacy-identity register: names the pre-rename tokens the compat boundary preserves. The scan's own subject.",

    # --- records of past runs and of the public surface as it stands --------
    "docs/RELEASE_VERDICT_2.0.0-alpha.3.md": "Dated release verdict. A record, not a live surface.",
    "docs/RELEASE_VERDICT_3.0.0-alpha.1.md": "Dated release verdict. A record, not a live surface.",
    "docs/canon/GITHUB_SURFACE_INVENTORY.md": "Quotes the live GitHub metadata verbatim, including the legacy homepageUrl awaiting owner approval.",
    "docs/canon/GITHUB_ISSUE_ACTIONS.md": "Quotes the live GitHub issue titles and bodies verbatim — including the legacy identity the proposed SHR-026 renames exist to remove. Replaces the scripts/shiroe-publish-releases.sh entry retired in the same commit, so the register did not grow.",
    "docs/canon/SHIROE_BASELINE.md": "Recorded audit baseline (SHR-004). Immutable evidence.",
    "docs/canon/SHIROE_EXECUTION_LOG.md": "Recorded audit execution log (SHR-004). Immutable evidence.",
    "docs/security/HISTORY_REDACTION_MANIFEST.md": "History-redaction evidence (SHR-029/031). Three of the fourteen historical file paths carrying the private Notion URL are spelled with the pre-rename identity, as are the commit subjects that introduced and removed it. Renaming them would falsify the evidence a rewrite decision rests on. Scoped to this one file, not to docs/security/.",

    # --- tests that pin the compat behaviour --------------------------------
    # The compat tests now read their legacy spellings from
    # shiroe/compat/legacy_identity.py, so only the two that must write the
    # tokens literally remain.
    "tests/test_install_identity.py": "Asserts the legacy identity is absent from installed payloads.",
    "tests/test_ws3_memory_coherence.py": "Names the audit run the test reproduces.",
    "tests/test_active_identity.py": "This gate's own test: it injects legacy references on purpose.",
    "scripts/check-active-identity.py": "This file. It has to spell the tokens it looks for.",

    # --- workflow path allowlist -------------------------------------------
    ".github/workflows/shr-verify.yml": "Its changed-path allowlist still admits the pre-rename zeref/ tree so old branches can be verified.",
}


def _relevant(rel: str, table: dict[str, str]) -> str | None:
    for key, reason in table.items():
        if rel == key or (key.endswith("/") and rel.startswith(key)):
            return reason
    return None


def walk_files(root: Path) -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            if name in PRUNE_DIRS:  # in a worktree `.git` is a file
                continue
            found.append(Path(dirpath, name).relative_to(root).as_posix())
    return sorted(found)


def read_text(root: Path, rel: str) -> str | None:
    path = root / rel
    if path.suffix.lower() in BINARY_SUFFIXES:
        return None
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def scan(root: Path) -> list[dict]:
    findings: list[dict] = []
    for rel in walk_files(root):
        if _relevant(rel, ARCHIVED) or _relevant(rel, ALLOWLIST):
            continue
        text = read_text(root, rel)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = LEGACY_RE.search(line)
            if match:
                findings.append({
                    "path": rel,
                    "line": lineno,
                    "token": match.group(0),
                    "excerpt": line.strip()[:160],
                })
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Active-surface identity scan (SHR-032)")
    ap.add_argument("--root", default=".", help="Repository root (default: cwd)")
    ap.add_argument("--json", action="store_true", help="Emit a JSON report on stdout")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: root is not a directory: {root}", file=sys.stderr)
        return 2

    findings = scan(root)

    if args.json:
        print(json.dumps({
            "schema": "shiroe.active-identity/v1",
            "root": str(root),
            "findings": findings,
        }, indent=2))
        return 1 if findings else 0

    if not findings:
        print(f"✔ Active-surface identity scan passed "
              f"({len(ARCHIVED)} archived prefix(es), {len(ALLOWLIST)} allowlisted path(s))")
        return 0

    print(f"Legacy identity on {len({f['path'] for f in findings})} active surface(s):",
          file=sys.stderr)
    for f in findings:
        print(f"  {f['path']}:{f['line']}: {f['excerpt']}", file=sys.stderr)
    print("\nEither rename it to Shiroe, or add the path to ALLOWLIST in "
          "scripts/check-active-identity.py with the reason it must keep the "
          "old name.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
