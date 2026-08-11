import pytest

from shiroe.adapters.capabilities.registry import adapter_registry
from shiroe.capabilities.manifest import ManifestError, validate_manifest


def test_context_only_adapters_are_not_registered():
    names = set(adapter_registry().keys())
    assert "generic-skill" not in names
    assert "generic" not in names
    assert "skill" not in names
    assert "agent" not in names


def test_manifest_requires_executable_entrypoint_for_invokable_type():
    with pytest.raises(ManifestError, match="entrypoint"):
        validate_manifest(
            {
                "schema": "shiroe.capability/v1",
                "id": "x",
                "name": "x",
                "type": "cli",
                "version": "1",
                "source": {"kind": "local-directory"},
                "entrypoint": {"adapter": "cli"},
                "requires": {},
            }
        )
