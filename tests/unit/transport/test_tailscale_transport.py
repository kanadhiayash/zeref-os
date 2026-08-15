from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from shiroe.transport.tailscale import TailscaleTransport, TransportError


def _fake_tailscale(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "tailscale"
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_discover_parses_running_tailnet_status(tmp_path: Path) -> None:
    fake = _fake_tailscale(
        tmp_path,
        """
import json, sys
assert sys.argv[1:] == ["status", "--json"], sys.argv
print(json.dumps({
    "BackendState": "Running",
    "Self": {"ID": "n-controller", "DNSName": "node0.tailnet.ts.net."},
    "Peer": {
        "node1": {
            "DNSName": "node1.tailnet.ts.net.",
            "HostName": "node1",
            "TailscaleIPs": ["100.64.0.2"],
            "Online": True,
            "OS": "linux",
        }
    },
}))
""",
    )

    status = TailscaleTransport(command=fake).discover()

    assert status.backend_state == "Running"
    assert status.self_stable_id == "n-controller"
    assert status.self_host == "node0.tailnet.ts.net"
    assert status.peers[0].host == "node1.tailnet.ts.net"
    assert status.peers[0].ip == "100.64.0.2"
    assert status.peers[0].online is True
    assert status.peers[0].os == "linux"


def test_discover_fails_when_backend_not_running(tmp_path: Path) -> None:
    fake = _fake_tailscale(
        tmp_path,
        """
import json
print(json.dumps({"BackendState": "NeedsLogin", "Peer": {}}))
""",
    )

    with pytest.raises(TransportError, match="BackendState"):
        TailscaleTransport(command=fake).discover()


def test_discover_fails_on_invalid_json(tmp_path: Path) -> None:
    fake = _fake_tailscale(tmp_path, "print('not json')\n")

    with pytest.raises(TransportError, match="invalid JSON"):
        TailscaleTransport(command=fake).discover()


def test_discover_fails_when_cli_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(TransportError, match="tailscale CLI not found"):
        TailscaleTransport(command="tailscale").discover()


def test_probe_parses_ping_path_and_latency(tmp_path: Path) -> None:
    fake = _fake_tailscale(
        tmp_path,
        """
import sys
assert sys.argv[1:] == ["ping", "--c", "1", "node1"], sys.argv
print("pong from node1 (100.64.0.2) via DERP(tor) in 42.5ms")
""",
    )

    result = TailscaleTransport(command=fake).probe("node1")

    assert result.host == "node1"
    assert result.reachable is True
    assert result.path_type == "relay"
    assert result.latency_ms == 42.5
    assert "DERP" in result.raw


def test_probe_reports_unreachable_from_failed_ping(tmp_path: Path) -> None:
    fake = _fake_tailscale(
        tmp_path,
        """
import sys
print("timeout waiting for pong")
raise SystemExit(1)
""",
    )

    result = TailscaleTransport(command=fake).probe("node1")

    assert result.reachable is False
    assert result.path_type == "unreachable"
    assert result.latency_ms is None


def test_whois_reads_stable_identity_from_json(tmp_path: Path) -> None:
    fake = _fake_tailscale(
        tmp_path,
        """
import json, sys
assert sys.argv[1:] == ["whois", "--json", "100.64.0.2:22"], sys.argv
print(json.dumps({
    "Node": {
        "ID": "n123",
        "Name": "node1.tailnet.ts.net.",
        "Tags": ["tag:shiroe-worker"],
    },
    "UserProfile": {"LoginName": "worker@example.com"},
}))
""",
    )

    identity = TailscaleTransport(command=fake).whois("100.64.0.2:22")

    assert identity.stable_id == "n123"
    assert identity.name == "node1.tailnet.ts.net"
    assert identity.user_login == "worker@example.com"
    assert identity.tags == ("tag:shiroe-worker",)


def test_transport_never_invokes_tailscale_mutation_commands(tmp_path: Path) -> None:
    fake = _fake_tailscale(
        tmp_path,
        """
import os, sys
with open(os.environ["CALLS"], "a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")
print('{"BackendState":"Running","Peer":{}}')
""",
    )
    calls = tmp_path / "calls.txt"
    env = {**os.environ, "CALLS": str(calls)}

    TailscaleTransport(command=fake, env=env).discover()

    assert calls.read_text(encoding="utf-8").splitlines() == ["status --json"]
