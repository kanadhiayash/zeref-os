from __future__ import annotations

from pathlib import Path

from shiroe.policy.loader import load_policy_stack
from shiroe.policy.schema import ActionKind


def test_config_permissions_md_does_not_create_policy_layer(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "PERMISSIONS.md").write_text(
        "---\nnetwork: allowed\nwrite: memory/\n---\n",
        encoding="utf-8",
    )

    stack = load_policy_stack(tmp_path, global_root=tmp_path / "no-global")
    project_defaults = [layer for layer in stack if layer.name == "project-defaults"]

    assert project_defaults == []


def test_json_defaults_are_the_project_policy_lane(tmp_path: Path) -> None:
    policy_dir = tmp_path / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True)
    (policy_dir / "defaults.json").write_text(
        '{"allow":["fs.write"],"fs_write_scopes":["memory/views"]}',
        encoding="utf-8",
    )

    stack = load_policy_stack(tmp_path, global_root=tmp_path / "no-global")
    project_defaults = [layer for layer in stack if layer.name == "project-defaults"]

    assert len(project_defaults) == 1
    assert project_defaults[0].allows == frozenset({ActionKind.fs_write})
    assert project_defaults[0].fs_write_scopes == ("memory/views",)
