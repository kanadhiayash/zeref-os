from __future__ import annotations

import json

from shiroe.nodes.store import NodeStore
from shiroe.storage import EventEnvelope, EventLog, StateDB


NEW_EVENT_TYPES = (
    "node.registered",
    "node.trust_changed",
    "node.probed",
    "node.lease_acquired",
    "node.lease_completed",
    "node.lease_failed",
    "transfer.started",
    "transfer.completed",
    "transfer.rejected",
    "remote.execution_started",
    "remote.execution_completed",
    "remote.execution_failed",
)


def test_d3_event_types_are_registered(tmp_path) -> None:
    with StateDB(tmp_path) as db:
        db.migrate()
        log = EventLog(tmp_path, mirror_conn=db.connect())
        for event_type in NEW_EVENT_TYPES:
            log.append(EventEnvelope(event_type=event_type, actor="test", payload={"id": "x"}))


def test_node_store_emits_bounded_canonical_events(tmp_path) -> None:
    store = NodeStore(tmp_path, id_factory=lambda: "node_worker")
    node = store.register_candidate(
        name="Node1",
        role="worker",
        transport_host="node1.tailnet.ts.net",
        ssh_user="shiroe_worker",
        capability_digest="sha256:cap",
    )
    store.trust_node(node.id, trusted=True)
    lease = store.acquire_lease(graph_id="graph1", work_node_id="work1", node_id=node.id)
    store.complete_lease(lease.id)

    rows = store.conn.execute(
        "SELECT event_type, payload FROM memory_events ORDER BY rowid"
    ).fetchall()
    events = [(row[0], json.loads(row[1])) for row in rows]

    assert [event_type for event_type, _payload in events] == [
        "node.registered",
        "node.trust_changed",
        "node.lease_acquired",
        "node.lease_completed",
    ]
    for _event_type, payload in events:
        assert set(payload) <= {
            "node_id",
            "graph_id",
            "work_node_id",
            "lease_id",
            "trusted",
            "role",
            "transport",
            "transport_host",
            "state",
        }
        assert "ssh_user" not in payload
        assert "capability_digest" not in payload
