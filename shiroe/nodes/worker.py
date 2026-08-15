"""Worker-side identity checks and receipt production."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from shiroe.nodes.local_config import LocalNodeConfig
from shiroe.nodes.protocol import WorkPackage, WorkPackageError, validate_work_package
from shiroe.transport import TailnetIdentity


EXECUTION_RECEIPT_SCHEMA = "shiroe.execution-receipt/v1"


class WorkerIdentityError(PermissionError):
    """Raised when the controller source identity cannot be trusted."""


class WorkerExecutionError(RuntimeError):
    """Raised when a worker refuses a package before execution."""


@dataclass(frozen=True)
class ExecutionReceipt:
    schema: str
    package_digest: str
    ok: bool
    output: dict[str, Any]
    error: str | None
    exit_code: int
    stderr_tail: str | None
    metadata: dict[str, Any]
    usage: dict[str, Any]
    controller_tailnet_id_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "package_digest": self.package_digest,
            "ok": self.ok,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "stderr_tail": self.stderr_tail,
            "metadata": self.metadata,
            "usage": self.usage,
            "controller_tailnet_id_digest": self.controller_tailnet_id_digest,
        }


def source_ip_from_ssh_env(env: Mapping[str, str]) -> str:
    for key in ("SSH_CONNECTION", "SSH_CLIENT"):
        raw = env.get(key)
        if not raw:
            continue
        parts = raw.split()
        if not parts:
            continue
        source = parts[0]
        try:
            ipaddress.ip_address(source)
        except ValueError as exc:
            raise WorkerIdentityError(f"{key} source address is malformed") from exc
        return source
    raise WorkerIdentityError("missing SSH source identity")


def verify_controller_identity(
    env: Mapping[str, str],
    *,
    config: LocalNodeConfig,
    transport,
) -> TailnetIdentity:
    source = source_ip_from_ssh_env(env)
    identity = transport.whois(source)
    digest = LocalNodeConfig.digest_tailnet_id(identity.stable_id)
    if digest not in config.trusted_controller_tailscale_id_digests:
        raise WorkerIdentityError("controller stable Tailnet id is not trusted")
    return identity


def worker_run_package(
    package_data: dict[str, Any],
    *,
    config: LocalNodeConfig,
    ssh_env: Mapping[str, str],
    transport,
    capability_digest: str,
    executor: Callable[[WorkPackage], dict[str, Any]],
    now: datetime | None = None,
) -> ExecutionReceipt:
    try:
        package = validate_work_package(
            package_data,
            worker_node_id=config.node_id,
            capability_digest=capability_digest,
            now=now or datetime.now(timezone.utc),
        )
    except WorkPackageError as exc:
        raise WorkerExecutionError(str(exc)) from exc
    try:
        controller = verify_controller_identity(ssh_env, config=config, transport=transport)
    except WorkerIdentityError as exc:
        raise WorkerExecutionError(f"controller identity rejected: {exc}") from exc

    result = executor(package)
    return ExecutionReceipt(
        schema=EXECUTION_RECEIPT_SCHEMA,
        package_digest=package.digest,
        ok=bool(result.get("ok", True)),
        output=dict(result.get("output", {})),
        error=result.get("error"),
        exit_code=int(result.get("exit_code", 0)),
        stderr_tail=result.get("stderr_tail"),
        metadata=dict(result.get("metadata", {})),
        usage=dict(result.get("usage", _zero_usage())),
        controller_tailnet_id_digest=LocalNodeConfig.digest_tailnet_id(controller.stable_id),
    )


def _zero_usage() -> dict[str, Any]:
    return {"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}
