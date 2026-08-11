"""PR18 export-gate invariants (SHR-074, SHR-075, SHR-076).

Locks two properties of the export decision surface (`shiroe.policy.evaluate`):

1. **Precedence integrity for export.** A lower-precedence layer that grants
   an export-shaped action (``publish``, ``external_message``, ``push``,
   ``merge``) cannot flip a higher-precedence deny. Tested against every
   plausible "widen the deny" fixture: the full downstream stack granting
   the action, callers passing the stack out of layer order, and adversarial
   bypass hints inside ``Action.context``.
2. **Mandatory-approval bypass is closed.** For every ``ActionKind`` in
   ``ALWAYS_REQUIRE_APPROVAL``, no combination of ``AutonomyMode``, downstream
   allows, ``context`` hints, or missing-invariant scaffolding produces
   ``Verdict.allow``. The verdict is always ``require_approval`` and the
   reason names the autonomy mode that intercepted it.

The gate is:
    lower-precedence grants cannot widen a deny;
    mandatory approvals cannot be bypassed.

These tests drive the real evaluator — no mocks, no scenario framework.
"""

from __future__ import annotations

import itertools

import pytest

from shiroe.policy import (
    ALWAYS_REQUIRE_APPROVAL,
    Action,
    ActionKind,
    AutonomyMode,
    Verdict,
    evaluate,
)
from shiroe.policy.precedence import LAYER_ORDER, resolve
from shiroe.policy.schema import PolicyLayer


# Actions that leave the trust boundary — the "export" surface this PR pins.
EXPORT_KINDS: tuple[ActionKind, ...] = (
    ActionKind.publish,
    ActionKind.external_message,
    ActionKind.push,
    ActionKind.merge,
)

# Layers that sit below every deny layer. Any allow set here must not be able
# to flip a higher-precedence deny for an export action.
LOWER_LAYERS: tuple[str, ...] = (
    "explicit-user-grant",
    "project-defaults",
    "global-defaults",
    "harness-defaults",
)

# Adversarial hints a naive evaluator might honor from Action.context.
BYPASS_CONTEXTS: tuple[dict, ...] = (
    {"approved": True},
    {"approval_required": False},
    {"override": True},
    {"test_mode": True},
    {"skip_approval": True},
    {"emergency": True, "signed_off": True},
)


def _grant_layer(name: str, kinds: tuple[ActionKind, ...]) -> PolicyLayer:
    return PolicyLayer(name=name, allows=frozenset(kinds))


def _full_downstream_allow(kind: ActionKind) -> list[PolicyLayer]:
    """Every lower-precedence layer explicitly allows ``kind``.

    This is the maximum-permissive downstream stack — the shape that would
    tempt a naive evaluator to widen a higher-layer deny."""
    return [_grant_layer(name, (kind,)) for name in LOWER_LAYERS]


# ---------------------------------------------------------------------------
# SHR-074 / SHR-075 — precedence integrity on the export gate.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("deny_layer", ("project-deny", "global-deny"))
@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_export_deny_survives_full_downstream_allow(
    deny_layer: str, kind: ActionKind
) -> None:
    """Every lower layer granting ``kind`` cannot flip a project/global deny."""
    stack = [
        PolicyLayer(name=deny_layer, denies=frozenset({kind})),
        *_full_downstream_allow(kind),
    ]
    d = resolve(Action(kind), stack)
    assert d.verdict is Verdict.deny, (
        f"{deny_layer} deny for {kind.value} was widened by a lower grant"
    )
    assert d.deciding_layer == deny_layer


@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_export_runtime_invariant_deny_is_absolute(kind: ActionKind) -> None:
    """Runtime invariants outrank every other layer for export kinds."""
    stack = [
        PolicyLayer(name="runtime-invariant", denies=frozenset({kind})),
        PolicyLayer(name="project-deny", allows=frozenset({kind})),  # nonsense
        *_full_downstream_allow(kind),
    ]
    d = resolve(Action(kind), stack)
    assert d.verdict is Verdict.deny
    assert d.deciding_layer == "runtime-invariant"


@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_export_precedence_is_stable_under_stack_reordering(
    kind: ActionKind,
) -> None:
    """Callers passing layers in the wrong order do not weaken precedence."""
    layers = [
        PolicyLayer(name="project-deny", denies=frozenset({kind})),
        *_full_downstream_allow(kind),
        PolicyLayer(name="runtime-invariant"),
    ]
    # Every permutation of the layer sequence must resolve to the same deny.
    seen: set[tuple[str, str]] = set()
    for perm in itertools.permutations(layers):
        d = resolve(Action(kind), list(perm))
        seen.add((d.verdict.value, d.deciding_layer))
    assert seen == {("deny", "project-deny")}, (
        f"resolution not invariant under reordering: {seen}"
    )


@pytest.mark.parametrize("kind", EXPORT_KINDS)
@pytest.mark.parametrize("ctx", BYPASS_CONTEXTS)
def test_export_deny_ignores_bypass_hints_in_action_context(
    kind: ActionKind, ctx: dict
) -> None:
    """Nothing inside ``Action.context`` can widen a higher-layer deny."""
    stack = [
        PolicyLayer(name="project-deny", denies=frozenset({kind})),
        *_full_downstream_allow(kind),
    ]
    d = resolve(Action(kind, target="dist/", context=ctx), stack)
    assert d.verdict is Verdict.deny
    assert d.deciding_layer == "project-deny"


def test_export_layer_order_matches_adr_0005() -> None:
    """Fail loudly if the documented layer order ever drifts.

    The precedence rule is only meaningful if the sequence in code is the one
    ADR-0005 pins. If a refactor renames or reorders these, this test breaks
    before any invariant test does — which is the intent.
    """
    assert LAYER_ORDER == (
        "runtime-invariant",
        "project-deny",
        "global-deny",
        "explicit-user-grant",
        "project-defaults",
        "global-defaults",
        "harness-defaults",
    )


# ---------------------------------------------------------------------------
# SHR-076 — mandatory-approval bypass is closed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", list(AutonomyMode))
@pytest.mark.parametrize(
    "kind", sorted(ALWAYS_REQUIRE_APPROVAL, key=lambda k: k.value)
)
def test_always_approval_not_bypassed_by_maximum_permissive_stack(
    mode: AutonomyMode, kind: ActionKind
) -> None:
    """Even with every downstream layer granting, approval is still required."""
    stack = [
        PolicyLayer(name="runtime-invariant"),
        *_full_downstream_allow(kind),
    ]
    d = evaluate(Action(kind), stack, mode=mode)
    assert d.verdict is Verdict.require_approval, (
        f"{kind.value} was auto-allowed under mode {mode.value}"
    )
    # Reason must name the autonomy mode that intercepted the grant, so an
    # audit trail explains why an otherwise-allowed action stopped.
    assert mode.value in d.reason


@pytest.mark.parametrize(
    "kind", sorted(ALWAYS_REQUIRE_APPROVAL, key=lambda k: k.value)
)
@pytest.mark.parametrize("ctx", BYPASS_CONTEXTS)
def test_always_approval_not_bypassed_by_context_hints(
    kind: ActionKind, ctx: dict
) -> None:
    """Bypass-flavored keys in ``Action.context`` do not skip approval."""
    stack = [
        PolicyLayer(name="runtime-invariant"),
        _grant_layer("explicit-user-grant", (kind,)),
    ]
    d = evaluate(
        Action(kind, target="prod", context=ctx),
        stack,
        mode=AutonomyMode.policy_bound,
    )
    assert d.verdict is Verdict.require_approval


@pytest.mark.parametrize(
    "kind", sorted(ALWAYS_REQUIRE_APPROVAL, key=lambda k: k.value)
)
def test_always_approval_not_bypassed_when_runtime_layer_absent(
    kind: ActionKind,
) -> None:
    """A caller that forgets to load the runtime-invariant layer still cannot
    dodge approval — the always-approval list is enforced in the autonomy
    gate, not in the layer stack, so a missing anchor cannot silently open
    the export surface."""
    stack = _full_downstream_allow(kind)  # no runtime-invariant, no denies
    d = evaluate(Action(kind), stack, mode=AutonomyMode.policy_bound)
    assert d.verdict is Verdict.require_approval


@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_export_deny_wins_over_always_approval(kind: ActionKind) -> None:
    """When export is both denied AND on the always-approval list, deny wins.

    Approval is only meaningful if an allow reached the autonomy gate; a
    higher-layer deny must terminate the decision without offering an
    "approve to bypass" path."""
    stack = [
        PolicyLayer(name="project-deny", denies=frozenset({kind})),
        _grant_layer("explicit-user-grant", (kind,)),
    ]
    d = evaluate(Action(kind), stack, mode=AutonomyMode.policy_bound)
    assert d.verdict is Verdict.deny
    assert d.deciding_layer == "project-deny"


def test_export_kinds_are_all_on_always_approval_list() -> None:
    """Guard against silently dropping an export kind from the mandatory list.

    If a future edit removes ``publish``/``push``/``merge``/``external_message``
    from ``ALWAYS_REQUIRE_APPROVAL``, this test breaks — which is the point;
    those kinds define the export surface this PR pins."""
    for kind in EXPORT_KINDS:
        assert kind in ALWAYS_REQUIRE_APPROVAL, (
            f"{kind.value} left the mandatory-approval list; export surface widened"
        )
