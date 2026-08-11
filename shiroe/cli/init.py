from __future__ import annotations

import argparse
from pathlib import Path


COMMAND_NAME = "init"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Scaffold a Shiroe project")
    parser.add_argument("directory", nargs="?", help="Target directory")
    parser.add_argument("--name", required=True)
    parser.add_argument("--privacy", choices=["abstract", "exact", "local-only"], default="abstract")
    parser.add_argument("--tier", choices=["auto", "free", "standard", "god-mode"], default="auto")
    parser.add_argument("--parent", default="")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe.memory import normalize_init_values, scaffold_project

    root = Path(args.directory).resolve() if args.directory else Path.cwd()
    values = normalize_init_values(name=args.name, privacy=args.privacy, tier=args.tier, parent=args.parent)
    scaffold_project(root, name=values["name"], privacy=values["privacy"], tier=values["tier"], parent=values["parent"])
    print(f"scaffolded {root}")
    return 0
