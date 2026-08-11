"""Capability discovery (vNext §8.4).

Configuration lives in ``<root>/config/capability-roots.json`` (schema:
``shiroe.capability-roots/v1``). Roots are adapter-tagged; personal home
paths are never persisted resolved — the runtime expands them at scan
time and reports only ``<home>/...`` aliases in logs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOTS_SCHEMA = "shiroe.capability-roots/v1"

_DEFAULT_ROOTS = [
    {"adapter": "cli", "path": "~/.shiroe/capabilities"},
]

DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_FILES = 500
DEFAULT_MAX_BYTES = 20_000_000
_IGNORE_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv"}


@dataclass(frozen=True)
class DiscoveredCapability:
    adapter: str
    root: str              # display alias, never full home path
    path: Path             # absolute local path
    kind: str              # "script", "cli", ...
    manifest_path: Path | None = None


@dataclass
class DiscoveryLimits:
    max_depth: int = DEFAULT_MAX_DEPTH
    max_files: int = DEFAULT_MAX_FILES
    max_bytes: int = DEFAULT_MAX_BYTES
    ignore_dir_names: frozenset[str] = field(default_factory=lambda: frozenset(_IGNORE_DIR_NAMES))
    follow_symlinks: bool = False


def _load_roots(project_root: Path) -> list[dict]:
    cfg = project_root / "config" / "capability-roots.json"
    if not cfg.exists():
        return list(_DEFAULT_ROOTS)
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return list(_DEFAULT_ROOTS)
    if data.get("schema") != ROOTS_SCHEMA:
        return list(_DEFAULT_ROOTS)
    return list(data.get("roots") or _DEFAULT_ROOTS)


def _alias(path: str) -> str:
    home = os.path.expanduser("~")
    if path == home or path.startswith(home + os.sep):
        return "<home>" + path[len(home):]
    return path


def _expand(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def _looks_like_capability(path: Path) -> tuple[bool, str, Path | None]:
    """Heuristic: manifest-backed capabilities and shebang scripts only."""
    if path.is_file():
        if path.suffix in (".sh", ".py") and _has_shebang(path):
            return True, "script", None
        return False, "", None
    if not path.is_dir():
        return False, "", None
    mf = path / "manifest.json"
    if mf.exists():
        return True, "capability", mf
    return False, "", None


def _has_shebang(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            head = fh.read(2)
        return head == b"#!"
    except OSError:
        return False


def _iter_candidates(root: Path, limits: DiscoveryLimits) -> Iterable[Path]:
    if not root.exists():
        return
    seen = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=limits.follow_symlinks):
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth > limits.max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in limits.ignore_dir_names]
        yield Path(dirpath)
        for fn in filenames:
            seen += 1
            if seen > limits.max_files:
                return
            fp = Path(dirpath) / fn
            try:
                total_bytes += fp.stat().st_size
            except OSError:
                continue
            if total_bytes > limits.max_bytes:
                return
            yield fp


def discover(project_root: Path | str, *,
             limits: DiscoveryLimits | None = None) -> list[DiscoveredCapability]:
    project_root = Path(project_root)
    limits = limits or DiscoveryLimits()
    roots = _load_roots(project_root)
    out: list[DiscoveredCapability] = []
    for entry in roots:
        adapter = entry.get("adapter", "cli")
        raw_path = entry.get("path", "")
        expanded = _expand(raw_path)
        display = _alias(str(expanded))
        for candidate in _iter_candidates(expanded, limits):
            ok, kind, manifest_path = _looks_like_capability(candidate)
            if not ok:
                continue
            out.append(DiscoveredCapability(
                adapter=adapter, root=display,
                path=candidate, kind=kind, manifest_path=manifest_path,
            ))
    return out
