import importlib


def test_runtime_components_import():
    for module in (
        "shiroe.storage",
        "shiroe.policy",
        "shiroe.capabilities",
        "shiroe.memory",
        "shiroe.handoff",
        "shiroe.execution",
    ):
        importlib.import_module(module)


def test_every_registered_cli_handler_is_callable():
    from shiroe.cli.main import iter_registered_commands

    for command, handler in iter_registered_commands():
        assert callable(handler), command


def test_every_registered_adapter_is_invokable_and_healthy():
    from shiroe.adapters.capabilities.registry import adapter_registry

    for name, adapter in adapter_registry().items():
        assert callable(adapter.invoke), name
        assert adapter.health().healthy is True
