"""Load + enforce PRIVACY / SHARING_POLICY / PERMISSIONS at runtime.

Design goals:
- Zero external deps (stdlib only) — same rule as `shiroe.privacy`.
- Fail-closed default: if the policy files are missing or unparseable,
  every connector / network call is denied.
- Env-var opt-in for the session override lane so scripted / CI work
  can consent without editing tracked files:

    SHIROE_ALLOW_NETWORK=1                    # blanket per-session allow
    SHIROE_ALLOW_CONNECTOR=github,litellm     # per-connector allow

- Every call site (LLM egress, sync outbound)
  routes through `require_connector` / `require_network` before running.
"""
from __future__ import annotations

import os

from shiroe.env import getenv as env_get
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class NetworkDeniedError(RuntimeError):
    """Raised when `network: denied` policy blocks an outbound call."""


class ConnectorDisabledError(RuntimeError):
    """Raised when SHARING_POLICY.md marks a connector disabled."""


@dataclass(frozen=True)
class SecurityPolicy:
    """Snapshot of the four policy files at load time."""

    privacy_mode: str
    external_transmission: bool
    network_denied: bool
    connectors: Mapping[str, bool]
    local_only_blocks: tuple[str, ...]


def _parse_yaml_frontmatter(text: str) -> dict:
    """Extract the first `---` frontmatter block; return {} if none.

    Deliberately minimal: no YAML dep. Handles the field shapes actually
    used in this project.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    out: dict = {}
    current_list: list | None = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent == 0:
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                current_list = []
                out[key] = current_list
            else:
                current_list = None
                if value.lower() in ("true", "false"):
                    out[key] = (value.lower() == "true")
                elif value.lower() in ("on", "off"):
                    out[key] = (value.lower() == "on")
                else:
                    out[key] = value.strip('"').strip("'")
        elif current_list is not None and stripped.startswith("- "):
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
    return out


def _load_privacy(project_root: Path) -> tuple[str, bool, tuple[str, ...]]:
    priv = project_root / "PRIVACY.md"
    if not priv.exists():
        return ("local-only", False, ())
    fm = _parse_yaml_frontmatter(priv.read_text(errors="ignore"))
    mode = str(fm.get("mode", "abstract")).strip()
    ext = fm.get("external_transmission", False)
    if isinstance(ext, str):
        ext = ext.lower() in ("on", "true", "yes", "1")
    blocks = tuple(fm.get("local_only_blocks", []) or ())
    return (mode, bool(ext), blocks)


def _load_permissions(project_root: Path) -> bool:
    """Return True if network is denied (default: denied, fail-closed).

    config/PERMISSIONS.md can enable network egress by declaring either
    `network: allowed` inline or `- allowed` as the first entry under a
    `network:` list key. Any explicit `denied` entry wins over `allowed`.
    A missing or unreadable file denies. This is the file lane referenced by
    `require_network`'s error message; PRIVACY.md `external_transmission`
    must ALSO be on for the file lane to authorize a call.
    """
    perms = project_root / "config" / "PERMISSIONS.md"
    if not perms.exists():
        return True
    try:
        text = perms.read_text(errors="ignore")
    except OSError:
        return True
    lowered = text.lower()
    block = re.search(
        r"^\s*network:\s*$\n(?P<body>(?:^\s+-\s*[a-z_-]+\s*$\n?)+)",
        lowered,
        re.MULTILINE,
    )
    if "network: denied" in lowered:
        return True
    if block and re.search(r"-\s*denied\b", block.group("body")):
        return True
    if "network: allowed" in lowered:
        return False
    if block and re.search(r"-\s*allowed\b", block.group("body")):
        return False
    return True


def _load_sharing_policy(project_root: Path) -> dict[str, bool]:
    sp = project_root / "SHARING_POLICY.md"
    if not sp.exists():
        return {}
    text = sp.read_text(errors="ignore")
    connectors: dict[str, bool] = {}
    for match in re.finditer(
        r"^\s{2}(?P<name>[a-z_]+):\s*\n(?:\s{4}.*\n)*?\s{4}enabled:\s*(?P<val>true|false)\s*$",
        text,
        re.MULTILINE | re.IGNORECASE,
    ):
        connectors[match.group("name").strip()] = match.group("val").lower() == "true"
    return connectors


def load_policy(project_root: Path | None = None) -> SecurityPolicy:
    """Read the four policy files and return the merged SecurityPolicy."""
    root = project_root or Path.cwd()
    mode, ext_ok, blocks = _load_privacy(root)
    net_denied = _load_permissions(root)
    connectors = _load_sharing_policy(root)
    return SecurityPolicy(
        privacy_mode=mode,
        external_transmission=ext_ok,
        network_denied=net_denied,
        connectors=connectors,
        local_only_blocks=blocks,
    )


def _env_allow_network() -> bool:
    return (env_get("ALLOW_NETWORK", "") or "").strip() in ("1", "true", "yes", "on")


def _env_allowed_connectors() -> set[str]:
    raw = env_get("ALLOW_CONNECTOR", "") or ""
    return {c.strip().lower() for c in raw.split(",") if c.strip()}


def require_network(policy: SecurityPolicy, *, purpose: str) -> None:
    """Refuse the outbound call unless policy or env override authorizes it."""
    if _env_allow_network():
        return
    if not policy.network_denied and policy.external_transmission:
        return
    raise NetworkDeniedError(
        f"Network egress denied for {purpose}. "
        f"Enable in config/PERMISSIONS.md + PRIVACY.md external_transmission, "
        f"or set SHIROE_ALLOW_NETWORK=1 for the session."
    )


def require_connector(policy: SecurityPolicy, name: str, *, purpose: str) -> None:
    """Refuse the connector call unless SHARING_POLICY.md enables it, or env override."""
    name_l = name.strip().lower()
    if name_l in _env_allowed_connectors():
        return
    if policy.connectors.get(name_l, False):
        require_network(policy, purpose=f"{name_l}:{purpose}")
        return
    raise ConnectorDisabledError(
        f"Connector '{name_l}' disabled by SHARING_POLICY.md for {purpose}. "
        f"Enable it in SHARING_POLICY.md, or set "
        f"SHIROE_ALLOW_CONNECTOR={name_l} for the session."
    )
