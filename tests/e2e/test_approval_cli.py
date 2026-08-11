from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy.approval_service import ApprovalService


ROOT = Path(__file__).resolve().parents[2]


def _run(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def _seed_reasoner(root: Path) -> str:
    script = root / "advisor.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'recommendation':'revise','rationale':'needs narrower scope','risks':[],'evidence_gaps':[],'conditions':[]}))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    capability_id = "test.reasoner"
    CapabilityStore(root).upsert_capability(
        capability_id=capability_id,
        name="Test Reasoner",
        type_="script",
        lifecycle="active",
        digest=inspect_source(script).digest,
        manifest={
            "schema": "shiroe.capability/v1",
            "id": capability_id,
            "name": "Test Reasoner",
            "type": "script",
            "version": "1.0.0",
            "source": {"kind": "file", "location": str(script)},
            "entrypoint": {"adapter": "cli"},
            "requires": {},
        },
        source_kind="file",
        source_location=str(script),
    )
    return capability_id


def test_approval_advise_does_not_decide_and_human_decide_approves(tmp_path: Path) -> None:
    init = _run(ROOT, ["init", str(tmp_path), "--name", "approvals", "--privacy", "abstract", "--tier", "auto"])
    assert init.returncode == 0, init.stderr
    policy_dir = tmp_path / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True)
    (policy_dir / "defaults.json").write_text('{"allow":["subprocess"]}', encoding="utf-8")
    approval = ApprovalService(tmp_path).request(
        approval_type="strategic",
        requested_action="choose release path",
        scope={"path": "release"},
        reason="human boundary",
        risk="high",
    )
    capability_id = _seed_reasoner(tmp_path)

    advice = _run(tmp_path, ["approve", "advise", approval.id, "--capability", capability_id, "--json"])
    assert advice.returncode == 0, advice.stderr
    assert json.loads(advice.stdout)["recommendation"] == "revise"

    shown = _run(tmp_path, ["approve", "show", approval.id, "--json"])
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout)["status"] == "pending"

    decided = _run(
        tmp_path,
        ["approve", "decide", approval.id, "--decision", "approved", "--reason", "human confirmed", "--json"],
    )
    assert decided.returncode == 0, decided.stderr
    payload = json.loads(decided.stdout)
    assert payload["status"] == "approved"
    assert payload["decided_by"] == "human"
