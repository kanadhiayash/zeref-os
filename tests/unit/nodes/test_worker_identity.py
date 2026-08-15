from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from shiroe.nodes.local_config import LocalNodeConfig, LocalNodeConfigError, load_local_node_config
from shiroe.nodes.worker import WorkerIdentityError, source_ip_from_ssh_env, verify_controller_identity
from shiroe.transport import TailnetIdentity


CONTROLLER_DIGEST = sha256(b"n-controller").hexdigest()


class FakeTransport:
    def __init__(self, stable_id: str = "n-controller") -> None:
        self.sources: list[str] = []
        self.stable_id = stable_id

    def whois(self, source: str) -> TailnetIdentity:
        self.sources.append(source)
        return TailnetIdentity(
            stable_id=self.stable_id,
            name="controller.tailnet.ts.net",
            user_login="controller@example.com",
            tags=("tag:controller",),
        )


def test_load_local_node_config_rejects_secret_material(tmp_path: Path) -> None:
    path = tmp_path / "node.json"
    path.write_text(
        json.dumps(
            {
                "schema": "shiroe.node-local/v1",
                "node_id": "node_worker",
                "role": "worker",
                "trusted_controller_tailscale_id_digests": [CONTROLLER_DIGEST],
                "auth_key": "tskey-secret",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(LocalNodeConfigError, match="secret"):
        load_local_node_config(path)


def test_source_ip_from_ssh_env_uses_client_address() -> None:
    assert source_ip_from_ssh_env(
        {"SSH_CONNECTION": "100.64.0.1 55555 100.64.0.2 22"}
    ) == "100.64.0.1"
    assert source_ip_from_ssh_env({"SSH_CLIENT": "100.64.0.3 55555 22"}) == "100.64.0.3"


@pytest.mark.parametrize("env", [{}, {"SSH_CONNECTION": "not-an-ip 1 2 3"}])
def test_source_ip_from_ssh_env_fails_closed(env: dict[str, str]) -> None:
    with pytest.raises(WorkerIdentityError):
        source_ip_from_ssh_env(env)


def test_verify_controller_identity_requires_trusted_stable_id() -> None:
    config = LocalNodeConfig(
        node_id="node_worker",
        role="worker",
        trusted_controller_tailscale_id_digests=(CONTROLLER_DIGEST,),
    )
    transport = FakeTransport(stable_id="n-controller")

    identity = verify_controller_identity(
        {"SSH_CONNECTION": "100.64.0.1 55555 100.64.0.2 22"},
        config=config,
        transport=transport,
    )

    assert identity.stable_id == "n-controller"
    assert transport.sources == ["100.64.0.1"]


def test_verify_controller_identity_rejects_wrong_controller() -> None:
    config = LocalNodeConfig(
        node_id="node_worker",
        role="worker",
        trusted_controller_tailscale_id_digests=(CONTROLLER_DIGEST,),
    )

    with pytest.raises(WorkerIdentityError, match="not trusted"):
        verify_controller_identity(
            {"SSH_CONNECTION": "100.64.0.1 55555 100.64.0.2 22"},
            config=config,
            transport=FakeTransport(stable_id="n-other"),
        )
