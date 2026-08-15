from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run(cwd: Path, args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    merged = {**os.environ, "PYTHONPATH": str(ROOT)}
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        cwd=cwd,
        env=merged,
        text=True,
        capture_output=True,
    )


def test_doctor_reports_runtime_health_only(tmp_path: Path) -> None:
    assert _run(ROOT, ["init", str(tmp_path), "--name", "doctor", "--privacy", "abstract"]).returncode == 0
    result = _run(tmp_path, ["doctor", "--json"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {check["name"] for check in payload["checks"]}
    assert {
        "canonical_state",
        "hash_chain",
        "policy_stack",
        "policy_default_deny",
        "privacy_redaction",
        "capability_store",
        "adapters",
        "schema_version",
        "legacy_scaffold_absent",
    } <= names
    assert "claim_gate" not in names
    assert "release" not in result.stdout.lower()
    assert "benchmark" not in result.stdout.lower()


def test_doctor_fails_when_default_deny_is_widened(tmp_path: Path) -> None:
    assert _run(ROOT, ["init", str(tmp_path), "--name", "doctor", "--privacy", "abstract"]).returncode == 0
    policy_file = tmp_path / ".shiroe" / "policy" / "defaults.json"
    policy_file.write_text(json.dumps({"allow": ["network"]}), encoding="utf-8")

    result = _run(tmp_path, ["doctor", "--json"])

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    check = next(check for check in payload["checks"] if check["name"] == "policy_default_deny")
    assert check["status"] == "fail"


def test_doctor_fails_when_legacy_scaffold_paths_exist(tmp_path: Path) -> None:
    assert _run(ROOT, ["init", str(tmp_path), "--name", "doctor", "--privacy", "abstract"]).returncode == 0
    (tmp_path / "Skills").mkdir()

    result = _run(tmp_path, ["doctor", "--json"])

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    check = next(check for check in payload["checks"] if check["name"] == "legacy_scaffold_absent")
    assert check["status"] == "fail"
    assert "Skills" in check["detail"]


def test_doctor_checks_configured_tailscale_nodes_without_mutation(tmp_path: Path) -> None:
    assert _run(
        ROOT,
        ["init", str(tmp_path), "--name", "doctor", "--privacy", "abstract", "--network-scope", "tailnet"],
    ).returncode == 0
    (tmp_path / ".shiroe" / "policy" / "defaults.json").write_text(
        json.dumps({"allow": ["capability.invoke", "subprocess", "network"], "network_hosts": ["node1.tailnet.ts.net"]}),
        encoding="utf-8",
    )
    registered = _run(
        tmp_path,
        [
            "node",
            "register",
            "--name",
            "Node1",
            "--host",
            "node1.tailnet.ts.net",
            "--ssh-user",
            "shiroe_worker",
            "--tailscale-stable-id",
            "n-worker",
            "--json",
        ],
    )
    assert registered.returncode == 0, registered.stderr
    node = json.loads(registered.stdout)
    trusted = _run(tmp_path, ["node", "trust", node["id"], "--json"])
    assert trusted.returncode == 0, trusted.stderr
    fake = tmp_path / "tailscale"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if args == ['status', '--json']:\n"
        "    print(json.dumps({'BackendState': 'Running', 'Self': {'ID': 'n-controller', 'DNSName': 'node0.tailnet.ts.net.'}, 'Peer': {}}))\n"
        "elif args == ['ping', '--c', '1', 'node1.tailnet.ts.net']:\n"
        "    print('pong from node1 (100.64.0.2) via direct in 3ms')\n"
        "elif args == ['whois', '--json', 'node1.tailnet.ts.net']:\n"
        "    print(json.dumps({'Node': {'ID': 'n-worker', 'Name': 'node1.'}, 'UserProfile': {'LoginName': 'worker@example.com'}}))\n"
        "else:\n"
        "    raise SystemExit(f'unexpected tailscale args: {args!r}')\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    result = _run(
        tmp_path,
        ["doctor", "--json"],
        env={"PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", "")},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {check["name"] for check in payload["checks"]}
    assert "tailscale_cli" in names
    assert "tailscale_backend" in names
    assert "tailscale_self_identity" in names
    assert f"node:{node['id']}:peer_ping" in names
    assert f"node:{node['id']}:stable_identity" in names
    assert f"node:{node['id']}:network_policy" in names
