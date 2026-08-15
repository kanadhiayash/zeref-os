"""vNext PR 3 gate tests — policy & permission engine (ADR-0005)."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from shiroe.policy import (
    ALWAYS_REQUIRE_APPROVAL,
    Action,
    ActionKind,
    AutonomyMode,
    Decision,
    Verdict,
    autonomy_gate,
    evaluate,
    load_policy_stack,
)
from shiroe.policy.precedence import LAYER_ORDER, resolve
from shiroe.policy.schema import PolicyLayer


def _stack(**layers: dict) -> list[PolicyLayer]:
    order = {name: i for i, name in enumerate(LAYER_ORDER)}
    out = [PolicyLayer(name="runtime-invariant")]
    for name, spec in layers.items():
        real = name.replace("_", "-")
        out.append(PolicyLayer(
            name=real,
            denies=frozenset(ActionKind(v) for v in spec.get("deny", [])),
            allows=frozenset(ActionKind(v) for v in spec.get("allow", [])),
        ))
    out.sort(key=lambda layer: order.get(layer.name, 99))
    return out


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------

def test_default_is_deny() -> None:
    d = resolve(Action(ActionKind.network), _stack())
    assert d.verdict is Verdict.deny
    assert d.deciding_layer == "default-deny"


def test_project_defaults_can_allow() -> None:
    stack = _stack(project_defaults={"allow": ["network"]})
    d = resolve(Action(ActionKind.network), stack)
    assert d.verdict is Verdict.allow
    assert d.deciding_layer == "project-defaults"


def test_project_deny_beats_lower_grants() -> None:
    stack = _stack(
        project_deny={"deny": ["network"]},
        explicit_user_grant={"allow": ["network"]},
        project_defaults={"allow": ["network"]},
        global_defaults={"allow": ["network"]},
    )
    d = resolve(Action(ActionKind.network), stack)
    assert d.verdict is Verdict.deny
    assert d.deciding_layer == "project-deny"


def test_explicit_user_grant_beats_defaults_but_not_deny() -> None:
    stack = _stack(
        explicit_user_grant={"allow": ["fs.write"]},
        project_defaults={"deny": ["fs.write"]},
    )
    d = resolve(Action(ActionKind.fs_write), stack)
    assert d.verdict is Verdict.allow
    assert d.deciding_layer == "explicit-user-grant"


def test_runtime_invariants_denies_are_absolute() -> None:
    stack = [
        PolicyLayer(name="runtime-invariant",
                    denies=frozenset({ActionKind.destructive})),
        PolicyLayer(name="explicit-user-grant",
                    allows=frozenset({ActionKind.destructive})),
        PolicyLayer(name="project-defaults",
                    allows=frozenset({ActionKind.destructive})),
    ]
    d = resolve(Action(ActionKind.destructive), stack)
    assert d.verdict is Verdict.deny
    assert d.deciding_layer == "runtime-invariant"


# ---------------------------------------------------------------------------
# Monotonicity — the PR-3 acceptance gate.
# ---------------------------------------------------------------------------

_LOWER_LAYERS = (
    "explicit-user-grant", "project-defaults",
    "global-defaults", "harness-defaults",
)
_HIGHER_DENY_LAYERS = ("runtime-invariant", "project-deny", "global-deny")


@pytest.mark.parametrize(
    "higher_layer,lower_layer,kind",
    list(itertools.product(_HIGHER_DENY_LAYERS, _LOWER_LAYERS, list(ActionKind))),
)
def test_lower_layer_cannot_widen_higher_denial(
    higher_layer: str, lower_layer: str, kind: ActionKind,
) -> None:
    """No combination of a lower-layer allow may flip a higher-layer deny."""
    stack = [
        PolicyLayer(name=higher_layer, denies=frozenset({kind})),
        PolicyLayer(name=lower_layer, allows=frozenset({kind})),
    ]
    d = resolve(Action(kind), stack)
    assert d.verdict is Verdict.deny, (
        f"lower layer {lower_layer} widened higher deny at {higher_layer} for {kind.value}"
    )


# ---------------------------------------------------------------------------
# Autonomy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", list(AutonomyMode))
@pytest.mark.parametrize("kind", sorted(ALWAYS_REQUIRE_APPROVAL, key=lambda k: k.value))
def test_always_require_approval_regardless_of_mode(
    mode: AutonomyMode, kind: ActionKind,
) -> None:
    stack = _stack(project_defaults={"allow": [kind.value]})
    d = evaluate(Action(kind), stack, mode=mode)
    assert d.verdict is Verdict.require_approval, (
        f"{kind.value} must require approval under mode {mode.value}"
    )


def test_suggest_mode_never_executes() -> None:
    stack = _stack(project_defaults={"allow": ["memory.write"]})
    d = evaluate(Action(ActionKind.memory_write), stack,
                 mode=AutonomyMode.suggest)
    assert d.verdict is Verdict.require_approval


def test_auto_safe_runs_only_reversible() -> None:
    stack = _stack(project_defaults={"allow": ["memory.write", "fs.write"]})
    ok = evaluate(Action(ActionKind.memory_write), stack,
                  mode=AutonomyMode.auto_safe)
    assert ok.verdict is Verdict.allow
    nope = evaluate(Action(ActionKind.fs_write), stack,
                    mode=AutonomyMode.auto_safe)
    assert nope.verdict is Verdict.require_approval


def test_policy_bound_runs_non_approval_actions() -> None:
    stack = _stack(project_defaults={"allow": ["fs.write"]})
    d = evaluate(Action(ActionKind.fs_write), stack,
                 mode=AutonomyMode.policy_bound)
    assert d.verdict is Verdict.allow


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def test_loader_ignores_permissions_md_for_project_policy(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "PERMISSIONS.md").write_text(
        "network: denied\nwrite: memory/\nread: project-root\n",
        encoding="utf-8",
    )
    stack = load_policy_stack(tmp_path, global_root=tmp_path / "no-such")
    d = resolve(Action(ActionKind.network), stack)
    assert d.verdict is Verdict.deny
    d = resolve(Action(ActionKind.fs_write), stack)
    assert d.verdict is Verdict.deny


def test_loader_reads_project_defaults_json(tmp_path: Path) -> None:
    (tmp_path / ".shiroe" / "policy").mkdir(parents=True)
    (tmp_path / ".shiroe" / "policy" / "defaults.json").write_text(
        json.dumps({"allow": ["fs.write"], "fs_write_scopes": ["memory"]}),
        encoding="utf-8",
    )

    stack = load_policy_stack(tmp_path, global_root=tmp_path / "no-such")
    d = resolve(Action(ActionKind.fs_write, target="memory/hot.md"), stack)
    assert d.verdict is Verdict.allow


def test_loader_project_deny_json(tmp_path: Path) -> None:
    (tmp_path / ".shiroe" / "policy").mkdir(parents=True)
    (tmp_path / ".shiroe" / "policy" / "deny.json").write_text(
        json.dumps({"deny": ["fs.delete"]}), encoding="utf-8",
    )
    stack = load_policy_stack(tmp_path, global_root=tmp_path / "no-such")
    d = resolve(Action(ActionKind.fs_delete), stack)
    assert d.verdict is Verdict.deny
    assert d.deciding_layer == "project-deny"
