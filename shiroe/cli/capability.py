from __future__ import annotations

import argparse

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "capability"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Inspect executable capabilities")
    sub = parser.add_subparsers(dest="capability_command", required=True)
    sub.add_parser("list").add_argument("--json", action="store_true")
    sub.add_parser("adapters").add_argument("--json", action="store_true")
    gate = sub.add_parser("gate")
    gate.add_argument("capability_id")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    if args.capability_command == "adapters":
        from shiroe.adapters.capabilities.registry import list_adapters

        payload = list_adapters()
    elif args.capability_command == "gate":
        from shiroe.capabilities.gate import assert_executable

        assert_executable(project_root(), args.capability_id)
        payload = {"capability_id": args.capability_id, "status": "pass"}
    else:
        from shiroe.capabilities.store import CapabilityStore

        store = CapabilityStore(project_root())
        try:
            payload = store.list()
        finally:
            store.close()
    print_json(payload) if getattr(args, "json", False) else print(payload)
    return 0
