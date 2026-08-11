from __future__ import annotations

import argparse
from dataclasses import asdict

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "run"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Run or dry-run a Work Graph")
    parser.add_argument("--graph", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = project_root()
    if args.dry_run:
        from shiroe.work.store import WorkStore

        store = WorkStore(root)
        try:
            graph = store.get(args.graph)
            ready = set(store.ready_node_ids(args.graph))
            payload = {
                "graph_id": graph.id,
                "dry_run": True,
                "selected": [
                    {"id": node.id, "requires": list(node.requires), "policy": "not_invoked"}
                    for node in graph.nodes
                    if node.id in ready
                ],
            }
        finally:
            store.close()
    else:
        from shiroe.execution import ExecutionSupervisor

        payload = asdict(ExecutionSupervisor(root).run(args.graph))
    print_json(payload) if args.json or args.dry_run else print(payload["status"])
    return 0
