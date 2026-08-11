"""Adapter registry — resolves ``entrypoint.adapter`` → adapter instance.

Adapters are stateless singletons. Lookup is deterministic and offline.
"""

from __future__ import annotations

from shiroe.adapters.capabilities.base import CapabilityAdapter
from shiroe.adapters.capabilities.cli import CLIAdapter
from shiroe.adapters.capabilities.repository_tool import RepositoryToolAdapter


class AdapterNotFoundError(KeyError):
    pass


_ADAPTERS: dict[str, CapabilityAdapter] = {
    "cli": CLIAdapter(),
    "repository-tool": RepositoryToolAdapter(),
    "repository_tool": RepositoryToolAdapter(),
}


def adapter_registry() -> dict[str, CapabilityAdapter]:
    return dict(_ADAPTERS)


def register_adapter(name: str, adapter: CapabilityAdapter) -> None:
    if not name.strip():
        raise ValueError("adapter name must be non-empty")
    _ADAPTERS[name] = adapter


def resolve_adapter(name: str) -> CapabilityAdapter:
    try:
        return _ADAPTERS[name]
    except KeyError as e:
        raise AdapterNotFoundError(
            f"no capability adapter registered for {name!r}. "
            f"Known: {sorted(set(_ADAPTERS))}"
        ) from e


def list_adapters() -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    for _, adapter in _ADAPTERS.items():
        if adapter.name in seen:
            continue
        seen.add(adapter.name)
        rows.append({
            "name": adapter.name,
            "enforcement_level": adapter.enforcement_level.value,
            "supported_types": list(adapter.supported_types),
        })
    return rows
