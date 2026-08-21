from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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


def _ok(result: subprocess.CompletedProcess) -> str:
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    return result.stdout


def _seed_reasoner(root: Path) -> str:
    """Onboard the reasoner capability through the real CLI (project-relative
    source path -- REDACT.md would scrub an absolute external path such as
    sys.executable) and approve it so the gate lets `advise` invoke it."""
    script = root / "advisor.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'recommendation':'revise','rationale':'needs narrower scope','risks':[],'evidence_gaps':[],'conditions':[]}))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    onboarded = json.loads(_ok(_run(root, ["capability", "onboard", str(script), "--json"])))
    capability_id = onboarded["capability_id"]
    _ok(_run(root, [
        "approve", "decide", onboarded["approval_id"],
        "--decision", "approved",
        "--reason", "test setup: allow reasoner capability to execute",
        "--json",
    ]))
    return capability_id


def test_approval_advise_does_not_decide_and_human_decide_approves(tmp_path: Path) -> None:
    init = _run(ROOT, ["init", str(tmp_path), "--name", "approvals", "--privacy", "abstract"])
    assert init.returncode == 0, init.stderr
    policy_dir = tmp_path / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        '{"allow":["capability.invoke","subprocess"]}',
        encoding="utf-8",
    )
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
