"""Dispatch Work Nodes to trusted remote Shiroe workers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from shiroe.adapters.capabilities.base import AdapterResult
from shiroe.capabilities.store import CapabilityStore
from shiroe.nodes.protocol import make_work_package
from shiroe.nodes.store import NodeStore
from shiroe.transport import TailscaleTransport
from shiroe.transport.tailscale_ssh import execute_remote_package
from shiroe.work.schema import WorkNode


class NodeDispatcher:
    def __init__(
        self,
        root: Path | str,
        *,
        remote_executor: Callable[..., AdapterResult] | None = None,
        transport: Any | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = Path(root)
        self.remote_executor = remote_executor or execute_remote_package
        self.transport = transport or TailscaleTransport()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def invoke(
        self,
        *,
        graph_id: str,
        work_node: WorkNode,
        capability_id: str,
        inputs: dict[str, Any],
        timeout_s: int,
    ) -> AdapterResult:
        if work_node.placement.mode != "node" or not work_node.placement.node_id:
            raise ValueError("NodeDispatcher requires node placement")
        node_store = NodeStore(self.root)
        node = node_store.get_node(work_node.placement.node_id)
        current_digest = _capability_digest(self.root, capability_id)
        if node.capability_digest != current_digest:
            raise RuntimeError("worker capability digest does not match controller capability")
        lease = node_store.acquire_lease(
            graph_id=graph_id,
            work_node_id=work_node.id,
            node_id=node.id,
            ttl_s=timeout_s,
        )
        now = self.clock()
        package = make_work_package(
            package_id="pkg_" + uuid.uuid4().hex,
            graph_id=graph_id,
            work_node_id=work_node.id,
            lease_id=lease.id,
            worker_node_id=node.id,
            capability_id=capability_id,
            capability_digest=current_digest,
            inputs=inputs,
            timeout_s=timeout_s,
            created_at=now,
            expires_at=now + timedelta(seconds=timeout_s),
        ).to_dict()
        try:
            result = self.remote_executor(
                self.root,
                node=node,
                package=package,
                transport=self.transport,
            )
            if result.ok:
                node_store.complete_lease(lease.id)
            else:
                node_store.fail_lease(lease.id)
            return result
        except Exception:
            node_store.fail_lease(lease.id)
            raise


def _capability_digest(root: Path, capability_id: str) -> str:
    store = CapabilityStore(root)
    try:
        row = store.get(capability_id)
    finally:
        store.close()
    if row is None:
        raise KeyError(capability_id)
    return str(row["current_digest"])
