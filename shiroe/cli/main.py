"""vNext command router."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from shiroe import __version__
from shiroe.cli import (
    approve,
    capability,
    doctor,
    handoff,
    init,
    memory,
    node,
    plan,
    policy,
    run,
    state,
    status,
    verify,
    version,
)


_COMMANDS = (
    init,
    status,
    plan,
    run,
    approve,
    memory,
    node,
    verify,
    handoff,
    doctor,
    policy,
    capability,
    state,
    version,
)

_PUBLIC_COMMAND_NAMES = (
    "init",
    "status",
    "plan",
    "run",
    "approve",
    "memory",
    "verify",
    "handoff",
    "doctor",
    "policy",
    "capability",
    "state",
    "version",
)


def registered_command_names() -> tuple[str, ...]:
    return tuple(module.COMMAND_NAME for module in _COMMANDS)


def iter_registered_commands():
    for module in _COMMANDS:
        yield module.COMMAND_NAME, module.run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shiroe", description=f"Shiroe CLI v{__version__}")
    parser.add_argument("--version", action="version", version=f"shiroe {__version__}")
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{" + ",".join(_PUBLIC_COMMAND_NAMES) + "}",
    )
    for module in _COMMANDS:
        module.register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
