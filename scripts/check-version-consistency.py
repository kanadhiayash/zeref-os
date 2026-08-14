#!/usr/bin/env python3
"""
check-version-consistency.py — Fail CI on any drift across version surfaces.

Single source of truth: shiroe/VERSION
Surfaces verified:
    - shiroe/VERSION                       (the canonical file)
    - shiroe/__init__.py:__version__       (loaded at import time)
    - pyproject.toml:[project].version
    - .claude-plugin/plugin.json:.version
    - docs/wiki/Installation.md:grep example

Identity block — single source of truth: shiroe/IDENTITY.json
Surfaces verified:
    - pyproject.toml:[project].name             == .distribution
    - pyproject.toml:[project.scripts]           has a .cli key -> "<module>.cli:main"
    - pyproject.toml:[project.urls] Homepage     == .repo_url
    - .claude-plugin/plugin.json:.name           == .distribution
    - .claude-plugin/marketplace.json:.name      == .distribution
    - .claude-plugin/marketplace.json:.plugins[0].name == .distribution
    - pyproject.toml:[project].description        == .description
    - .claude-plugin/plugin.json:.description     == .description
    - .claude-plugin/marketplace.json:.description == .description
    - .claude-plugin/marketplace.json:.plugins[0].description == .description
    - .github/CODEOWNERS (the file GitHub actually reads) exists on disk

Exit code:
    0  all surfaces agree
    1  drift detected (prints offending surfaces)
    2  the canonical VERSION file (or IDENTITY.json) is missing or malformed

Usage:
    python3 scripts/check-version-consistency.py [--root <repo-root>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CANONICAL_FILE = "shiroe/VERSION"
IDENTITY_FILE = "shiroe/IDENTITY.json"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][\w.\-]+)?$")


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8", errors="ignore")


def _read_canonical(root: Path) -> str:
    p = root / CANONICAL_FILE
    if not p.exists():
        print(f"ERROR: canonical version file missing: {p}", file=sys.stderr)
        sys.exit(2)
    v = p.read_text(encoding="utf-8").strip()
    if not SEMVER_RE.match(v):
        print(f"ERROR: canonical version '{v}' is not SemVer", file=sys.stderr)
        sys.exit(2)
    return v


def _check_pyproject(root: Path, expected: str) -> tuple[str, str | None]:
    text = _read(root, "pyproject.toml")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return ("pyproject.toml:[project].version", m.group(1) if m else None)


def _check_init(root: Path, expected: str) -> tuple[str, str | None]:
    # We do not exec the file; we treat VERSION as the canonical and check the loader is intact.
    text = _read(root, "shiroe/__init__.py")
    if "_VERSION_FILE" not in text or "VERSION" not in text:
        return ("shiroe/__init__.py loader", None)
    return ("shiroe/__init__.py loader", expected)


def _check_plugin(root: Path, expected: str) -> tuple[str, str | None]:
    data = json.loads(_read(root, ".claude-plugin/plugin.json"))
    return (".claude-plugin/plugin.json:.version", data.get("version"))


def _check_wiki_install(root: Path, expected: str) -> tuple[str, str | None]:
    text = _read(root, "docs/wiki/Installation.md")
    m = re.search(r"shiroe@shiroe\s+v(\d+\.\d+\.\d+(?:[-+][\w.\-]+)?)", text)
    return ("docs/wiki/Installation.md", m.group(1) if m else None)


def _check_skill_manifest(root: Path, expected: str) -> tuple[str, str | None]:
    # H7.3: root SKILL.md is a plugin surface with its own YAML frontmatter
    # version. Must stay locked to shiroe/VERSION so a plugin marketplace
    # cannot advertise a stale version and mislead an install.
    path = root / "SKILL.md"
    if not path.exists():
        return ("SKILL.md:frontmatter.version", None)
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"(?m)^version:\s*(\d+\.\d+\.\d+(?:[-+][\w.\-]+)?)\s*$", text)
    return ("SKILL.md:frontmatter.version", m.group(1) if m else None)


CHECKS = [
    _check_pyproject,
    _check_init,
    _check_plugin,
    _check_wiki_install,
    _check_skill_manifest,
]


def _read_identity(root: Path) -> dict:
    p = root / IDENTITY_FILE
    if not p.exists():
        print(f"ERROR: canonical identity file missing: {p}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: canonical identity file '{p}' is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)


def _check_identity_pyproject_name(root: Path, identity: dict) -> tuple[str, str, str | None]:
    text = _read(root, "pyproject.toml")
    m = re.search(r'(?m)^name\s*=\s*"([^"]+)"', text)
    return ("pyproject.toml:[project].name", identity["distribution"], m.group(1) if m else None)


def _check_identity_pyproject_scripts(root: Path, identity: dict) -> tuple[str, str, str | None]:
    text = _read(root, "pyproject.toml")
    cli = identity["cli"]
    expected = f"{identity['module']}.cli:main"
    m = re.search(rf'(?m)^{re.escape(cli)}\s*=\s*"([^"]+)"', text)
    return (f"pyproject.toml:[project.scripts].{cli}", expected, m.group(1) if m else None)


def _check_identity_pyproject_homepage(root: Path, identity: dict) -> tuple[str, str, str | None]:
    text = _read(root, "pyproject.toml")
    m = re.search(r'(?m)^Homepage\s*=\s*"([^"]+)"', text)
    return ("pyproject.toml:[project.urls].Homepage", identity["repo_url"], m.group(1) if m else None)


def _check_identity_plugin(root: Path, identity: dict) -> tuple[str, str, str | None]:
    data = json.loads(_read(root, ".claude-plugin/plugin.json"))
    return (".claude-plugin/plugin.json:.name", identity["distribution"], data.get("name"))


def _check_identity_marketplace_name(root: Path, identity: dict) -> tuple[str, str, str | None]:
    data = json.loads(_read(root, ".claude-plugin/marketplace.json"))
    return (".claude-plugin/marketplace.json:.name", identity["distribution"], data.get("name"))


def _check_identity_marketplace_plugin0(root: Path, identity: dict) -> tuple[str, str, str | None]:
    data = json.loads(_read(root, ".claude-plugin/marketplace.json"))
    plugins = data.get("plugins") or []
    observed = plugins[0].get("name") if plugins else None
    return (".claude-plugin/marketplace.json:.plugins[0].name", identity["distribution"], observed)


def _check_identity_pyproject_description(root: Path, identity: dict) -> tuple[str, str, str | None]:
    text = _read(root, "pyproject.toml")
    m = re.search(r'(?m)^description\s*=\s*"([^"]+)"', text)
    return ("pyproject.toml:[project].description", identity["description"],
            m.group(1) if m else None)


def _check_identity_plugin_description(root: Path, identity: dict) -> tuple[str, str, str | None]:
    data = json.loads(_read(root, ".claude-plugin/plugin.json"))
    return (".claude-plugin/plugin.json:.description", identity["description"],
            data.get("description"))


def _check_identity_marketplace_description(root: Path, identity: dict) -> tuple[str, str, str | None]:
    data = json.loads(_read(root, ".claude-plugin/marketplace.json"))
    return (".claude-plugin/marketplace.json:.description", identity["description"],
            data.get("description"))


def _check_identity_marketplace_plugin0_description(root: Path, identity: dict) -> tuple[str, str, str | None]:
    data = json.loads(_read(root, ".claude-plugin/marketplace.json"))
    plugins = data.get("plugins") or []
    return (".claude-plugin/marketplace.json:.plugins[0].description", identity["description"],
            plugins[0].get("description") if plugins else None)


def _check_identity_codeowners(root: Path, identity: dict) -> tuple[str, str, str | None]:
    # SHR-020: GitHub reads one CODEOWNERS per repo and prefers .github/ over
    # the root. Checking the root file passed while the rules that actually
    # governed review lived elsewhere; check the effective one.
    exists = (root / ".github" / "CODEOWNERS").exists()
    return (".github/CODEOWNERS exists", "True", str(exists) if exists else None)


IDENTITY_CHECKS = [
    _check_identity_pyproject_name,
    _check_identity_pyproject_scripts,
    _check_identity_pyproject_homepage,
    _check_identity_plugin,
    _check_identity_marketplace_name,
    _check_identity_marketplace_plugin0,
    _check_identity_pyproject_description,
    _check_identity_plugin_description,
    _check_identity_marketplace_description,
    _check_identity_marketplace_plugin0_description,
    _check_identity_codeowners,
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="Repository root (default: cwd)")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    expected = _read_canonical(root)
    print(f"canonical version (from {CANONICAL_FILE}): {expected}")

    drift: list[tuple[str, str | None]] = []
    for check in CHECKS:
        name, observed = check(root, expected)
        mark = "OK" if observed == expected else "DRIFT"
        print(f"  [{mark}] {name}: {observed!r}")
        if observed != expected:
            drift.append((name, observed))

    identity = _read_identity(root)
    print(f"\ncanonical identity (from {IDENTITY_FILE}): distribution={identity['distribution']!r}")

    identity_drift: list[tuple[str, str, str | None]] = []
    for check in IDENTITY_CHECKS:
        name, id_expected, observed = check(root, identity)
        mark = "OK" if observed == id_expected else "DRIFT"
        print(f"  [{mark}] {name}: {observed!r}")
        if observed != id_expected:
            identity_drift.append((name, id_expected, observed))

    if drift or identity_drift:
        if drift:
            print("\nVersion drift detected:", file=sys.stderr)
            for name, observed in drift:
                print(f"  - {name}: expected {expected!r}, found {observed!r}", file=sys.stderr)
        if identity_drift:
            print("\nIdentity drift detected:", file=sys.stderr)
            for name, id_expected, observed in identity_drift:
                print(f"  - {name}: expected {id_expected!r}, found {observed!r}", file=sys.stderr)
        return 1

    # R8 (SHR-AUDIT-020): also compare against the latest git tag.
    # Semantics:
    #   - `tag > VERSION` (backwards drift) — always fail unless CHANGELOG.md
    #     names the lineage restart with a `restart-from-<version>` marker.
    #   - `tag == VERSION` — fine (post-release state).
    #   - `tag < VERSION` — fine (unreleased-tag pre-release state; expected between bump and tag).
    # Intentional lineage restarts must be recorded in CHANGELOG.md.
    import subprocess
    try:
        tags = subprocess.check_output(
            ["git", "-C", str(root), "tag", "--sort=-version:refname"],
            text=True,
        ).splitlines()
    except (OSError, subprocess.CalledProcessError):
        tags = []
    latest_tag = next((t.lstrip("v") for t in tags if SEMVER_RE.match(t.lstrip("v"))), None)

    def _to_semver_tuple(v: str) -> tuple[int, int, int]:
        core = v.split("-", 1)[0].split("+", 1)[0]
        parts = (core.split(".") + ["0", "0", "0"])[:3]
        return tuple(int(p) if p.isdigit() else 0 for p in parts)  # type: ignore[return-value]

    if latest_tag:
        tag_tuple = _to_semver_tuple(latest_tag)
        expected_tuple = _to_semver_tuple(expected)
        if tag_tuple > expected_tuple:
            # Backwards drift — either intentional restart (documented) or an error.
            changelog = root / "CHANGELOG.md"
            if changelog.exists() and f"restart-from-{latest_tag}" in changelog.read_text(errors="ignore"):
                print(f"\nTag {latest_tag!r} exceeds VERSION {expected!r} — "
                      f"documented in CHANGELOG.md (restart-from-{latest_tag}).")
            else:
                print(f"\nTag divergence: latest tag {latest_tag!r} exceeds VERSION {expected!r}.",
                      file=sys.stderr)
                print("Either bump shiroe/VERSION or document the intentional lineage restart in "
                      "CHANGELOG.md with a `restart-from-<version>` marker.", file=sys.stderr)
                return 1
        elif tag_tuple < expected_tuple:
            # Pre-tag state — VERSION advanced beyond last shipped tag. Normal between bump and cut.
            print(f"\nTag {latest_tag!r} < VERSION {expected!r} — pre-tag state (VERSION bumped, tag pending).")
        else:
            print(f"\nTag {latest_tag!r} matches VERSION.")

    print("\nAll surfaces aligned on", expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
