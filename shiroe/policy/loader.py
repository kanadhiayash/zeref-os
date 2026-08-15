"""Load a policy stack from disk.

Layer files (all optional):

- Runtime invariants  → hardcoded here.
- Project deny        → .shiroe/policy/deny.json
- Project defaults    → .shiroe/policy/defaults.json
- Global deny         → ~/.shiroe/policies/deny.json
- Global defaults     → ~/.shiroe/policies/defaults.json

Missing layers are dropped silently (default-deny still applies).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from shiroe.policy.schema import ActionKind, PolicyLayer


def _runtime_invariants() -> PolicyLayer:
    # Denies that no config can turn off.
    return PolicyLayer(
        name="runtime-invariant",
        denies=frozenset({
            # Reserved: event-log tampering + redaction bypass are guarded in
            # code paths, not via ActionKind — the invariant layer's job here
            # is to remain a fail-closed anchor even when empty.
        }),
    )


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _mk_layer(name: str, data: dict) -> PolicyLayer | None:
    if not data:
        return None
    denies = frozenset(ActionKind(k) for k in data.get("deny", []) if _is_kind(k))
    allows = frozenset(ActionKind(k) for k in data.get("allow", []) if _is_kind(k))
    if (
        not denies
        and not allows
        and not data.get("fs_write_scopes")
        and not data.get("fs_read_scopes")
        and not data.get("network_hosts")
    ):
        return None
    return PolicyLayer(
        name=name,
        denies=denies,
        allows=allows,
        fs_write_scopes=tuple(data.get("fs_write_scopes", ())),
        fs_read_scopes=tuple(data.get("fs_read_scopes", ())),
        network_hosts=tuple(data.get("network_hosts", ())),
    )


def _is_kind(name: str) -> bool:
    try:
        ActionKind(name)
        return True
    except ValueError:
        return False


WORKSPACE_DIR = ".shiroe"


def _workspace_file(root: Path, *parts: str) -> Path:
    """Path under the current Shiroe workspace directory."""
    return root.joinpath(WORKSPACE_DIR, *parts)


def load_policy_stack(project_root: Path | str,
                      *,
                      global_root: Path | None = None) -> list[PolicyLayer]:
    project_root = Path(project_root)
    home = Path(os.path.expanduser("~"))
    if global_root is None:
        global_root = home / WORKSPACE_DIR / "policies"

    stack: list[PolicyLayer] = [_runtime_invariants()]

    for src, name in (
        (_workspace_file(project_root, "policy", "deny.json"), "project-deny"),
        (global_root / "deny.json", "global-deny"),
    ):
        layer = _mk_layer(name, _load_json(src))
        if layer:
            stack.append(layer)

    proj_defaults = _mk_layer(
        "project-defaults",
        _load_json(_workspace_file(project_root, "policy", "defaults.json")),
    )
    if proj_defaults:
        stack.append(proj_defaults)

    global_defaults = _mk_layer("global-defaults", _load_json(global_root / "defaults.json"))
    if global_defaults:
        stack.append(global_defaults)

    return stack
