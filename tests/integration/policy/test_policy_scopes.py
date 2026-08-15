from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiroe.policy.autonomy import AutonomyMode
from shiroe.policy.schema import Action, ActionKind, Verdict
from shiroe.policy.service import PolicyService
from shiroe.security import NetworkDeniedError, load_policy, require_network


def _write_privacy(root: Path, network_scope: str) -> None:
    (root / "PRIVACY.md").write_text(
        f"---\nmode: abstract\nnetwork_scope: {network_scope}\n---\n",
        encoding="utf-8",
    )


def _write_defaults(root: Path, data: dict) -> None:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps(data, sort_keys=True),
        encoding="utf-8",
    )


def _write_deny(root: Path, data: dict) -> None:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "deny.json").write_text(
        json.dumps(data, sort_keys=True),
        encoding="utf-8",
    )


def test_missing_policy_is_default_deny(tmp_path: Path) -> None:
    result = PolicyService(tmp_path).authorize(
        Action(ActionKind.fs_read, target="memory/hot.md"),
        mode=AutonomyMode.policy_bound,
    )

    assert result.verdict is Verdict.deny
    assert result.reason == "no matching allow rule"


def test_authorize_call_does_not_create_implicit_grant(tmp_path: Path) -> None:
    result = PolicyService(tmp_path).authorize(
        Action(ActionKind.capability_invoke, target="test.echo"),
        mode=AutonomyMode.policy_bound,
    )

    assert result.verdict is Verdict.deny
    assert result.approval_id is None


def test_network_scope_device_only_cannot_be_widened_by_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_privacy(tmp_path, "device-only")
    _write_defaults(
        tmp_path,
        {
            "allow": ["network"],
            "network_hosts": ["worker-a.tailnet.test"],
        },
    )
    monkeypatch.setenv("SHIROE_ALLOW_NETWORK", "1")

    with pytest.raises(NetworkDeniedError, match="device-only"):
        require_network(
            load_policy(tmp_path),
            purpose="remote worker probe",
            target="worker-a.tailnet.test",
            destination_scope="tailnet",
        )


def test_tailnet_scope_rejects_external_destination(tmp_path: Path) -> None:
    _write_privacy(tmp_path, "tailnet")
    _write_defaults(
        tmp_path,
        {
            "allow": ["network"],
            "network_hosts": ["api.example.com"],
        },
    )

    with pytest.raises(NetworkDeniedError, match="external"):
        require_network(
            load_policy(tmp_path),
            purpose="provider refresh",
            target="api.example.com",
            destination_scope="external",
        )


def test_network_grant_for_worker_does_not_allow_other_host(tmp_path: Path) -> None:
    _write_privacy(tmp_path, "tailnet")
    _write_defaults(
        tmp_path,
        {
            "allow": ["network"],
            "network_hosts": ["worker-a.tailnet.test"],
        },
    )

    with pytest.raises(NetworkDeniedError, match="worker-b.tailnet.test"):
        require_network(
            load_policy(tmp_path),
            purpose="remote worker probe",
            target="worker-b.tailnet.test",
            destination_scope="tailnet",
        )


def test_fs_write_scope_does_not_allow_sibling_path(tmp_path: Path) -> None:
    _write_defaults(
        tmp_path,
        {
            "allow": ["fs.write"],
            "fs_write_scopes": ["memory/views"],
        },
    )

    result = PolicyService(tmp_path).authorize(
        Action(ActionKind.fs_write, target="memory/raw/secret.txt"),
        mode=AutonomyMode.policy_bound,
    )

    assert result.verdict is Verdict.deny
    assert result.reason == "no matching allow rule"


def test_configured_reversible_capability_invoke_allows(tmp_path: Path) -> None:
    _write_defaults(tmp_path, {"allow": ["capability.invoke"]})

    result = PolicyService(tmp_path).authorize(
        Action(ActionKind.capability_invoke, target="test.echo"),
        mode=AutonomyMode.policy_bound,
    )

    assert result.verdict is Verdict.allow
    assert result.deciding_layer == "project-defaults"


def test_configured_irreversible_publish_requires_human_approval(tmp_path: Path) -> None:
    _write_defaults(tmp_path, {"allow": ["publish"]})

    result = PolicyService(tmp_path).authorize(
        Action(ActionKind.publish, target="release-v1"),
        scope={"tag": "v1"},
        mode=AutonomyMode.policy_bound,
    )

    assert result.verdict is Verdict.require_approval
    assert result.approval_id


def test_project_deny_beats_allows(tmp_path: Path) -> None:
    _write_defaults(tmp_path, {"allow": ["publish"]})
    _write_deny(tmp_path, {"deny": ["publish"]})

    result = PolicyService(tmp_path).authorize(
        Action(ActionKind.publish, target="release-v1"),
        scope={"tag": "v1"},
        mode=AutonomyMode.policy_bound,
    )

    assert result.verdict is Verdict.deny
    assert result.approval_id is None
