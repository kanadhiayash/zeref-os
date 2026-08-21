from __future__ import annotations

import argparse

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "status"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Show project or Work Graph status")
    parser.add_argument("--graph")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--runtime", action="store_true", help="Emit the runtime-update disclosure payload")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = project_root()
    if args.runtime:
        from shiroe.runtime.report import build_runtime_report

        payload = build_runtime_report(root)
        if args.graph:
            from shiroe.work.store import WorkStore

            store = WorkStore(root)
            try:
                graph = store.get(args.graph)
            finally:
                store.close()
            payload["run"]["graph_id"] = graph.id
            payload["run"]["status"] = graph.status.value
        if args.json:
            print_json(payload)
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0
    if args.graph:
        from shiroe.work.store import WorkStore

        store = WorkStore(root)
        try:
            graph = store.get(args.graph)
            nodes = [
                {"id": node.id, "status": store.get_node(node.id).status.value, "objective": node.objective}
                for node in graph.nodes
            ]
        finally:
            store.close()
        payload = {"graph": {"id": graph.id, "status": graph.status.value, "version": graph.version}, "nodes": nodes}
    else:
        payload = {
            "project_root": str(root),
            "state": str(root / "memory" / "state" / "shiroe.sqlite"),
            "privacy": str(root / "PRIVACY.md"),
        }
    if args.json:
        print_json(payload)
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0
