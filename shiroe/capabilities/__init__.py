"""Capability registry & lifecycle (vNext §8, ADR-0004).

Every executable unit of work — CLI, repository tool, script, workflow,
evaluator, or API service — enters Shiroe through this package. Nothing runs until it is ``approved`` (or a
lifecycle state past it) AND its stored digest still matches the source
on disk.

The single choke point every executor must call:

    from shiroe.capabilities import assert_executable
    assert_executable(root, capability_id)   # raises CapabilityGateError
"""

from shiroe.capabilities.manifest import (
    CAPABILITY_SCHEMA,
    ManifestError,
    infer_manifest,
    validate_manifest,
)
from shiroe.capabilities.lifecycle import (
    LIFECYCLE_STATES,
    EXECUTABLE_STATES,
    InvalidTransition,
    can_transition,
    is_executable,
    next_state_for_digest_change,
)
from shiroe.capabilities.discovery import discover
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import (
    CapabilityStore,
    register_discovery,
    approve,
    revoke,
)
from shiroe.capabilities.gate import CapabilityGateError, assert_executable

__all__ = [
    "CAPABILITY_SCHEMA",
    "ManifestError", "infer_manifest", "validate_manifest",
    "LIFECYCLE_STATES", "EXECUTABLE_STATES", "InvalidTransition",
    "can_transition", "is_executable", "next_state_for_digest_change",
    "discover", "inspect_source",
    "CapabilityStore", "register_discovery", "approve", "revoke",
    "CapabilityGateError", "assert_executable",
]
