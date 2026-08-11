"""Installed-state manifest (SHR-67).

Describes what is *actually on disk* at a given root right now: product
identity, package/plugin version, source repo, git position, and content
digests. Computed live on every call — never cached to a file — so it can
never itself go stale the way the Claude Code plugin-cache payload can.

Root cause this exists for: Claude Code resolves an installed plugin's
version from ``plugin.json`` first; if that string does not change between
publishes, new repository commits are silently skipped and a stale cached
payload keeps being served. This module gives operators a way to see what
is really installed (via ``shiroe doctor --installation`` / ``shiroe version
--verbose``) and to compare a previously recorded manifest against current
content to detect drift.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
PRODUCT_NAME = "Shiroe AI Tactician"

# Directories never included in the packaged-file digest even without git:
# generated caches, VCS internals, and — critically — memory/, which is the
# user's own mutable data and must never affect the "is my install stale"
# signal (see tests/test_install_identity.py: memory survives a reinstall).
_EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".pytest_cache", ".shiroe-sandbox", "memory", ".claude",
}


@dataclass(frozen=True)
class InstalledManifest:
    schema_version: int
    product_name: str
    compat_id: str
    version: str
    source_repo: str | None
    git_sha: str | None
    release_tag: str | None
    agents_digest: str | None
    package_file_count: int
    package_digest: str
    generated_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    def format_text(self) -> str:
        lines = [
            f"product: {self.product_name} (compat: {self.compat_id})",
            f"version: {self.version}",
            f"source_repo: {self.source_repo or 'unknown'}",
            f"git_sha: {self.git_sha or 'unknown (not a git checkout)'}",
            f"release_tag: {self.release_tag or 'none'}",
            f"agents_digest: {self.agents_digest or 'unavailable'}",
            f"package_files: {self.package_file_count}",
            f"package_digest: {self.package_digest}",
            f"schema_version: {self.schema_version}",
            f"generated_at: {self.generated_at}",
        ]
        return "\n".join(lines) + "\n"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _compat_id(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            name = data.get("project", {}).get("name")
            if name:
                return name
        except Exception:  # noqa: BLE001 — best effort, fall through
            pass
    return "shiroe"


def _source_repo(root: Path) -> str | None:
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            return data.get("project", {}).get("urls", {}).get("Homepage")
        except Exception:  # noqa: BLE001
            pass
    return None


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _packaged_files(root: Path) -> list[Path]:
    tracked = _git(root, "ls-files")
    if tracked is not None:
        return sorted(
            root / rel for rel in tracked.splitlines()
            if rel and not rel.startswith("memory/")
        )
    # Non-git install (e.g. a flat copy without .git): walk the tree.
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in _EXCLUDED_DIRS for part in rel_parts):
            continue
        out.append(p)
    return sorted(out)


def _digest_files(root: Path, files: list[Path]) -> str:
    h = hashlib.sha256()
    for p in files:
        rel = str(p.relative_to(root))
        try:
            data = p.read_bytes()
        except OSError:
            continue
        h.update(rel.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(data).digest())
    return "sha256:" + h.hexdigest()


def build_manifest(root: Path) -> InstalledManifest:
    from shiroe import __version__ as version

    files = _packaged_files(root)
    return InstalledManifest(
        schema_version=SCHEMA_VERSION,
        product_name=PRODUCT_NAME,
        compat_id=_compat_id(root),
        version=version,
        source_repo=_source_repo(root),
        git_sha=_git(root, "rev-parse", "HEAD"),
        release_tag=_git(root, "describe", "--tags", "--exact-match", "HEAD"),
        agents_digest=_sha256_file(root / "AGENTS.md"),
        package_file_count=len(files),
        package_digest=_digest_files(root, files),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def is_stale(recorded: dict, root: Path) -> bool:
    """True if a previously recorded manifest no longer matches ``root``.

    Compares the content-identity fields only (version, git position, and
    the package digest) — cosmetic fields like ``generated_at`` never count.
    """
    current = build_manifest(root).to_dict()
    identity_fields = ("version", "git_sha", "package_digest", "agents_digest")
    return any(recorded.get(field) != current.get(field) for field in identity_fields)


if __name__ == "__main__":  # pragma: no cover — manual smoke check
    import json

    m = build_manifest(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())
    print(json.dumps(m.to_dict(), indent=2, sort_keys=True))
