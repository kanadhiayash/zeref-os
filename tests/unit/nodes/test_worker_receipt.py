from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shiroe.nodes.local_config import LocalNodeConfig
from shiroe.nodes.protocol import make_work_package
from shiroe.nodes.worker import WorkerExecutionError, worker_run_package
from shiroe.transport import TailnetIdentity


NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self, stable_id: str = "n-controller") -> None:
        self.stable_id = stable_id

    def whois(self, source: str) -> TailnetIdentity:
        return TailnetIdentity(
            stable_id=self.stable_id,
            name="node0.tailnet.ts.net",
            user_login="controller@example.com",
            tags=(),
        )


def _config() -> LocalNodeConfig:
    return LocalNodeConfig(
        node_id="node_worker",
        role="worker",
        trusted_controller_tailscale_ids=("n-controller",),
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


def test_worker_run_creates_receipt_bound_to_package_digest() -> None:
    package = _package()

    receipt = worker_run_package(
        package,
        config=_config(),
        ssh_env={"SSH_CONNECTION": "100.64.0.1 55555 100.64.0.2 22"},
        transport=FakeTransport(),
        capability_digest="sha256:cap",
        executor=lambda work_package: {"output": {"seen": work_package.inputs["value"]}},
        now=NOW,
    )

    assert receipt.schema == "shiroe.execution-receipt/v1"
    assert receipt.package_digest == package["digest"]
    assert receipt.ok is True
    assert receipt.output == {"seen": 1}
    assert receipt.controller_tailnet_id == "n-controller"


def test_worker_run_rejects_capability_drift_before_execution() -> None:
    called = False

    def executor(_package):
        nonlocal called
        called = True
        return {}

    with pytest.raises(WorkerExecutionError, match="capability digest"):
        worker_run_package(
            _package(),
            config=_config(),
            ssh_env={"SSH_CONNECTION": "100.64.0.1 55555 100.64.0.2 22"},
            transport=FakeTransport(),
            capability_digest="sha256:other",
            executor=executor,
            now=NOW,
        )

    assert called is False


def test_worker_run_rejects_untrusted_controller_before_execution() -> None:
    with pytest.raises(WorkerExecutionError, match="controller identity"):
        worker_run_package(
            _package(),
            config=_config(),
            ssh_env={"SSH_CONNECTION": "100.64.0.1 55555 100.64.0.2 22"},
            transport=FakeTransport(stable_id="n-other"),
            capability_digest="sha256:cap",
            executor=lambda _package: {},
            now=NOW,
        )
