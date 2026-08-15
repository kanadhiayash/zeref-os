"""Precedence resolution (vNext §13.3)."""

from __future__ import annotations

from typing import Iterable

from shiroe.policy.schema import Action, ActionKind, Decision, PolicyLayer, Verdict


# Runtime safety invariants: nothing further down the chain can weaken these.
_RUNTIME_INVARIANTS_DENY: frozenset[ActionKind] = frozenset()


# Layer names, top→bottom. First match wins for denies; grants require a
# permitting layer at or below any relevant deny.
LAYER_ORDER = (
    "runtime-invariant",
    "project-deny",
    "global-deny",
    "explicit-user-grant",
    "project-defaults",
    "global-defaults",
    "harness-defaults",
)


def _layer_dict(stack: Iterable[PolicyLayer]) -> dict[str, PolicyLayer]:
    return {layer.name: layer for layer in stack}


def _path_in_scopes(target: str, scopes: tuple[str, ...]) -> bool:
    if not scopes:
        return True
    normalized_target = target.strip().rstrip("/")
    if not normalized_target:
        return False
    for scope in scopes:
        normalized_scope = scope.strip().rstrip("/")
        if not normalized_scope:
            continue
        if normalized_target == normalized_scope:
            return True
        if normalized_target.startswith(normalized_scope + "/"):
            return True
    return False


def _target_allowed(action: Action, layer: PolicyLayer) -> bool:
    if action.kind is ActionKind.network:
        return not layer.network_hosts or action.target in layer.network_hosts
    if action.kind is ActionKind.fs_write:
        return _path_in_scopes(action.target, layer.fs_write_scopes)
    if action.kind is ActionKind.fs_read:
        return _path_in_scopes(action.target, layer.fs_read_scopes)
    return True


def resolve(action: Action, stack: Iterable[PolicyLayer]) -> Decision:
    layers = _layer_dict(stack)

    # 1. Runtime invariants — hardcoded, non-overridable.
    inv = layers.get("runtime-invariant")
    if inv is not None and action.kind in inv.denies:
        return Decision(Verdict.deny, "runtime safety invariant",
                        "runtime-invariant")

    # 2 / 3. Denies at project/global scope — final.
    for name in ("project-deny", "global-deny"):
        layer = layers.get(name)
        if layer is None:
            continue
        if action.kind in layer.denies and _target_allowed(action, layer):
            return Decision(Verdict.deny, f"denied by {name}", name)

    # 4. Explicit user grants — override defaults but not denies above.
    egrant = layers.get("explicit-user-grant")
    if egrant is not None and action.kind in egrant.allows and _target_allowed(action, egrant):
        return Decision(Verdict.allow, "explicit user grant",
                        "explicit-user-grant")

    # 5–7. Defaults (project → global → harness): first allow wins.
    for name in ("project-defaults", "global-defaults", "harness-defaults"):
        layer = layers.get(name)
        if layer is None:
            continue
        if action.kind in layer.allows and _target_allowed(action, layer):
            return Decision(Verdict.allow, f"allowed by {name}", name)
        if action.kind in layer.denies and _target_allowed(action, layer):
            return Decision(Verdict.deny, f"denied by {name}", name)

    # Default is deny.
    return Decision(Verdict.deny, "no matching allow rule",
                    "default-deny")


def narrower(a: PolicyLayer, b: PolicyLayer) -> PolicyLayer:
    """Combine two same-name layers by narrowing: union denies, intersect allows.

    Used when both project-deny and global-deny apply — the effective deny
    set is the union.
    """
    return PolicyLayer(
        name=a.name,
        denies=a.denies | b.denies,
        allows=a.allows & b.allows,
        fs_write_scopes=tuple(sorted(set(a.fs_write_scopes) & set(b.fs_write_scopes))),
        fs_read_scopes=tuple(sorted(set(a.fs_read_scopes) | set(b.fs_read_scopes))),
        network_hosts=tuple(sorted(set(a.network_hosts) & set(b.network_hosts))),
    )
