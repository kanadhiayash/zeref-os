"""Load and enforce privacy, sharing, and canonical project policy at runtime.

Design goals:
- Zero external deps (stdlib only) — same rule as `shiroe.privacy`.
- Fail-closed default: missing JSON policy means no network allow.
- Content privacy scope and network destination scope are separate.
"""
from __future__ import annotations

from shiroe.env import getenv as env_get
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from shiroe.policy.loader import load_policy_stack
from shiroe.policy.precedence import resolve
from shiroe.policy.schema import Action, ActionKind, PolicyLayer, Verdict


class NetworkDeniedError(RuntimeError):
    """Raised when `network: denied` policy blocks an outbound call."""


class ConnectorDisabledError(RuntimeError):
    """Raised when SHARING_POLICY.md marks a connector disabled."""


@dataclass(frozen=True)
class SecurityPolicy:
    """Snapshot of policy-relevant runtime inputs."""

    root: Path
    content_mode: str
    network_scope: str
    connectors: Mapping[str, bool]


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


def _load_privacy(project_root: Path) -> tuple[str, str]:
    priv = project_root / "PRIVACY.md"
    if not priv.exists():
        return ("abstract", "device-only")
    fm = _parse_yaml_frontmatter(priv.read_text(errors="ignore"))
    mode = str(fm.get("mode", "abstract")).strip()
    network_scope = str(fm.get("network_scope", "device-only")).strip()
    if mode not in {"abstract", "exact"}:
        mode = "abstract"
    if network_scope not in {"device-only", "tailnet", "external"}:
        network_scope = "device-only"
    return (mode, network_scope)


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
    """Read privacy/sharing files and bind them to the canonical policy root."""
    root = project_root or Path.cwd()
    mode, network_scope = _load_privacy(root)
    connectors = _load_sharing_policy(root)
    return SecurityPolicy(
        root=root,
        content_mode=mode,
        network_scope=network_scope,
        connectors=connectors,
    )


def _env_allow_network() -> bool:
    return (env_get("ALLOW_NETWORK", "") or "").strip() in ("1", "true", "yes", "on")


def _env_allowed_connectors() -> set[str]:
    raw = env_get("ALLOW_CONNECTOR", "") or ""
    return {c.strip().lower() for c in raw.split(",") if c.strip()}


def require_network(
    policy: SecurityPolicy,
    *,
    purpose: str,
    target: str = "",
    destination_scope: str = "external",
) -> None:
    """Refuse outbound calls outside privacy/network and policy bounds."""
    if policy.network_scope == "device-only":
        raise NetworkDeniedError(f"Network egress denied for {purpose}: device-only scope")
    if policy.network_scope == "tailnet" and destination_scope == "external":
        raise NetworkDeniedError(f"Network egress denied for {purpose}: external destination outside tailnet scope")
    if destination_scope not in {"tailnet", "external"}:
        raise NetworkDeniedError(f"Network egress denied for {purpose}: unsupported destination scope {destination_scope!r}")

    action = Action(ActionKind.network, target=target or purpose)
    stack = load_policy_stack(policy.root)
    if _env_allow_network():
        stack.append(
            PolicyLayer(
                name="explicit-user-grant",
                allows=frozenset({ActionKind.network}),
                network_hosts=(target or purpose,),
            )
        )
    decision = resolve(action, stack)
    if decision.verdict is Verdict.allow:
        return
    raise NetworkDeniedError(
        f"Network egress denied for {purpose} to {target or purpose}: {decision.reason}"
    )


def require_connector(policy: SecurityPolicy, name: str, *, purpose: str) -> None:
    """Refuse the connector call unless SHARING_POLICY.md enables it, or env override."""
    name_l = name.strip().lower()
    if name_l in _env_allowed_connectors():
        require_network(policy, purpose=f"{name_l}:{purpose}", target=name_l, destination_scope="external")
        return
    if policy.connectors.get(name_l, False):
        require_network(policy, purpose=f"{name_l}:{purpose}", target=name_l, destination_scope="external")
        return
    raise ConnectorDisabledError(
        f"Connector '{name_l}' disabled by SHARING_POLICY.md for {purpose}. "
        f"Enable it in SHARING_POLICY.md, or set "
        f"SHIROE_ALLOW_CONNECTOR={name_l} for the session."
    )
