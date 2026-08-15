from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from shiroe.nodes.protocol import make_work_package


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_DIGEST = sha256(b"n-controller").hexdigest()


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


def _init(root: Path) -> None:
    result = _run(ROOT, ["init", str(root), "--name", "node-cli", "--network-scope", "tailnet"])
    assert result.returncode == 0, result.stderr


def test_node_register_list_trust_inspect(tmp_path: Path) -> None:
    _init(tmp_path)

    registered = _run(
        tmp_path,
        [
            "node",
            "register",
            "--name",
            "WorkerA",
            "--host",
            "worker-a.tailnet.ts.net",
            "--ssh-user",
            "shiroe_worker",
            "--json",
        ],
    )
    assert registered.returncode == 0, registered.stderr
    node = json.loads(registered.stdout)
    assert node["trusted"] is False
    assert "transport_host" not in node
    assert "ssh_user" not in node
    assert "tailscale_stable_id" not in node

    trusted = _run(tmp_path, ["node", "trust", node["id"], "--json"])
    assert trusted.returncode == 0, trusted.stderr
    trusted_payload = json.loads(trusted.stdout)
    assert trusted_payload["trusted"] is True
    assert "transport_host" not in trusted_payload
    assert "ssh_user" not in trusted_payload
    assert "tailscale_stable_id" not in trusted_payload

    listed = _run(tmp_path, ["node", "list", "--json"])
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)[0]["id"] == node["id"]

    inspected = _run(tmp_path, ["node", "inspect", node["id"], "--json"])
    assert inspected.returncode == 0, inspected.stderr
    inspected_payload = json.loads(inspected.stdout)
    assert inspected_payload["id"] == node["id"]
    assert "transport_host" not in inspected_payload


def test_node_probe_uses_tailscale_transport_without_mutation(tmp_path: Path) -> None:
    _init(tmp_path)
    fake = tmp_path / "tailscale"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "assert sys.argv[1:] == ['ping', '--c', '1', 'worker-a.tailnet.ts.net'], sys.argv\n"
        "print('pong from worker-a (100.64.0.2) via direct in 3ms')\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {"PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", "")}
    node = json.loads(
        _run(
            tmp_path,
            [
                "node",
                "register",
                "--name",
                "WorkerA",
                "--host",
                "worker-a.tailnet.ts.net",
                "--ssh-user",
                "shiroe_worker",
                "--json",
            ],
        ).stdout
    )

    probed = _run(tmp_path, ["node", "probe", node["id"], "--json"], env=env)

    assert probed.returncode == 0, probed.stderr
    payload = json.loads(probed.stdout)
    assert payload["reachable"] is True
    assert payload["path_type"] == "direct"


def test_node_worker_run_validates_package_and_source_identity(tmp_path: Path) -> None:
    package = make_work_package(
        package_id="pkg_1",
        graph_id="graph1",
        work_node_id="work1",
        lease_id="lease_1",
        worker_node_id="node_worker",
        capability_id="cap.remote",
        capability_digest="sha256:cap",
        inputs={},
        timeout_s=30,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    ).to_dict()
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")
    config_path = tmp_path / "node.json"
    config_path.write_text(
        json.dumps(
            {
                "schema": "shiroe.node-local/v1",
                "node_id": "node_worker",
                "role": "worker",
                "trusted_controller_tailscale_id_digests": [CONTROLLER_DIGEST],
            }
        ),
        encoding="utf-8",
    )
    fake = tmp_path / "tailscale"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "assert sys.argv[1:] == ['whois', '--json', '100.64.0.1'], sys.argv\n"
        "print(json.dumps({'Node': {'ID': 'n-controller', 'Name': 'controller.'}, 'UserProfile': {'LoginName': 'controller@example.com'}}))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {
        "PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", ""),
        "SHIROE_NODE_CONFIG": str(config_path),
        "SHIROE_WORKER_CAPABILITY_DIGEST": "sha256:cap",
        "SSH_CONNECTION": "100.64.0.1 55555 100.64.0.2 22",
    }

    result = _run(tmp_path, ["node", "worker-run", "--package", str(package_path), "--json"], env=env)

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["schema"] == "shiroe.execution-receipt/v1"
    assert receipt["package_digest"] == package["digest"]
    assert receipt["controller_tailnet_id_digest"] == CONTROLLER_DIGEST
    assert "controller_tailnet_id" not in receipt
