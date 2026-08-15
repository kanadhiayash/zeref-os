from __future__ import annotations

import json
import re
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "docs" / "canon" / "SOURCE_AUTHORITY.md"
CANON_SCRIPT = ROOT / "scripts" / "check-canon-consistency.py"

OPERATIONAL_PATHS = (
    "config/PROJECT.md",
    ".claude-plugin/plugin.json",
    ".cursor/rules/shiroe.mdc",
    ".windsurfrules",
    ".aider.conf.yml.example",
    "scripts/release_ready.py",
    "scripts/shiroe-validate.py",
    ".github/workflows/shr-verify.yml",
)


def test_operational_paths_are_tiered_not_unscoped() -> None:
    amap = _authority_map()
    for rel in OPERATIONAL_PATHS:
        tier_hits = [
            tier["id"]
            for tier in amap["tiers"]
            if any(canon._matches(pattern, rel) for pattern in tier["paths"])
            and not any(canon._matches(pattern, rel) for pattern in tier.get("exclude", ()))
        ]
        unscoped_hits = [pattern for pattern in amap["unscoped"] if canon._matches(pattern, rel)]
        assert tier_hits, f"{rel} is not assigned to an authority tier"
        assert not unscoped_hits, f"{rel} is still unscoped via {unscoped_hits}"


def _authority_map() -> dict:
    text = AUTHORITY.read_text(encoding="utf-8")
    match = re.search(r"```json\s+shiroe\.source-authority/v1\s*\n(.*?)\n```", text, re.DOTALL)
    assert match, "source authority JSON block missing"
    return json.loads(match.group(1))


def _canon_module():
    spec = importlib.util.spec_from_file_location("check_canon_consistency", CANON_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_canon_consistency"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


canon = _canon_module()
