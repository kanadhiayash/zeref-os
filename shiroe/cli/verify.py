from __future__ import annotations

import argparse

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "verify"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Verify Work Graph or memory state")
    parser.add_argument("--graph")
    parser.add_argument("--memory")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = project_root()
    if args.graph:
        from shiroe.work.schema import NodeStatus
        from shiroe.work.store import WorkStore

        store = WorkStore(root)
        try:
            graph = store.get(args.graph)
            blocked = [node.id for node in graph.nodes if store.get_node(node.id).status is NodeStatus.blocked]
        finally:
            store.close()
        payload = {"subject": "work_graph", "graph_id": args.graph, "status": "block" if blocked else "pass", "blocked_nodes": blocked}
    elif args.memory:
        from shiroe.memory.service import MemoryService

        service = MemoryService(root)
        try:
            record = service.get(args.memory)
        finally:
            service.close()
        payload = {"subject": "memory", "memory_id": record.id, "status": "pass"}
    else:
        payload = {"subject": "runtime", "status": "pass"}
    print_json(payload) if args.json else print(payload["status"])
    return 0 if payload["status"] == "pass" else 1
