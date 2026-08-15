"""Tailscale plus SSH/SCP remote package executor."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from shiroe.adapters.capabilities.base import AdapterResult
from shiroe.nodes.store import NodeRecord
from shiroe.security import NetworkDeniedError, load_policy, require_network
from shiroe.storage import EventEnvelope, EventLog


_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_SSH_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


class RemoteExecutionError(RuntimeError):
    """Raised when remote execution fails a transport or receipt invariant."""


def execute_remote_package(
    root: Path | str,
    *,
    node: NodeRecord,
    package: dict[str, Any],
    transport,
    scp_command: str | Path = "scp",
    ssh_command: str | Path = "ssh",
    timeout_s: int | None = None,
) -> AdapterResult:
    root_path = Path(root)
    _validate_node(node)
    package_id = _validate_package_id(str(package.get("package_id") or ""))
    package_digest = str(package.get("digest") or "")
    log = EventLog(root_path)
    try:
        require_network(
            load_policy(root_path),
            purpose="remote worker execution",
            target=node.transport_host,
            destination_scope="tailnet",
        )
    except NetworkDeniedError as exc:
        _emit(log, "remote.execution_failed", node=node, package=package, status="policy_denied")
        raise RemoteExecutionError(str(exc)) from exc

    probe = transport.probe(node.transport_host)
    if not probe.reachable:
        _emit(log, "remote.execution_failed", node=node, package=package, status="unreachable")
        raise RemoteExecutionError(f"remote worker {node.transport_host} unreachable: {probe.raw}")

    _emit(
        log,
        "remote.execution_started",
        node=node,
        package=package,
        status="started",
        extra={"path_type": probe.path_type},
    )
    remote_path = f"~/.shiroe/inbox/{package_id}.json"
    remote = f"{node.ssh_user}@{node.transport_host}:{remote_path}"
    try:
        with tempfile.TemporaryDirectory(prefix="shiroe-package-") as tmpdir:
            local_package = Path(tmpdir) / f"{package_id}.json"
            local_package.write_text(
                json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            _emit(log, "transfer.started", node=node, package=package, status="started")
            try:
                _run([os.fspath(scp_command), str(local_package), remote], timeout_s=timeout_s)
            except RemoteExecutionError:
                _emit(log, "transfer.rejected", node=node, package=package, status="failed")
                raise
            _emit(log, "transfer.completed", node=node, package=package, status="completed")
            ssh = _run(
                [
                    os.fspath(ssh_command),
                    "-o",
                    "BatchMode=yes",
                    f"{node.ssh_user}@{node.transport_host}",
                    "shiroe",
                    "node",
                    "worker-run",
                    "--package",
                    remote_path,
                    "--json",
                ],
                timeout_s=timeout_s,
            )
        receipt = _parse_receipt(ssh.stdout)
        if receipt.get("schema") != "shiroe.execution-receipt/v1":
            raise RemoteExecutionError("remote worker returned wrong receipt schema")
        if receipt.get("package_digest") != package_digest:
            raise RemoteExecutionError("remote worker receipt package digest mismatch")
        _emit(log, "remote.execution_completed", node=node, package=package, status="completed")
        return AdapterResult(
            ok=bool(receipt.get("ok")),
            output=receipt.get("output"),
            error=receipt.get("error"),
            exit_code=receipt.get("exit_code"),
            stderr_tail=receipt.get("stderr_tail"),
            metadata=dict(receipt.get("metadata") or {}),
            usage=receipt.get("usage"),
        )
    except Exception:
        _emit(log, "remote.execution_failed", node=node, package=package, status="failed")
        raise


def _validate_node(node: NodeRecord) -> None:
    if node.role != "worker" or node.transport != "tailscale" or not node.trusted:
        raise RemoteExecutionError("remote execution requires a trusted tailscale worker node")
    if not _HOST_RE.fullmatch(node.transport_host) or ".." in node.transport_host:
        raise RemoteExecutionError("invalid worker transport_host")
    if not _SSH_USER_RE.fullmatch(node.ssh_user):
        raise RemoteExecutionError("invalid worker ssh_user")


def _validate_package_id(package_id: str) -> str:
    if (
        not _PACKAGE_ID_RE.fullmatch(package_id)
        or "/" in package_id
        or "\\" in package_id
        or ".." in package_id
    ):
        raise RemoteExecutionError("invalid package_id for remote inbox path")
    return package_id


def _run(args: list[str], *, timeout_s: int | None) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            check=False,
            encoding="utf-8",
            shell=False,
            timeout=timeout_s,
        )
    except FileNotFoundError as exc:
        raise RemoteExecutionError(f"remote transport executable not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RemoteExecutionError(f"remote transport command timed out: {args[0]}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise RemoteExecutionError(f"remote transport command failed: {args[0]}{suffix}")
    return proc


def _parse_receipt(raw: str) -> dict[str, Any]:
    try:
        receipt = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RemoteExecutionError("remote worker returned invalid receipt JSON") from exc
    if not isinstance(receipt, dict):
        raise RemoteExecutionError("remote worker receipt must be a JSON object")
    return receipt


def _emit(
    log: EventLog,
    event_type: str,
    *,
    node: NodeRecord,
    package: dict[str, Any],
    status: str,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "node_id": node.id,
        "package_id": package.get("package_id"),
        "package_digest": package.get("digest"),
        "status": status,
    }
    if extra:
        payload.update(extra)
    log.append(
        EventEnvelope(
            event_type=event_type,
            actor="shiroe",
            target=f"node:{node.id}",
            payload=payload,
        )
    )
