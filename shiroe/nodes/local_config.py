"""Worker-local node configuration.

This file lives outside the controller project database and must not contain
secrets or Tailscale auth material.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


LOCAL_NODE_SCHEMA = "shiroe.node-local/v1"
_SECRET_KEY_PARTS = ("secret", "token", "api_key", "apikey", "auth_key", "private_key", "password")
_SHA256_HEX = set("0123456789abcdef")


class LocalNodeConfigError(ValueError):
    """Raised when worker-local config is malformed or unsafe."""


@dataclass(frozen=True)
class LocalNodeConfig:
    node_id: str
    role: str
    trusted_controller_tailscale_id_digests: tuple[str, ...]
    schema: str = LOCAL_NODE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != LOCAL_NODE_SCHEMA:
            raise LocalNodeConfigError("unsupported local node config schema")
        if not self.node_id.startswith("node_"):
            raise LocalNodeConfigError("node_id must be a Shiroe node id")
        if self.role != "worker":
            raise LocalNodeConfigError("worker local config role must be worker")
        object.__setattr__(
            self,
            "trusted_controller_tailscale_id_digests",
            tuple(str(item) for item in self.trusted_controller_tailscale_id_digests),
        )
        for digest in self.trusted_controller_tailscale_id_digests:
            if len(digest) != 64 or any(ch not in _SHA256_HEX for ch in digest):
                raise LocalNodeConfigError("trusted controller ids must be SHA-256 hex digests")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "node_id": self.node_id,
            "role": self.role,
            "trusted_controller_tailscale_id_digests": list(self.trusted_controller_tailscale_id_digests),
        }

    @staticmethod
    def digest_tailnet_id(stable_id: str) -> str:
        return sha256(stable_id.encode("utf-8")).hexdigest()


def default_local_config_path(*, home: Path | None = None) -> Path:
    return (home or Path.home()) / ".shiroe" / "node.json"


def load_local_node_config(path: Path | str | None = None) -> LocalNodeConfig:
    target = Path(path) if path is not None else default_local_config_path()
    data = json.loads(target.read_text(encoding="utf-8"))
    _reject_secret_keys(data)
    try:
        return LocalNodeConfig(
            schema=data.get("schema", ""),
            node_id=data.get("node_id", ""),
            role=data.get("role", ""),
            trusted_controller_tailscale_id_digests=tuple(
                data.get("trusted_controller_tailscale_id_digests", ())
            ),
        )
    except TypeError as exc:
        raise LocalNodeConfigError(f"malformed local node config: {exc}") from exc


def save_local_node_config(config: LocalNodeConfig, path: Path | str | None = None) -> Path:
    target = Path(path) if path is not None else default_local_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Local config stores only validated SHA-256 controller identity digests.
    # codeql[py/clear-text-storage-sensitive-data]
    target.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _reject_secret_keys(value: Any, *, prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SECRET_KEY_PARTS):
                name = f"{prefix}.{key}" if prefix else str(key)
                raise LocalNodeConfigError(f"local node config must not contain secret field {name}")
            _reject_secret_keys(child, prefix=f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_keys(child, prefix=f"{prefix}[{index}]")
