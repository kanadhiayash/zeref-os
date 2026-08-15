from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shiroe.nodes.store import NodeStore, NodeValidationError


def test_register_candidate_distinguishes_logical_and_transport_identity(tmp_path) -> None:
    store = NodeStore(tmp_path, id_factory=lambda: "node_abc123")

    node = store.register_candidate(
        name="WorkerA",
        role="worker",
        transport_host="worker-a.tailnet.ts.net",
        ssh_user="shiroe_worker",
        tailscale_stable_id="n123",
        capabilities=("cap.remote.exec",),
        capability_digest="sha256:abc",
    )

    assert node.id == "node_abc123"
    assert node.transport_host == "worker-a.tailnet.ts.net"
    assert node.tailscale_stable_id == "n123"
    assert node.trusted is False
    assert node.capabilities == ("cap.remote.exec",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transport_host", "worker-a; rm -rf /"),
        ("ssh_user", "root;touch pwned"),
        ("role", "admin"),
        ("transport", "ssh"),
    ],
)
def test_register_candidate_validates_conservative_identity_fields(tmp_path, field, value) -> None:
    kwargs = {
        "name": "WorkerA",
        "role": "worker",
        "transport": "tailscale",
        "transport_host": "worker-a.tailnet.ts.net",
        "ssh_user": "shiroe_worker",
    }
    kwargs[field] = value

    with pytest.raises(NodeValidationError):
        NodeStore(tmp_path).register_candidate(**kwargs)


def test_untrusted_or_controller_node_cannot_acquire_lease(tmp_path) -> None:
    store = NodeStore(tmp_path, id_factory=lambda: "node_worker")
    worker = store.register_candidate(
        name="WorkerA",
        role="worker",
        transport_host="worker-a.tailnet.ts.net",
        ssh_user="shiroe_worker",
    )

    with pytest.raises(PermissionError, match="trusted worker"):
        store.acquire_lease(graph_id="graph1", work_node_id="work1", node_id=worker.id)

    store.trust_node(worker.id, trusted=True)
    controller = NodeStore(tmp_path, id_factory=lambda: "node_controller").register_candidate(
        name="Controller",
        role="controller",
        transport_host="controller.tailnet.ts.net",
        ssh_user="shiroe",
    )
    store.trust_node(controller.id, trusted=True)

    with pytest.raises(PermissionError, match="trusted worker"):
        store.acquire_lease(graph_id="graph1", work_node_id="work1", node_id=controller.id)


def test_one_active_lease_per_work_node(tmp_path) -> None:
    store = NodeStore(tmp_path, id_factory=lambda: "node_worker")
    node = store.register_candidate(
        name="WorkerA",
        role="worker",
        transport_host="worker-a.tailnet.ts.net",
        ssh_user="shiroe_worker",
    )
    store.trust_node(node.id, trusted=True)

    first = store.acquire_lease(graph_id="graph1", work_node_id="work1", node_id=node.id)

    with pytest.raises(RuntimeError, match="active lease"):
        store.acquire_lease(graph_id="graph1", work_node_id="work1", node_id=node.id)

    assert store.get_lease(first.id).state == "active"


def test_expired_active_lease_is_marked_expired_before_replacement(tmp_path) -> None:
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    store = NodeStore(tmp_path, id_factory=lambda: "node_worker", clock=lambda: now)
    node = store.register_candidate(
        name="WorkerA",
        role="worker",
        transport_host="worker-a.tailnet.ts.net",
        ssh_user="shiroe_worker",
    )
    store.trust_node(node.id, trusted=True)
    first = store.acquire_lease(
        graph_id="graph1",
        work_node_id="work1",
        node_id=node.id,
        ttl_s=1,
    )

    later = now + timedelta(seconds=2)
    replacement_store = NodeStore(
        tmp_path,
        id_factory=lambda: "node_worker",
        lease_id_factory=lambda: "lease_replacement",
        clock=lambda: later,
    )
    replacement = replacement_store.acquire_lease(
        graph_id="graph1",
        work_node_id="work1",
        node_id=node.id,
        ttl_s=60,
    )

    assert replacement.id == "lease_replacement"
    assert replacement_store.get_lease(first.id).state == "expired"
    assert replacement_store.get_lease(replacement.id).state == "active"


def test_completed_lease_is_not_completed_twice(tmp_path) -> None:
    store = NodeStore(tmp_path, id_factory=lambda: "node_worker")
    node = store.register_candidate(
        name="WorkerA",
        role="worker",
        transport_host="worker-a.tailnet.ts.net",
        ssh_user="shiroe_worker",
    )
    store.trust_node(node.id, trusted=True)
    lease = store.acquire_lease(graph_id="graph1", work_node_id="work1", node_id=node.id)

    completed = store.complete_lease(lease.id)
    again = store.complete_lease(lease.id)

    assert completed.state == "completed"
    assert again.id == completed.id
    assert len(store.leases_for_work_node("work1", state="completed")) == 1
