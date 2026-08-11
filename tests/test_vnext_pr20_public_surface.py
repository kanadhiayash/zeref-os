"""vNext PR 20 gate tests — public surface + 2.0-alpha release."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Version consistency across all surfaces
# ---------------------------------------------------------------------------

EXPECTED_VERSION = (REPO_ROOT / "shiroe" / "VERSION").read_text(encoding="utf-8").strip()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shiroe_version_file() -> None:
    # The other version tests compare their surface against EXPECTED_VERSION,
    # which is read from this file — so this one cannot also compare against
    # it without becoming a tautology. It asserts the canonical file's own
    # contract instead: present, and parseable as SemVer.
    assert EXPECTED_VERSION, "shiroe/VERSION is empty"
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.\-]+)?", EXPECTED_VERSION), (
        f"shiroe/VERSION is not SemVer: {EXPECTED_VERSION!r}"
    )


def test_pyproject_version() -> None:
    text = _read(REPO_ROOT / "pyproject.toml")
    assert f'version = "{EXPECTED_VERSION}"' in text


def test_plugin_manifest_version() -> None:
    manifest = json.loads(_read(REPO_ROOT / ".claude-plugin" / "plugin.json"))
    assert manifest["version"] == EXPECTED_VERSION


# Runtime surface is discovered from executable Python registrations, not
# tracked JSON inventory files.
def test_tracked_runtime_registries_removed() -> None:
    assert not (REPO_ROOT / "registry" / "components.json").exists()
    assert not (REPO_ROOT / "registry" / "adapters.json").exists()
    assert not (REPO_ROOT / "registry" / "capabilities.json").exists()
    assert not (REPO_ROOT / "shiroe" / "registry").exists()


# ---------------------------------------------------------------------------
# No unsupported runtime claims (§20 PR-20 gate)
# ---------------------------------------------------------------------------

def test_readme_makes_no_hardcoded_provider_claims() -> None:
    text = _read(REPO_ROOT / "README.md")
    banned = re.compile(
        r"claude-(?:opus|sonnet|haiku|fable|instant)"
        r"|gpt-[0-9]|gemini-[0-9]|codex-gpt"
    )
    # README may reference reasoning classes and harness names, but not
    # provider *model* ids.
    match = banned.search(text)
    assert not match, (
        f"README references provider model id {match.group(0)!r}; "
        f"provider ids belong under shiroe/adapters/providers/"
    )
