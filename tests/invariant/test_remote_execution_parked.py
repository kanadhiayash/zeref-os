"""Parked remote execution must fail closed, never fabricate success.

Node0/Node1 live execution is parked/out of scope. worker-run without a real
configured executor must NOT report ok=true; it must return a structured parked
marker (status "parked", code "REMOTE_EXECUTION_NOT_ENABLED").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

from shiroe.cli.node import REMOTE_EXECUTION_NOT_ENABLED, default_worker_executor
from shiroe.nodes.local_config import LocalNodeConfig
from shiroe.nodes.protocol import make_work_package
from shiroe.nodes.worker import worker_run_package
from shiroe.transport import TailnetIdentity


NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
CONTROLLER_DIGEST = sha256(b"n-controller").hexdigest()


class FakeTransport:
    def whois(self, source: str) -> TailnetIdentity:
        return TailnetIdentity(
            stable_id="n-controller",
            name="controller.tailnet.ts.net",
            user_login="controller@example.com",
            tags=(),
        )


def _config() -> LocalNodeConfig:
    return LocalNodeConfig(
        node_id="node_worker",
        role="worker",
        trusted_controller_tailscale_id_digests=(CONTROLLER_DIGEST,),
    )


def _package() -> dict:
    return make_work_package(
        package_id="pkg_1",
        graph_id="graph1",
        work_node_id="work1",
        lease_id="lease_1",
        worker_node_id="node_worker",
        capability_id="cap.remote",
        capability_digest="sha256:cap",
        inputs={"value": 1},
        timeout_s=30,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    ).to_dict()


def _run(executor) -> object:
    return worker_run_package(
        _package(),
        config=_config(),
        ssh_env={"SSH_CONNECTION": "100.64.0.1 55555 100.64.0.2 22"},
        transport=FakeTransport(),
        capability_digest="sha256:cap",
        executor=executor,
        now=NOW,
    )


def test_absent_ok_is_treated_as_false() -> None:
    # An executor that omits "ok" must never default to success.
    receipt = _run(lambda _package: {"output": {}})
    assert receipt.ok is False


def test_default_worker_executor_returns_parked_marker() -> None:
    result = default_worker_executor(_package())
    assert result["ok"] is False
    assert result["metadata"]["status"] == "parked"
    assert result["metadata"]["code"] == REMOTE_EXECUTION_NOT_ENABLED


def test_worker_run_with_default_executor_fails_closed() -> None:
    receipt = _run(default_worker_executor)
    assert receipt.ok is False
    assert receipt.metadata["status"] == "parked"
    assert receipt.metadata["code"] == "REMOTE_EXECUTION_NOT_ENABLED"
    assert receipt.error
