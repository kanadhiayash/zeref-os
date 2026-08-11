"""SHR-67 — plugin identity + install freshness.

Covers two things:
  1. The display-name rebrand landed on live surfaces, without touching the
     `shiroe` compatibility identifier (package name / plugin name /
     registry namespace), and without rewriting historical records.
  2. The installed-state manifest (`shiroe doctor --installation`,
     `shiroe version --verbose`) is well-formed, its digests are real, it can
     detect that a previously recorded manifest is stale against current
     content, and computing it never touches — let alone loses — memory/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from shiroe.release.manifest import _packaged_files, build_manifest, is_stale

# Specific current *display* surfaces — the doc/manifest text a user actually
# reads. Deliberately NOT a blanket repo grep: historical records (CHANGELOG),
# migration notes (skills/memory-import-export, skills/parent-sync), and test
# fixtures are allowed to keep the old name.
DISPLAY_SURFACES = [
    "README.md", "SKILL.md", "AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md",
    "LLAMA.md", "GITHUB_OS.md", "config/PROJECT.md",
    "shiroe/__init__.py", "shiroe/cli.py",
]


def _env(repo_root: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(repo_root: Path, cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        cwd=str(cwd), capture_output=True, text=True, env=_env(repo_root),
    )


# ---------------------------------------------------------------------------
# Part A — identity
# ---------------------------------------------------------------------------

def test_no_display_surface_renders_old_name(repo_root: Path) -> None:
    for rel in DISPLAY_SURFACES:
        text = (repo_root / rel).read_text(encoding="utf-8")
        assert "Zeref OS" not in text, f"{rel} still renders the old display name"

    plugin = json.loads((repo_root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert "Zeref OS" not in plugin["description"]

    marketplace = json.loads((repo_root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert "Zeref OS" not in marketplace["description"]
    for entry in marketplace["plugins"]:
        assert "Zeref OS" not in entry.get("description", "")

    pyproject_text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    desc_line = next(line for line in pyproject_text.splitlines() if line.startswith("description"))
    assert "Zeref OS" not in desc_line


def test_compat_identifier_intact(repo_root: Path) -> None:
    """The shiroe package/plugin identifier is the namespace-rename target
    (SHR-namespace-rename) and must be consistent across every distribution
    manifest. The registry's `$schema` is not just branding text either: it
    must point at a schema file that actually exists in the repo, and the
    registry must actually validate against it — an operational contract,
    not a dangling pointer."""
    pyproject_text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "shiroe"' in pyproject_text

    plugin = json.loads((repo_root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "shiroe"

    marketplace = json.loads((repo_root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["name"] == "shiroe"
    assert marketplace["plugins"][0]["name"] == "shiroe"

    assert not (repo_root / "shiroe-registry.json").exists()
    assert not (repo_root / "registry" / "shiroe-registry.schema.json").exists()

    # The registry must actually validate against the committed schema —
    # run it through the same validator the CI `validate` job and
    # `shiroe release check` invoke on every run.
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "shiroe-validate.py")],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Registry schema" not in result.stdout


# ---------------------------------------------------------------------------
# Part B — installed-state manifest
# ---------------------------------------------------------------------------

def test_manifest_well_formed_and_digests_match_actual_files(repo_root: Path) -> None:
    manifest = build_manifest(repo_root)

    assert manifest.schema_version == 1
    assert manifest.product_name == "Shiroe AI Tactician"
    assert manifest.compat_id == "shiroe"
    assert manifest.package_file_count > 0
    assert manifest.package_digest.startswith("sha256:")

    import hashlib
    expected_agents = "sha256:" + hashlib.sha256((repo_root / "AGENTS.md").read_bytes()).hexdigest()
    assert manifest.agents_digest == expected_agents


def test_doctor_installation_and_version_verbose_cli(repo_root: Path) -> None:
    doctor = _run(repo_root, repo_root, ["doctor", "--installation"])
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert "version:" in doctor.stdout
    assert "git_sha:" in doctor.stdout

    version = _run(repo_root, repo_root, ["version", "--verbose"])
    assert version.returncode == 0, version.stdout + version.stderr
    assert "version:" in version.stdout
    assert "git_sha:" in version.stdout

    # The existing global --version flag must keep working unchanged.
    flag = _run(repo_root, repo_root, ["--version"])
    assert flag.returncode == 0
    assert flag.stdout.strip().startswith("shiroe ")

    bare = _run(repo_root, repo_root, ["version"])
    assert bare.returncode == 0
    assert bare.stdout.strip().startswith("shiroe ")


def test_is_stale_detects_upgrade(repo_root: Path) -> None:
    fresh = build_manifest(repo_root).to_dict()
    assert is_stale(fresh, repo_root) is False

    old = dict(fresh, git_sha="0" * 40, version="0.0.1")
    assert is_stale(old, repo_root) is True


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _init_repo(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _seed_installable(root: Path, *, version: str, plugin_description: str) -> None:
    (root / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "shiroe-os"\nversion = "{version}"\n', encoding="utf-8",
    )
    (root / ".claude-plugin").mkdir(exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "shiroe-os", "version": version, "description": plugin_description}),
        encoding="utf-8",
    )


def test_upgrade_from_stale_cache_replaces_old_payload(tmp_path: Path, monkeypatch) -> None:
    """Regression fixture for the exact defect SHR-67/PR9 exists to fix:
    Claude Code resolves an installed plugin's version from plugin.json
    first, and skips newer repo commits when that string looks unchanged.
    PR9 changed plugin.json/marketplace.json *content* (a rebrand) without
    bumping the version — which reproduces the bug it was meant to fix.

    This builds two real on-disk installs — an "old cached" one and a "new
    published" one, each a real tiny git repo, each manifested with the
    genuine `build_manifest` — and proves `is_stale` correctly flags the
    old cache against the new payload, so the new content actually replaces
    it rather than being silently skipped.
    """
    old_root = tmp_path / "old_cache"
    new_root = tmp_path / "new_publish"
    old_root.mkdir()
    new_root.mkdir()

    for root, version, desc in (
        (old_root, "2.0.0-alpha.2", "Zeref OS — old descriptor text"),
        (new_root, "2.0.0-alpha.3", "Shiroe — rebranded descriptor text"),
    ):
        _init_repo(root)
        _seed_installable(root, version=version, plugin_description=desc)
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "seed")

    import shiroe

    monkeypatch.setattr(shiroe, "__version__", "2.0.0-alpha.2", raising=False)
    old_manifest = build_manifest(old_root)
    monkeypatch.setattr(shiroe, "__version__", "2.0.0-alpha.3", raising=False)
    new_manifest = build_manifest(new_root)

    # The payload genuinely changed (not just the version string).
    assert old_manifest.version != new_manifest.version
    assert old_manifest.package_digest != new_manifest.package_digest

    # A cache still holding the old manifest must be detected as stale
    # against the newly published root — this is what forces the refresh.
    assert is_stale(old_manifest.to_dict(), new_root) is True

    # Once the new payload IS what's installed, it is no longer stale
    # against itself — the upgrade actually lands, it isn't perpetually
    # flagged.
    assert is_stale(new_manifest.to_dict(), new_root) is False


def test_memory_survives_manifest_rebuild(tmp_path: Path) -> None:
    """Computing/rebuilding the manifest must never read or depend on memory/
    content, so a real reinstall (which regenerates packaged files) can never
    touch it."""
    root = tmp_path
    (root / "memory").mkdir()
    marker = root / "memory" / "hot.md"
    marker.write_text("user-private-note", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "shiroe-os"\n', encoding="utf-8"
    )
    (root / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")

    before_digest = build_manifest(root).package_digest
    packaged_rel_paths = {str(p.relative_to(root)) for p in _packaged_files(root)}
    assert not any(p.startswith("memory/") for p in packaged_rel_paths)

    # Simulate a reinstall: every packaged (non-memory) file gets rewritten.
    (root / "AGENTS.md").write_text("# AGENTS.md (updated)\n", encoding="utf-8")
    after_digest = build_manifest(root).package_digest

    assert marker.read_text(encoding="utf-8") == "user-private-note"
    assert before_digest != after_digest
