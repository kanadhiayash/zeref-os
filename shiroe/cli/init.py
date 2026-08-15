from __future__ import annotations

import argparse
from pathlib import Path


COMMAND_NAME = "init"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Scaffold a Shiroe project")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--name")
    parser.add_argument("--privacy", choices=("abstract", "exact"), default="abstract")
    parser.add_argument(
        "--network-scope",
        choices=("device-only", "tailnet", "external"),
        default="device-only",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe.memory import normalize_init_values, scaffold_project

    root = Path(args.path).resolve()
    values = normalize_init_values(
        name=args.name,
        privacy=args.privacy,
        network_scope=args.network_scope,
    )
    scaffold_project(
        root,
        name=values["name"],
        privacy=values["privacy"],
        network_scope=values["network_scope"],
    )
    print(f"scaffolded {root}")
    return 0
