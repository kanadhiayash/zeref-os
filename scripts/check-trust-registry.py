#!/usr/bin/env python3
"""SHR-077..080: refuse an imported reference or public visual that has no
approved source + rights status in docs/canon/TRUST_REGISTRY.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SURFACES = (
    "README.md",
    "SOUL.md",
    "PRIVACY.md",
    "REDACT.md",
    "SHARING_POLICY.md",
    "AGENTS.md",
)
VISUAL_EXTS = {".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp"}
URL_RE = re.compile(r"https?://[^\s)\"'>]+")


def _load(registry_path: Path) -> dict:
    return json.loads(registry_path.read_text(encoding="utf-8"))


def _visuals(root: Path) -> list[str]:
    assets = root / "assets"
    if not assets.is_dir():
        return []
    out: list[str] = []
    for p in sorted(assets.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in VISUAL_EXTS:
            continue
        rel = p.relative_to(root)
        if "archive" in rel.parts:
            continue
        out.append(rel.as_posix())
    return out


def _references(root: Path, surfaces: tuple[str, ...]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name in surfaces:
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in URL_RE.finditer(text):
            url = m.group(0).rstrip(".,);:'\"")
            out.append((name, url))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    registry_path = (args.registry or (root / "docs/canon/TRUST_REGISTRY.json")).resolve()

    if not registry_path.is_file():
        print(f"trust registry missing: {registry_path}", file=sys.stderr)
        return 1

    reg = _load(registry_path)
    visual_paths = {v["path"] for v in reg.get("public_visuals", [])}
    ref_patterns = [
        re.compile(r["url_pattern"]) for r in reg.get("imported_references", [])
    ]

    problems: list[str] = []

    for rel in _visuals(root):
        if rel not in visual_paths:
            problems.append(f"public visual: {rel} has no TRUST_REGISTRY entry")

    for surface, url in _references(root, DEFAULT_SURFACES):
        if not any(p.search(url) for p in ref_patterns):
            problems.append(f"imported reference: {surface}: {url}")

    if problems:
        print("Trust registry failures:")
        for p in problems:
            print(f"  - {p}")
        print("Add each entry to docs/canon/TRUST_REGISTRY.json with an "
              "approved_source and rights_status.")
        return 1

    print(
        f"✔ Trust registry passed ({len(visual_paths)} visual(s), "
        f"{len(ref_patterns)} reference pattern(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
