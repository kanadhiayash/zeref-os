"""Provider-neutral transport records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TailnetPeer:
    host: str
    ip: str
    online: bool
    os: str = ""


@dataclass(frozen=True)
class ProbeResult:
    host: str
    reachable: bool
    path_type: str
    latency_ms: float | None
    raw: str


@dataclass(frozen=True)
class TailnetIdentity:
    stable_id: str
    name: str
    user_login: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class TailnetStatus:
    backend_state: str
    peers: tuple[TailnetPeer, ...]
    self_stable_id: str = ""
    self_host: str = ""
