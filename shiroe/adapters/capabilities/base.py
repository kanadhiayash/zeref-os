"""Adapter protocol + shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class EnforcementLevel(str, Enum):
    """How much runtime control Shiroe actually has over this adapter."""

    embedded = "A"        # subprocess or native hook we own
    sidecar = "B"         # routed through Shiroe CLI / MCP / proxy


@dataclass(frozen=True)
class AdapterResult:
    """Return value from ``CapabilityAdapter.invoke``.

    ``usage`` carries the adapter's own accounting of what the call cost
    (SHR-055/063). Shape: ``{"tokens_in": int, "tokens_out": int,
    "cost_usd": float}``. Adapters that don't report usage leave this
    ``None`` and the supervisor charges zero — better a truthful zero
    than a hardcoded fiction.
    """

    ok: bool
    output: Any = None
    error: str | None = None
    exit_code: int | None = None
    stderr_tail: str | None = None
    metadata: dict = field(default_factory=dict)
    usage: dict | None = None


@dataclass(frozen=True)
class HealthReport:
    """What ``adapter.health()`` returns and what
    ``shiroe.adapters.capabilities.health.record_status`` writes to the
    ``adapter_status`` SQLite row."""

    adapter: str
    detected_version: str | None
    enforcement_level: EnforcementLevel
    supported_features: tuple[str, ...] = ()
    healthy: bool = True
    failure_reason: str | None = None
    supported_types: tuple[str, ...] = ()


@runtime_checkable
class CapabilityAdapter(Protocol):
    """Every adapter conforms to this shape.

    Adapters are stateless singletons. Nothing here calls network endpoints
    unless the concrete adapter says so in ``supported_features``.
    """

    name: str
    enforcement_level: EnforcementLevel
    supported_types: tuple[str, ...]

    def health(self) -> HealthReport: ...
    def invoke(self,
               *,
               capability_id: str,
               action: str,
               inputs: dict,
               permissions: dict | None = None,
               timeout_s: int | None = None) -> AdapterResult: ...
