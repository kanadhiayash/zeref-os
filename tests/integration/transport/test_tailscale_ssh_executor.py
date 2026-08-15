from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from shiroe.adapters.capabilities.base import AdapterResult
from shiroe.nodes.protocol import make_work_package
from shiroe.nodes.store import NodeRecord
from shiroe.transport import ProbeResult
from shiroe.transport.tailscale_ssh import RemoteExecutionError, execute_remote_package


NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
CONTROLLER_DIGEST = sha256(b"n-controller").hexdigest()


class FakeTransport:
    def __init__(self, reachable: bool = True) -> None:
        self.hosts: list[str] = []
        self.reachable = reachable

    def probe(self, host: str) -> ProbeResult:
        self.hosts.append(host)
        return ProbeResult(
            host=host,
            reachable=self.reachable,
            path_type="direct" if self.reachable else "unreachable",
            latency_ms=1.0 if self.reachable else None,
            raw="pong" if self.reachable else "timeout",
        )


def _write_policy(root: Path) -> None:
    (root / "PRIVACY.md").write_text(
        "---\nmode: abstract\nnetwork_scope: tailnet\n---\n",
        encoding="utf-8",
    )
    policy = root / ".shiroe" / "policy"
    policy.mkdir(parents=True)
    (policy / "defaults.json").write_text(
        json.dumps({"allow": ["network"], "network_hosts": ["worker-a.tailnet.ts.net"]}),
        encoding="utf-8",
    )


def _node() -> NodeRecord:
    return NodeRecord(
        id="node_worker",
        name="WorkerA",
        role="worker",
        transport="tailscale",
        transport_host="worker-a.tailnet.ts.net",
        ssh_user="shiroe_worker",
        tailscale_stable_id="n-worker",
        trusted=True,
        status="unknown",
        capabilities=("cap.remote",),
        capability_digest="sha256:cap",
        last_seen_at=None,
        created_at="2026-08-15T00:00:00+00:00",
        updated_at="2026-08-15T00:00:00+00:00",
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


def _fake_executable(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_tailscale_ssh_executor_runs_fixed_scp_and_ssh_commands(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    package = _package()
    calls = tmp_path / "calls.jsonl"
    scp = _fake_executable(
        tmp_path / "scp",
        f"""
import json, sys
with open({str(calls)!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"tool": "scp", "argv": sys.argv[1:]}}) + "\\n")
raise SystemExit(0)
""",
    )
    ssh = _fake_executable(
        tmp_path / "ssh",
        f"""
import json, sys
with open({str(calls)!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"tool": "ssh", "argv": sys.argv[1:]}}) + "\\n")
print(json.dumps({{
    "schema": "shiroe.execution-receipt/v1",
    "package_digest": {package["digest"]!r},
    "ok": True,
    "output": {{"done": True}},
    "error": None,
    "exit_code": 0,
    "stderr_tail": None,
    "metadata": {{}},
    "usage": {{"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}},
    "controller_tailnet_id_digest": {CONTROLLER_DIGEST!r}
}}))
""",
    )
    transport = FakeTransport()

    result = execute_remote_package(
        tmp_path,
        node=_node(),
        package=package,
        transport=transport,
        scp_command=scp,
        ssh_command=ssh,
    )

    lines = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
    assert isinstance(result, AdapterResult)
    assert result.ok is True
    assert result.output == {"done": True}
    assert transport.hosts == ["worker-a.tailnet.ts.net"]
    assert lines[0]["tool"] == "scp"
    assert lines[0]["argv"][1] == "shiroe_worker@worker-a.tailnet.ts.net:~/.shiroe/inbox/pkg_1.json"
    assert lines[1]["tool"] == "ssh"
    assert lines[1]["argv"] == [
        "-o",
        "BatchMode=yes",
        "shiroe_worker@worker-a.tailnet.ts.net",
        "shiroe",
        "node",
        "worker-run",
        "--package",
        "~/.shiroe/inbox/pkg_1.json",
        "--json",
    ]


def test_tailscale_ssh_executor_rejects_wrong_package_receipt(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    scp = _fake_executable(tmp_path / "scp", "raise SystemExit(0)\n")
    ssh = _fake_executable(
        tmp_path / "ssh",
        f"""
import json
print(json.dumps({{
    "schema": "shiroe.execution-receipt/v1",
    "package_digest": "sha256:wrong",
    "ok": True,
    "output": {{}},
    "error": None,
    "exit_code": 0,
    "stderr_tail": None,
    "metadata": {{}},
    "usage": {{"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}},
    "controller_tailnet_id_digest": {CONTROLLER_DIGEST!r}
}}))
""",
    )

    with pytest.raises(RemoteExecutionError, match="package digest"):
        execute_remote_package(
            tmp_path,
            node=_node(),
            package=_package(),
            transport=FakeTransport(),
            scp_command=scp,
            ssh_command=ssh,
        )


def test_tailscale_ssh_executor_respects_policy_default_deny(tmp_path: Path) -> None:
    (tmp_path / "PRIVACY.md").write_text(
        "---\nmode: abstract\nnetwork_scope: device-only\n---\n",
        encoding="utf-8",
    )

    with pytest.raises(RemoteExecutionError, match="Network egress denied"):
        execute_remote_package(
            tmp_path,
            node=_node(),
            package=_package(),
            transport=FakeTransport(),
            scp_command=tmp_path / "scp",
            ssh_command=tmp_path / "ssh",
        )


def test_tailscale_ssh_executor_rejects_unreachable_peer(tmp_path: Path) -> None:
    _write_policy(tmp_path)

    with pytest.raises(RemoteExecutionError, match="unreachable"):
        execute_remote_package(
            tmp_path,
            node=_node(),
            package=_package(),
            transport=FakeTransport(reachable=False),
            scp_command=tmp_path / "scp",
            ssh_command=tmp_path / "ssh",
        )
