"""``shiroe.capability/v1`` manifest schema + validator (stdlib only)."""

from __future__ import annotations

import json
from pathlib import Path

CAPABILITY_SCHEMA = "shiroe.capability/v1"

_ALLOWED_TYPES = {
    "cli", "repository_tool", "script", "workflow", "evaluator", "api_service",
}

_REQUIRED_TOP = ("schema", "id", "name", "type", "version", "source",
                 "entrypoint", "requires")

_REQUIRED_SOURCE = ("kind",)  # location + digest may be inferred at discovery
_REQUIRED_ENTRYPOINT = ("adapter",)
_EXECUTABLE_ENTRYPOINT_KEYS = ("command", "callable", "url")


class ManifestError(ValueError):
    """Raised for schema violations."""


def validate_manifest(manifest: dict) -> None:
    if manifest.get("schema") != CAPABILITY_SCHEMA:
        raise ManifestError(
            f"expected schema {CAPABILITY_SCHEMA!r}, got {manifest.get('schema')!r}"
        )
    for field in _REQUIRED_TOP:
        if field not in manifest:
            raise ManifestError(f"missing required field {field!r}")
    if manifest["type"] not in _ALLOWED_TYPES:
        raise ManifestError(
            f"type {manifest['type']!r} not in {sorted(_ALLOWED_TYPES)}"
        )
    src = manifest["source"]
    if not isinstance(src, dict):
        raise ManifestError("source must be an object")
    for f in _REQUIRED_SOURCE:
        if f not in src:
            raise ManifestError(f"source.{f} required")
    ep = manifest["entrypoint"]
    if not isinstance(ep, dict):
        raise ManifestError("entrypoint must be an object")
    for f in _REQUIRED_ENTRYPOINT:
        if f not in ep:
            raise ManifestError(f"entrypoint.{f} required")
    if not any(ep.get(key) for key in _EXECUTABLE_ENTRYPOINT_KEYS):
        raise ManifestError("entrypoint must declare an executable command, callable, or url")
    reqs = manifest["requires"]
    if not isinstance(reqs, dict):
        raise ManifestError("requires must be an object")


def infer_manifest(path: Path, *, capability_id: str,
                   name: str | None = None,
                   type_: str = "script") -> dict:
    """Produce a draft ``shiroe.capability/v1`` manifest for a directory that
    ships no manifest of its own. Every discovered capability starts with a
    draft; a human approves before the state machine advances beyond
    ``inspected``."""
    if type_ not in _ALLOWED_TYPES:
        raise ManifestError(f"cannot infer manifest with unknown type {type_!r}")
    return {
        "schema": CAPABILITY_SCHEMA,
        "id": capability_id,
        "name": name or path.name,
        "type": type_,
        "version": "0.0.0-draft",
        "source": {
            "kind": "local-directory",
            "location": str(path),
        },
        "entrypoint": {
            "adapter": "cli",
            "command": [str(path)] if path.is_file() else [],
        },
        "provides": [],
        "requires": {
            "filesystem": {"read": [], "write": []},
            "network": "none",
            "secrets": [],
            "subprocess": False,
            "external_write": False,
        },
        "trust": {
            "lifecycle": "discovered",
            "approval_source": None,
            "benchmark_minimum": 0.0,
        },
    }


def parse_manifest_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(data)
    return data
