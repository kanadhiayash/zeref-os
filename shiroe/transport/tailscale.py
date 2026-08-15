"""Tailscale transport discovery.

This adapter treats Tailscale as transport only. It never performs login, up,
down, set, or credential-file operations.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Mapping

from shiroe.transport.base import ProbeResult, TailnetIdentity, TailnetPeer, TailnetStatus


class TransportError(RuntimeError):
    """Raised when transport discovery cannot produce trustworthy data."""


class TailscaleTransport:
    def __init__(
        self,
        *,
        command: str | Path = "tailscale",
        timeout: float = 10.0,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.command = os.fspath(command)
        self.timeout = timeout
        self.env = dict(env) if env is not None else None

    def discover(self) -> TailnetStatus:
        data = self._json(["status", "--json"])
        backend_state = str(data.get("BackendState") or "")
        if backend_state != "Running":
            raise TransportError(f"tailscale BackendState is {backend_state!r}, expected 'Running'")
        peers = tuple(_peer_from_status(peer) for peer in _peer_values(data.get("Peer")))
        self_node = data.get("Self") if isinstance(data.get("Self"), dict) else {}
        return TailnetStatus(
            backend_state=backend_state,
            peers=peers,
            self_stable_id=str(self_node.get("ID") or ""),
            self_host=_clean_host(str(self_node.get("DNSName") or self_node.get("HostName") or "")),
        )

    def probe(self, host: str) -> ProbeResult:
        proc = self._run(["ping", "--c", "1", host], check=False)
        raw = _combined_output(proc)
        if proc.returncode != 0:
            return ProbeResult(
                host=host,
                reachable=False,
                path_type="unreachable",
                latency_ms=None,
                raw=raw,
            )
        return ProbeResult(
            host=host,
            reachable=True,
            path_type=_path_type(raw),
            latency_ms=_latency_ms(raw),
            raw=raw,
        )

    def whois(self, source: str) -> TailnetIdentity:
        data = self._json(["whois", "--json", source])
        node = data.get("Node")
        if not isinstance(node, dict):
            raise TransportError("tailscale whois JSON missing Node object")
        stable_id = str(node.get("ID") or "")
        if not stable_id:
            raise TransportError("tailscale whois JSON missing stable Node.ID")
        profile = data.get("UserProfile") if isinstance(data.get("UserProfile"), dict) else {}
        tags = node.get("Tags") if isinstance(node.get("Tags"), list) else []
        return TailnetIdentity(
            stable_id=stable_id,
            name=_clean_host(str(node.get("Name") or "")),
            user_login=str(profile.get("LoginName") or ""),
            tags=tuple(str(tag) for tag in tags),
        )

    def _json(self, args: list[str]) -> dict:
        proc = self._run(args, check=True)
        raw = _combined_output(proc)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TransportError(f"tailscale {' '.join(args)} returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise TransportError(f"tailscale {' '.join(args)} returned non-object JSON")
        return data

    def _run(self, args: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        command = self._resolve_command()
        try:
            proc = subprocess.run(
                [command, *args],
                capture_output=True,
                check=False,
                encoding="utf-8",
                env=self.env,
                shell=False,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise TransportError(f"tailscale {' '.join(args)} timed out") from exc
        except FileNotFoundError as exc:
            raise TransportError("tailscale CLI not found") from exc
        if check and proc.returncode != 0:
            raw = _combined_output(proc).strip()
            detail = f": {raw}" if raw else ""
            raise TransportError(f"tailscale {' '.join(args)} failed{detail}")
        return proc

    def _resolve_command(self) -> str:
        if os.path.sep in self.command or (os.path.altsep and os.path.altsep in self.command):
            path = Path(self.command)
            if not path.exists():
                raise TransportError("tailscale CLI not found")
            return str(path)
        resolved = shutil.which(self.command, path=(self.env or os.environ).get("PATH"))
        if resolved is None:
            raise TransportError("tailscale CLI not found")
        return resolved


def _peer_values(value: object) -> tuple[dict, ...]:
    if isinstance(value, dict):
        return tuple(peer for peer in value.values() if isinstance(peer, dict))
    if isinstance(value, list):
        return tuple(peer for peer in value if isinstance(peer, dict))
    return ()


def _peer_from_status(peer: dict) -> TailnetPeer:
    ips = peer.get("TailscaleIPs")
    ip = str(ips[0]) if isinstance(ips, list) and ips else ""
    host = _clean_host(str(peer.get("DNSName") or peer.get("HostName") or peer.get("ID") or ""))
    return TailnetPeer(
        host=host,
        ip=ip,
        online=bool(peer.get("Online")),
        os=str(peer.get("OS") or ""),
    )


def _clean_host(host: str) -> str:
    return host.rstrip(".")


def _combined_output(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


def _path_type(raw: str) -> str:
    lowered = raw.lower()
    if "peer relay" in lowered:
        return "peer-relay"
    if "derp" in lowered or " relay" in lowered:
        return "relay"
    if "pong" in lowered:
        return "direct"
    return "unreachable"


def _latency_ms(raw: str) -> float | None:
    match = re.search(r"\bin\s+([0-9]+(?:\.[0-9]+)?)ms\b", raw)
    if not match:
        return None
    return float(match.group(1))
