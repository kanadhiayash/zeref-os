"""Digest-bound remote work package protocol."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


WORK_PACKAGE_SCHEMA = "shiroe.work-package/v1"


class WorkPackageError(ValueError):
    """Raised when a remote work package fails identity or digest checks."""


@dataclass(frozen=True)
class WorkPackage:
    schema: str
    package_id: str
    graph_id: str
    work_node_id: str
    lease_id: str
    worker_node_id: str
    capability_id: str
    capability_digest: str
    inputs: dict[str, Any]
    timeout_s: int
    created_at: str
    expires_at: str
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_work_package(
    *,
    package_id: str,
    graph_id: str,
    work_node_id: str,
    lease_id: str,
    worker_node_id: str,
    capability_id: str,
    capability_digest: str,
    inputs: dict[str, Any],
    timeout_s: int,
    created_at: datetime | str,
    expires_at: datetime | str,
) -> WorkPackage:
    data = {
        "schema": WORK_PACKAGE_SCHEMA,
        "package_id": package_id,
        "graph_id": graph_id,
        "work_node_id": work_node_id,
        "lease_id": lease_id,
        "worker_node_id": worker_node_id,
        "capability_id": capability_id,
        "capability_digest": capability_digest,
        "inputs": dict(inputs),
        "timeout_s": int(timeout_s),
        "created_at": _iso(created_at),
        "expires_at": _iso(expires_at),
    }
    data["digest"] = package_digest(data)
    return WorkPackage(**data)


def validate_work_package(
    data: dict[str, Any],
    *,
    worker_node_id: str,
    capability_digest: str,
    now: datetime | str | None = None,
) -> WorkPackage:
    if data.get("schema") != WORK_PACKAGE_SCHEMA:
        raise WorkPackageError("wrong work package schema")
    expected_digest = package_digest(data)
    if data.get("digest") != expected_digest:
        raise WorkPackageError("work package digest mismatch")
    if data.get("worker_node_id") != worker_node_id:
        raise WorkPackageError("work package worker identity mismatch")
    if data.get("capability_digest") != capability_digest:
        raise WorkPackageError("work package capability digest mismatch")
    current = _parse_time(now or datetime.now(timezone.utc))
    expires_at = _parse_time(str(data.get("expires_at") or ""))
    if expires_at <= current:
        raise WorkPackageError("work package expired")
    try:
        return WorkPackage(**data)
    except TypeError as exc:
        raise WorkPackageError(f"malformed work package: {exc}") from exc


def package_digest(data: dict[str, Any]) -> str:
    body = {key: value for key, value in data.items() if key != "digest"}
    return "sha256:" + hashlib.sha256(_canonical_json(body)).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _iso(value: datetime | str) -> str:
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise WorkPackageError(f"invalid package timestamp {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
