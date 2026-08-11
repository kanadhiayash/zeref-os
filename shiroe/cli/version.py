from __future__ import annotations

import argparse

from shiroe.cli.common import print_json


COMMAND_NAME = "version"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Print version")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe import __version__

    payload = {"version": __version__}
    print_json(payload) if args.json else print(f"shiroe {__version__}")
    return 0
